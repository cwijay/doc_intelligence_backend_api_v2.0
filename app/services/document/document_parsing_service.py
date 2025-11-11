import os
import tempfile
from typing import Optional, Dict, Any
from pathlib import Path
from datetime import datetime

from app.core.logging import get_service_logger
from app.core.gcs_client import gcs_client, GCSClientError, GCSObjectNotFoundError
from app.core.firebase_client import get_collection, firebase_manager
from app.ai.file_parser import parse_with_metadata, is_supported_file_type
from app.models.document import DocumentStatus
from google.api_core.exceptions import GoogleAPIError
from google.cloud.firestore import FieldFilter

logger = get_service_logger("document_parsing")


class DocumentParsingError(Exception):
    """Base exception for document parsing errors."""

    pass


class DocumentNotFoundError(DocumentParsingError):
    """Document not found error."""

    pass


class UnsupportedFileTypeError(DocumentParsingError):
    """Unsupported file type error."""

    pass


class DocumentParsingService:
    """Service for parsing documents stored in GCS."""

    def __init__(self):
        self.logger = logger

    async def parse_document_from_gcs(
        self, org_id: str, storage_path: str, user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Parse a document from GCS storage path and return markdown content.

        Args:
            org_id: Organization ID for security isolation
            storage_path: GCS storage path (e.g., "Google/original/invoices/file.pdf")
            user_id: User ID for tracking (optional)

        Returns:
            Dictionary with parsed content, metadata, and storage info
        """
        try:
            self.logger.info(
                "Starting document parsing",
                org_id=org_id,
                storage_path=storage_path,
                user_id=user_id,
            )

            # Step 1: Validate GCS client is initialized
            if not gcs_client.is_initialized:
                raise DocumentParsingError("GCS client not initialized")

            # Step 1.5: Clean storage path - remove bucket name prefix if present
            cleaned_storage_path = self._clean_storage_path(storage_path)
            self.logger.debug(
                "Cleaned storage path",
                original_path=storage_path,
                cleaned_path=cleaned_storage_path,
            )

            # Step 2: Check if file exists in GCS
            try:
                gcs_metadata = gcs_client.get_document_metadata(cleaned_storage_path)
                self.logger.debug(
                    "Retrieved GCS metadata",
                    storage_path=cleaned_storage_path,
                    file_size=gcs_metadata.get("size"),
                )
            except GCSObjectNotFoundError:
                raise DocumentNotFoundError(
                    f"Document not found in GCS: {cleaned_storage_path}"
                )

            # Step 3: Validate file type is supported
            if not is_supported_file_type(cleaned_storage_path):
                file_ext = Path(cleaned_storage_path).suffix.lower()
                raise UnsupportedFileTypeError(
                    f"File type '{file_ext}' is not supported for parsing"
                )

            # Step 4: Download file to temporary location
            try:
                file_content = gcs_client.download_document_file(cleaned_storage_path)
                self.logger.debug(
                    "Downloaded file from GCS",
                    storage_path=storage_path,
                    content_size=len(file_content),
                )
            except GCSClientError as e:
                raise DocumentParsingError(f"Failed to download file from GCS: {e}")

            # Step 5: Create temporary file for parsing
            file_extension = Path(cleaned_storage_path).suffix.lower()
            with tempfile.NamedTemporaryFile(
                suffix=file_extension, delete=False
            ) as temp_file:
                temp_file.write(file_content)
                temp_file_path = temp_file.name

            try:
                # Step 6: Parse the document
                self.logger.info(
                    "Starting document parsing with LlamaParse",
                    temp_file_path=temp_file_path,
                    storage_path=cleaned_storage_path,
                )

                parsed_content, parsing_metadata = parse_with_metadata(temp_file_path)

                self.logger.info(
                    "Document parsing completed",
                    content_length=len(parsed_content),
                    total_pages=parsing_metadata.get("total_pages", 0),
                    storage_path=cleaned_storage_path,
                )

                # Step 7: Store parsed content in GCS (parsed folder)
                parsed_storage_path = self._generate_parsed_storage_path(
                    cleaned_storage_path
                )

                try:
                    gcs_client.upload_file_to_path(
                        storage_path=parsed_storage_path,
                        content=parsed_content.encode("utf-8"),
                        content_type="text/markdown",
                    )

                    self.logger.info(
                        "Stored parsed content in GCS",
                        original_path=cleaned_storage_path,
                        parsed_path=parsed_storage_path,
                    )
                except GCSClientError as e:
                    self.logger.warning(
                        "Failed to store parsed content in GCS",
                        error=str(e),
                        parsed_path=parsed_storage_path,
                    )
                    # Continue without failing - we still have the parsed content

                # Step 8: Update document status in Firestore (if document exists)
                try:
                    await self._update_document_status(
                        org_id=org_id,
                        storage_path=cleaned_storage_path,
                        status=DocumentStatus.PARSED,
                        parsing_metadata=parsing_metadata,
                        parsed_storage_path=parsed_storage_path,
                        file_content=parsed_content,
                    )
                except Exception as e:
                    self.logger.warning(
                        "Failed to update document status in Firestore",
                        error=str(e),
                        storage_path=cleaned_storage_path,
                    )
                    # Continue without failing - parsing was successful

                # Step 9: Prepare response
                result = {
                    "success": True,
                    "storage_path": cleaned_storage_path,
                    "parsed_storage_path": parsed_storage_path,
                    "parsed_content": parsed_content,
                    "parsing_metadata": parsing_metadata,
                    "gcs_metadata": gcs_metadata,
                    "file_info": {
                        "original_size": gcs_metadata.get("size"),
                        "parsed_size": len(parsed_content.encode("utf-8")),
                        "file_type": file_extension,
                        "content_type": gcs_metadata.get("content_type"),
                    },
                }

                self.logger.info(
                    "Document parsing workflow completed successfully",
                    org_id=org_id,
                    storage_path=cleaned_storage_path,
                    parsed_content_length=len(parsed_content),
                )

                return result

            finally:
                # Cleanup temporary file
                try:
                    os.unlink(temp_file_path)
                    self.logger.debug(
                        "Cleaned up temporary file", temp_file_path=temp_file_path
                    )
                except OSError as e:
                    self.logger.warning(
                        "Failed to cleanup temporary file",
                        temp_file_path=temp_file_path,
                        error=str(e),
                    )

        except Exception as e:
            self.logger.error(
                "Document parsing failed",
                org_id=org_id,
                storage_path=storage_path,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

    def _clean_storage_path(self, storage_path: str) -> str:
        """
        Clean storage path by removing bucket name prefix if present.

        Args:
            storage_path: Storage path that may include bucket name prefix

        Returns:
            Cleaned storage path without bucket name prefix
        """
        # Check if path starts with bucket name (from settings)
        from app.core.config import settings

        bucket_name = settings.GCS_BUCKET_NAME

        if bucket_name and storage_path.startswith(f"{bucket_name}/"):
            # Remove bucket name prefix
            cleaned_path = storage_path[len(f"{bucket_name}/") :]
            self.logger.debug(
                "Removed bucket name prefix from storage path",
                original=storage_path,
                cleaned=cleaned_path,
                bucket_name=bucket_name,
            )
            return cleaned_path

        return storage_path

    def _generate_parsed_storage_path(self, original_path: str) -> str:
        """
        Generate storage path for parsed content.

        Args:
            original_path: Original GCS path (e.g., "Google/original/invoices/file.pdf")

        Returns:
            Parsed storage path (e.g., "Google/parsed/invoices/file.md")
        """
        path_parts = original_path.split("/")

        if len(path_parts) >= 4:
            # Standard path: org_name/original/folder_name/filename
            org_name = path_parts[0]
            folder_name = path_parts[2]
            filename = path_parts[3]

            # Change extension to .md and replace 'original' with 'parsed'
            base_filename = Path(filename).stem
            parsed_filename = f"{base_filename}.md"

            return f"{org_name}/parsed/{folder_name}/{parsed_filename}"
        else:
            # Fallback for non-standard paths
            base_path = original_path.replace("/original/", "/parsed/")
            return f"{Path(base_path).with_suffix('.md')}"

    async def _update_document_status(
        self,
        org_id: str,
        storage_path: str,
        status: DocumentStatus,
        parsing_metadata: Dict[str, Any],
        parsed_storage_path: str,
        file_content: Optional[str] = None,
    ) -> None:
        """
        Update document status and content in Firestore if document exists.

        Args:
            org_id: Organization ID
            storage_path: Original storage path to find document
            status: New document status
            parsing_metadata: Metadata from parsing
            parsed_storage_path: Path where parsed content is stored
            file_content: Parsed content to sync to Firestore (optional)
        """
        try:
            if not firebase_manager.is_initialized:
                self.logger.warning("Firebase not initialized, skipping status update")
                return

            # Find document by storage_path
            collection = (
                get_collection("organizations").document(org_id).collection("documents")
            )
            query = collection.where(
                filter=FieldFilter("storage_path", "==", storage_path)
            )

            docs = query.stream()
            document_found = False

            async for doc in docs:
                document_found = True

                # Update document with parsing results
                update_data = {
                    "status": status.value,
                    "parsed_storage_path": parsed_storage_path,
                    "parsing_metadata": parsing_metadata,
                    "updated_at": firebase_manager.get_server_timestamp(),
                }

                # Include file content if provided (for Firestore-GCS synchronization)
                if file_content is not None:
                    update_data["file_content"] = file_content

                await doc.reference.update(update_data)

                self.logger.info(
                    "Updated document status in Firestore",
                    org_id=org_id,
                    document_id=doc.id,
                    status=status.value,
                    storage_path=storage_path,
                )
                break  # Should only be one document with this storage path

            if not document_found:
                self.logger.debug(
                    "No document found in Firestore for storage path",
                    org_id=org_id,
                    storage_path=storage_path,
                )

        except GoogleAPIError as e:
            self.logger.error(
                "Failed to update document status in Firestore",
                org_id=org_id,
                storage_path=storage_path,
                error=str(e),
            )
            raise

    async def get_parsed_document(
        self, org_id: str, storage_path: str
    ) -> Dict[str, Any]:
        """
        Get parsed document content if it exists.

        Args:
            org_id: Organization ID for security isolation
            storage_path: Original GCS storage path

        Returns:
            Dictionary with parsed content and metadata
        """
        try:
            # Clean storage path first
            cleaned_storage_path = self._clean_storage_path(storage_path)
            parsed_storage_path = self._generate_parsed_storage_path(
                cleaned_storage_path
            )

            # Check if parsed version exists
            try:
                parsed_metadata = gcs_client.get_document_metadata(parsed_storage_path)
                parsed_content_bytes = gcs_client.download_document_file(
                    parsed_storage_path
                )
                parsed_content = parsed_content_bytes.decode("utf-8")

                self.logger.info(
                    "Retrieved existing parsed document",
                    org_id=org_id,
                    original_path=cleaned_storage_path,
                    parsed_path=parsed_storage_path,
                )

                return {
                    "exists": True,
                    "storage_path": cleaned_storage_path,
                    "parsed_storage_path": parsed_storage_path,
                    "parsed_content": parsed_content,
                    "parsed_metadata": parsed_metadata,
                }

            except GCSObjectNotFoundError:
                return {
                    "exists": False,
                    "storage_path": cleaned_storage_path,
                    "parsed_storage_path": parsed_storage_path,
                    "message": "Parsed version does not exist",
                }

        except Exception as e:
            self.logger.error(
                "Error checking for parsed document",
                org_id=org_id,
                storage_path=storage_path,
                error=str(e),
            )
            raise DocumentParsingError(f"Failed to check parsed document: {e}")

    async def save_parsed_content_to_gcs(
        self,
        target_path: str,
        content: str,
        original_filename: str,
        metadata: Dict[str, Any],
        org_id: str,
    ) -> Dict[str, Any]:
        """
        Save parsed content directly to GCS and update Firestore document.

        Args:
            target_path: Target GCS path (e.g., "Tech Innovations Corp/parsed/control-docs")
            content: Markdown content to save
            original_filename: Original filename (e.g., "Sample2.pdf")
            metadata: Additional metadata
            org_id: Organization ID for Firestore operations

        Returns:
            Dictionary with save results and metadata
        """
        try:
            # Clean target_path to remove bucket name prefix if present
            cleaned_target_path = self._clean_storage_path(target_path)

            self.logger.info(
                "Starting save parsed content to GCS",
                target_path=target_path,
                cleaned_target_path=cleaned_target_path,
                original_filename=original_filename,
                content_size=len(content),
                org_id=org_id,
            )

            # Step 1: Validate GCS client is initialized
            if not gcs_client.is_initialized:
                raise DocumentParsingError("GCS client not initialized")

            # Step 2: Construct the markdown filename and full storage path
            base_filename = Path(original_filename).stem  # Remove original extension
            markdown_filename = f"{base_filename}.md"
            storage_path = f"{cleaned_target_path}/{markdown_filename}"

            self.logger.debug(
                "Constructed storage path",
                target_path=target_path,
                cleaned_target_path=cleaned_target_path,
                original_filename=original_filename,
                markdown_filename=markdown_filename,
                storage_path=storage_path,
            )

            # Step 3: Check if file already exists (for overwrite detection)
            file_exists = False
            try:
                existing_metadata = gcs_client.get_document_metadata(storage_path)
                file_exists = True
                self.logger.debug(
                    "File already exists in GCS", storage_path=storage_path
                )
            except GCSObjectNotFoundError:
                file_exists = False
                self.logger.debug(
                    "File does not exist in GCS, will create new",
                    storage_path=storage_path,
                )

            # Step 4: Save content to GCS
            try:
                content_bytes = content.encode("utf-8")
                gcs_url = gcs_client.upload_file_to_path(
                    storage_path=storage_path,
                    content=content_bytes,
                    content_type="text/markdown",
                )

                self.logger.info(
                    "Successfully saved parsed content to GCS",
                    storage_path=storage_path,
                    content_size=len(content_bytes),
                    gcs_url=gcs_url,
                )

            except GCSClientError as e:
                raise DocumentParsingError(f"Failed to save content to GCS: {e}")

            # Step 5: Update Firestore document if it exists
            firestore_updated = False
            try:
                if firebase_manager.is_initialized:
                    # Find document by original filename
                    collection = (
                        get_collection("organizations")
                        .document(org_id)
                        .collection("documents")
                    )
                    query = collection.where(
                        filter=FieldFilter("filename", "==", original_filename)
                    )

                    docs = query.stream()
                    document_found = False

                    async for doc in docs:
                        document_found = True

                        # Update document with new content
                        update_data = {
                            "file_content": content,
                            "parsed_storage_path": storage_path,
                            "status": DocumentStatus.PARSED.value,
                            "parsing_metadata": {
                                "source": "user_edited",
                                "content_length": len(content),
                                "updated_via": "save_parsed_endpoint",
                                **metadata,
                            },
                            "updated_at": firebase_manager.get_server_timestamp(),
                        }

                        await doc.reference.update(update_data)

                        self.logger.info(
                            "Updated document in Firestore with parsed content",
                            org_id=org_id,
                            document_id=doc.id,
                            filename=original_filename,
                            content_size=len(content),
                        )

                        firestore_updated = True
                        break  # Should only be one document with this filename

                    if not document_found:
                        self.logger.warning(
                            "No document found in Firestore for filename",
                            org_id=org_id,
                            filename=original_filename,
                        )
                else:
                    self.logger.warning(
                        "Firebase not initialized, skipping Firestore update"
                    )

            except GoogleAPIError as e:
                self.logger.error(
                    "Failed to update document in Firestore",
                    org_id=org_id,
                    filename=original_filename,
                    error=str(e),
                )
                # Continue without failing - GCS save was successful

            # Step 6: Prepare response
            from app.core.config import settings

            bucket_name = settings.GCS_BUCKET_NAME

            response = {
                "success": True,
                "gcs_path": storage_path,
                "gcs_url": f"https://storage.googleapis.com/{bucket_name}/{storage_path}",
                "target_path": cleaned_target_path,
                "final_filename": markdown_filename,
                "file_size": len(content),
                "overwritten": file_exists,
                "timestamp": datetime.now(),
                "metadata": {
                    "firestore_updated": firestore_updated,
                    "message": "Parsed content saved successfully",
                },
            }

            self.logger.info(
                "Save parsed content operation completed successfully", **response
            )

            return response

        except Exception as e:
            self.logger.error(
                "Error saving parsed content",
                target_path=target_path,
                original_filename=original_filename,
                org_id=org_id,
                error=str(e),
            )
            raise DocumentParsingError(f"Failed to save parsed content: {e}")


# Global service instance
document_parsing_service = DocumentParsingService()
