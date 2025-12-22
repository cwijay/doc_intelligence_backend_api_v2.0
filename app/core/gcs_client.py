import os
import asyncio
from typing import Optional, List, Tuple, Dict, Any
from functools import lru_cache
from datetime import datetime, timezone

from google.cloud import storage
from google.cloud.storage import Bucket
from google.auth.exceptions import DefaultCredentialsError
from google.api_core.exceptions import GoogleAPIError, NotFound

from app.core.config import settings
from app.core.logging import get_service_logger

logger = get_service_logger("gcs_client")


class GCSClientError(Exception):
    """Base exception for GCS client errors."""

    pass


class GCSBucketNotFoundError(GCSClientError):
    """Bucket not found error."""

    pass


class GCSObjectNotFoundError(GCSClientError):
    """Object not found error."""

    pass


class GCSClient:
    """Google Cloud Storage client singleton for document storage management."""

    def __init__(self):
        self.logger = logger
        self._client: Optional[storage.Client] = None
        self._bucket: Optional[Bucket] = None
        self._bucket_name = settings.GCS_BUCKET_NAME
        self._initialized = False
        self._initialization_error: Optional[str] = None

        # Only initialize if required settings are provided
        if self._should_initialize():
            try:
                self._initialize_client()
            except Exception as e:
                self.logger.warning(
                    "GCS client initialization failed, will operate in disabled mode",
                    error=str(e),
                )
                self._initialization_error = str(e)

    def _should_initialize(self) -> bool:
        """Check if GCS client should be initialized based on available settings."""
        # Check if we have the minimum required configuration
        has_credentials = (
            settings.GOOGLE_APPLICATION_CREDENTIALS
            or
            # Check if default credentials are available in environment
            os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
            or os.environ.get("GCLOUD_SERVICE_ACCOUNT_JSON")
            or
            # Check if Application Default Credentials are available
            self._check_application_default_credentials()
        )

        has_project = settings.GCP_PROJECT_ID

        return has_credentials and has_project

    def _check_application_default_credentials(self) -> bool:
        """Check if Application Default Credentials are available."""
        try:
            import google.auth

            credentials, project = google.auth.default()
            return credentials is not None
        except Exception:
            return False

    def _initialize_client(self) -> None:
        """Initialize GCS client and bucket."""
        try:
            # Initialize the storage client
            if settings.GOOGLE_APPLICATION_CREDENTIALS:
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = (
                    settings.GOOGLE_APPLICATION_CREDENTIALS
                )

            project_id = settings.GCP_PROJECT_ID
            self._client = storage.Client(project=project_id)

            # Get or create bucket
            try:
                self._bucket = self._client.bucket(self._bucket_name)
                # Test bucket access by checking if it exists
                self._bucket.reload()
                self._initialized = True
                self.logger.info("Connected to GCS bucket", bucket=self._bucket_name)
            except NotFound:
                self.logger.error("GCS bucket not found", bucket=self._bucket_name)
                raise GCSBucketNotFoundError(f"Bucket '{self._bucket_name}' not found")

        except DefaultCredentialsError as e:
            self.logger.error("GCS authentication failed", error=str(e))
            raise GCSClientError(f"GCS authentication failed: {e}")
        except Exception as e:
            self.logger.error("Failed to initialize GCS client", error=str(e))
            raise GCSClientError(f"Failed to initialize GCS client: {e}")

    @property
    def is_initialized(self) -> bool:
        """Check if GCS client is properly initialized."""
        return self._initialized

    @property
    def initialization_error(self) -> Optional[str]:
        """Get initialization error if any."""
        return self._initialization_error

    @property
    def client(self) -> storage.Client:
        """Get the GCS client instance."""
        if not self._initialized:
            raise GCSClientError("GCS client is not initialized. Check configuration.")
        return self._client

    @property
    def bucket(self) -> Bucket:
        """Get the GCS bucket instance."""
        if not self._initialized:
            raise GCSClientError("GCS client is not initialized. Check configuration.")
        return self._bucket

    def _ensure_initialized(self) -> None:
        """Ensure GCS client is initialized, raise error if not."""
        if not self._initialized:
            error_msg = "GCS client is not initialized"
            if self._initialization_error:
                error_msg += f": {self._initialization_error}"
            else:
                error_msg += ". Please configure GCP_PROJECT_ID, GCS_BUCKET_NAME, and authentication credentials."
            raise GCSClientError(error_msg)

    def create_folder_structure(
        self, org_name: str, folder_path: str
    ) -> Dict[str, bool]:
        """
        Create folder structure in GCS for document types.
        Note: No placeholder file is created for 'original' folder type.

        Args:
            org_name: Organization name
            folder_path: Folder path (e.g., "folder1/subfolder")

        Returns:
            Dict with success status for each folder type
        """
        self._ensure_initialized()
        try:
            folder_types = ["original", "parsed", "bm-25"]
            results = {}

            for folder_type in folder_types:
                gcs_path = f"{org_name}/{folder_type}/{folder_path}/"

                if folder_type == "original":
                    # For original folder, create a .keep file to establish folder structure
                    blob_name = f"{gcs_path}.keep"
                    blob = self.bucket.blob(blob_name)

                    # Upload empty content to create the folder structure
                    blob.upload_from_string("", content_type="text/plain")

                    results[folder_type] = True
                    self.logger.debug(
                        "Created GCS original folder with .keep file",
                        org_name=org_name,
                        folder_type=folder_type,
                        path=gcs_path,
                    )
                else:
                    # Create a placeholder object for parsed and bm-25 folders
                    blob_name = f"{gcs_path}.folder_placeholder"
                    blob = self.bucket.blob(blob_name)

                    # Upload empty content to create the folder structure
                    blob.upload_from_string("", content_type="text/plain")

                    results[folder_type] = True
                    self.logger.debug(
                        "Created GCS folder",
                        org_name=org_name,
                        folder_type=folder_type,
                        path=gcs_path,
                    )

            return results

        except GoogleAPIError as e:
            self.logger.error(
                "Failed to create folder structure in GCS",
                org_name=org_name,
                folder_path=folder_path,
                error=str(e),
            )
            raise GCSClientError(f"Failed to create folder structure: {e}")

    def delete_folder_structure(
        self, org_name: str, folder_path: str
    ) -> Dict[str, bool]:
        """
        Delete folder structure and all contents from GCS.

        Args:
            org_name: Organization name
            folder_path: Folder path to delete

        Returns:
            Dict with deletion status for each folder type
        """
        self._ensure_initialized()
        try:
            folder_types = ["original", "parsed", "bm-25"]
            results = {}

            for folder_type in folder_types:
                gcs_prefix = f"{org_name}/{folder_type}/{folder_path}/"

                # Use iterator pattern to avoid loading all blobs into memory
                # Process blobs as we iterate - GCS iterator handles pagination internally
                deleted_count = 0
                for blob in self.bucket.list_blobs(prefix=gcs_prefix):
                    blob.delete()
                    deleted_count += 1

                results[folder_type] = True
                self.logger.info(
                    "Deleted GCS folder",
                    org_name=org_name,
                    folder_type=folder_type,
                    path=gcs_prefix,
                    deleted_objects=deleted_count,
                )

            return results

        except GoogleAPIError as e:
            self.logger.error(
                "Failed to delete folder structure from GCS",
                org_name=org_name,
                folder_path=folder_path,
                error=str(e),
            )
            raise GCSClientError(f"Failed to delete folder structure: {e}")

    def move_folder_structure(
        self, org_name: str, old_path: str, new_path: str
    ) -> Dict[str, bool]:
        """
        Move folder structure in GCS by copying and deleting original.

        Args:
            org_name: Organization name
            old_path: Current folder path
            new_path: New folder path

        Returns:
            Dict with move status for each folder type
        """
        self._ensure_initialized()
        try:
            folder_types = ["original", "parsed", "bm-25"]
            results = {}

            for folder_type in folder_types:
                old_prefix = f"{org_name}/{folder_type}/{old_path}/"
                new_prefix = f"{org_name}/{folder_type}/{new_path}/"

                # Use iterator pattern to avoid loading all blobs into memory
                # Note: For move operations, we need to be careful as we're modifying
                # while iterating. GCS list_blobs returns a snapshot-consistent iterator.
                moved_count = 0
                for blob in self.bucket.list_blobs(prefix=old_prefix):
                    # Calculate new blob name
                    old_name = blob.name
                    new_name = old_name.replace(old_prefix, new_prefix, 1)

                    # Copy to new location
                    new_blob = self.bucket.copy_blob(blob, self.bucket, new_name)

                    # Delete original
                    blob.delete()
                    moved_count += 1

                results[folder_type] = True
                self.logger.info(
                    "Moved GCS folder",
                    org_name=org_name,
                    folder_type=folder_type,
                    old_path=old_prefix,
                    new_path=new_prefix,
                    moved_objects=moved_count,
                )

            return results

        except GoogleAPIError as e:
            self.logger.error(
                "Failed to move folder structure in GCS",
                org_name=org_name,
                old_path=old_path,
                new_path=new_path,
                error=str(e),
            )
            raise GCSClientError(f"Failed to move folder structure: {e}")

    # Async versions of folder structure methods for use in async contexts
    async def create_folder_structure_async(
        self, org_name: str, folder_path: str
    ) -> Dict[str, bool]:
        """Async version of create_folder_structure using thread pool."""
        return await asyncio.to_thread(
            self.create_folder_structure, org_name, folder_path
        )

    async def delete_folder_structure_async(
        self, org_name: str, folder_path: str
    ) -> Dict[str, bool]:
        """Async version of delete_folder_structure using thread pool."""
        return await asyncio.to_thread(
            self.delete_folder_structure, org_name, folder_path
        )

    async def move_folder_structure_async(
        self, org_name: str, old_path: str, new_path: str
    ) -> Dict[str, bool]:
        """Async version of move_folder_structure using thread pool."""
        return await asyncio.to_thread(
            self.move_folder_structure, org_name, old_path, new_path
        )

    def upload_document_file(
        self,
        org_name: str,
        folder_name: Optional[str],
        document_id: str,
        filename: str,
        content: bytes,
        content_type: Optional[str] = None,
    ) -> str:
        """
        Upload document file to GCS in the original folder structure.

        Args:
            org_name: Organization name
            folder_name: Folder name (None for root)
            document_id: Unique document identifier
            filename: Document filename
            content: File content as bytes
            content_type: MIME content type

        Returns:
            GCS object path
        """
        self._ensure_initialized()
        try:
            # Build storage path: org_name/folder_name/document_id_filename
            if folder_name:
                gcs_path = f"{org_name}/{folder_name}/{document_id}_{filename}"
            else:
                gcs_path = f"{org_name}/root/{document_id}_{filename}"

            blob = self.bucket.blob(gcs_path)

            # Set content type if provided
            if content_type:
                blob.content_type = content_type

            # Upload the file
            blob.upload_from_string(content)

            self.logger.info(
                "Uploaded document file to GCS",
                org_name=org_name,
                folder_name=folder_name,
                document_id=document_id,
                filename=filename,
                gcs_path=gcs_path,
                size=len(content),
            )

            return gcs_path

        except GoogleAPIError as e:
            self.logger.error(
                "Failed to upload document file to GCS",
                org_name=org_name,
                folder_name=folder_name,
                document_id=document_id,
                filename=filename,
                error=str(e),
            )
            raise GCSClientError(f"Failed to upload document file: {e}")

    def download_document_file(self, storage_path: str) -> bytes:
        """
        Download document file from GCS.

        Args:
            storage_path: GCS storage path

        Returns:
            File content as bytes
        """
        self._ensure_initialized()
        try:
            blob = self.bucket.blob(storage_path)

            if not blob.exists():
                raise GCSObjectNotFoundError(f"Document file not found: {storage_path}")

            content = blob.download_as_bytes()

            self.logger.info(
                "Downloaded document file from GCS",
                storage_path=storage_path,
                size=len(content),
            )

            return content

        except GoogleAPIError as e:
            self.logger.error(
                "Failed to download document file from GCS",
                storage_path=storage_path,
                error=str(e),
            )
            raise GCSClientError(f"Failed to download document file: {e}")

    def delete_document_file(self, storage_path: str) -> bool:
        """
        Delete document file from GCS.

        Args:
            storage_path: GCS storage path

        Returns:
            True if deleted successfully
        """
        self._ensure_initialized()
        try:
            blob = self.bucket.blob(storage_path)

            if not blob.exists():
                self.logger.warning(
                    "Document file not found for deletion", storage_path=storage_path
                )
                return False

            blob.delete()

            self.logger.info(
                "Deleted document file from GCS", storage_path=storage_path
            )

            return True

        except GoogleAPIError as e:
            self.logger.error(
                "Failed to delete document file from GCS",
                storage_path=storage_path,
                error=str(e),
            )
            raise GCSClientError(f"Failed to delete document file: {e}")

    def generate_signed_url(
        self, storage_path: str, expiration_minutes: int = 60
    ) -> Tuple[str, datetime]:
        """
        Generate a signed URL for document download.

        Args:
            storage_path: GCS storage path
            expiration_minutes: URL expiration time in minutes

        Returns:
            Tuple of (signed_url, expiration_datetime)
        """
        self._ensure_initialized()
        try:
            from datetime import timedelta

            blob = self.bucket.blob(storage_path)

            if not blob.exists():
                raise GCSObjectNotFoundError(f"Document file not found: {storage_path}")

            # Calculate expiration
            expiration = datetime.now(timezone.utc) + timedelta(
                minutes=expiration_minutes
            )

            # Generate signed URL
            signed_url = blob.generate_signed_url(
                expiration=expiration, method="GET", version="v4"
            )

            self.logger.info(
                "Generated signed URL for document",
                storage_path=storage_path,
                expiration=expiration.isoformat(),
            )

            return signed_url, expiration

        except GoogleAPIError as e:
            self.logger.error(
                "Failed to generate signed URL", storage_path=storage_path, error=str(e)
            )
            raise GCSClientError(f"Failed to generate signed URL: {e}")

    def get_document_metadata(self, storage_path: str) -> Dict[str, Any]:
        """
        Get metadata for a document file in GCS.

        Args:
            storage_path: GCS storage path

        Returns:
            Dictionary with file metadata
        """
        self._ensure_initialized()
        try:
            blob = self.bucket.blob(storage_path)

            if not blob.exists():
                raise GCSObjectNotFoundError(f"Document file not found: {storage_path}")

            # Reload to get latest metadata
            blob.reload()

            metadata = {
                "name": blob.name,
                "size": blob.size,
                "content_type": blob.content_type,
                "created": blob.time_created.isoformat() if blob.time_created else None,
                "updated": blob.updated.isoformat() if blob.updated else None,
                "md5_hash": blob.md5_hash,
                "etag": blob.etag,
                "storage_class": blob.storage_class,
                "custom_metadata": blob.metadata or {},
            }

            self.logger.debug(
                "Retrieved document metadata from GCS",
                storage_path=storage_path,
                size=metadata["size"],
            )

            return metadata

        except GoogleAPIError as e:
            self.logger.error(
                "Failed to get document metadata from GCS",
                storage_path=storage_path,
                error=str(e),
            )
            raise GCSClientError(f"Failed to get document metadata: {e}")

    def list_documents_in_folder(
        self, org_name: str, folder_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List all documents in a specific folder.

        Args:
            org_name: Organization name
            folder_name: Folder name (None for root folder)

        Returns:
            List of document metadata dictionaries
        """
        self._ensure_initialized()
        try:
            # Build prefix for folder
            if folder_name:
                prefix = f"{org_name}/{folder_name}/"
            else:
                prefix = f"{org_name}/root/"

            blobs = self.bucket.list_blobs(prefix=prefix)
            documents = []

            for blob in blobs:
                # Skip folder placeholders and other non-document files
                if blob.name.endswith((".keep", ".folder_placeholder")):
                    continue

                # Extract document info from filename
                filename = blob.name.replace(prefix, "")
                if "_" in filename:
                    # Format is document_id_original_filename
                    parts = filename.split("_", 1)
                    if len(parts) == 2:
                        document_id, original_filename = parts
                    else:
                        document_id = parts[0]
                        original_filename = filename
                else:
                    document_id = None
                    original_filename = filename

                document_info = {
                    "storage_path": blob.name,
                    "filename": filename,
                    "original_filename": original_filename,
                    "document_id": document_id,
                    "size": blob.size,
                    "content_type": blob.content_type,
                    "created": (
                        blob.time_created.isoformat() if blob.time_created else None
                    ),
                    "updated": blob.updated.isoformat() if blob.updated else None,
                }
                documents.append(document_info)

            self.logger.debug(
                "Listed documents in folder",
                org_name=org_name,
                folder_name=folder_name,
                count=len(documents),
            )

            return documents

        except GoogleAPIError as e:
            self.logger.error(
                "Failed to list documents in folder",
                org_name=org_name,
                folder_name=folder_name,
                error=str(e),
            )
            raise GCSClientError(f"Failed to list documents: {e}")

    def upload_file(
        self,
        org_name: str,
        folder_path: str,
        file_name: str,
        content: bytes,
        file_type: str = "original",
        content_type: Optional[str] = None,
    ) -> str:
        """
        Upload file to GCS in specified folder structure.

        Args:
            org_name: Organization name
            folder_path: Folder path
            file_name: Name of the file
            content: File content as bytes
            file_type: Type of file ("original", "parsed", "bm-25")
            content_type: MIME content type (optional)

        Returns:
            GCS object path
        """
        self._ensure_initialized()
        try:
            gcs_path = f"{org_name}/{file_type}/{folder_path}/{file_name}"
            blob = self.bucket.blob(gcs_path)

            # Upload the file with proper content type
            blob.upload_from_string(content, content_type=content_type)

            self.logger.info(
                "Uploaded file to GCS",
                org_name=org_name,
                file_type=file_type,
                folder_path=folder_path,
                file_name=file_name,
                gcs_path=gcs_path,
            )

            return gcs_path

        except GoogleAPIError as e:
            self.logger.error(
                "Failed to upload file to GCS",
                org_name=org_name,
                folder_path=folder_path,
                file_name=file_name,
                error=str(e),
            )
            raise GCSClientError(f"Failed to upload file: {e}")

    def upload_file_to_path(
        self, storage_path: str, content: bytes, content_type: Optional[str] = None
    ) -> str:
        """
        Upload file to GCS using a custom storage path.

        Args:
            storage_path: Complete GCS storage path
            content: File content as bytes
            content_type: MIME content type (optional)

        Returns:
            GCS object path (same as input storage_path)
        """
        self._ensure_initialized()
        try:
            blob = self.bucket.blob(storage_path)

            # Upload the file with proper content type
            blob.upload_from_string(content, content_type=content_type)

            self.logger.info(
                "Uploaded file to custom GCS path",
                storage_path=storage_path,
                content_type=content_type,
                size=len(content),
            )

            return storage_path

        except GoogleAPIError as e:
            self.logger.error(
                "Failed to upload file to custom GCS path",
                storage_path=storage_path,
                error=str(e),
            )
            raise GCSClientError(f"Failed to upload file to custom path: {e}")

    def list_folder_contents(
        self, org_name: str, folder_path: str, file_type: str = "original"
    ) -> List[str]:
        """
        List contents of a folder in GCS.

        Args:
            org_name: Organization name
            folder_path: Folder path
            file_type: Type of files to list

        Returns:
            List of file names in the folder
        """
        self._ensure_initialized()
        try:
            prefix = f"{org_name}/{file_type}/{folder_path}/"
            blobs = self.bucket.list_blobs(prefix=prefix, delimiter="/")

            # Extract file names (remove prefix and path)
            file_names = []
            for blob in blobs:
                if not blob.name.endswith(".folder_placeholder"):
                    file_name = blob.name.replace(prefix, "")
                    if file_name:  # Skip empty names
                        file_names.append(file_name)

            return file_names

        except GoogleAPIError as e:
            self.logger.error(
                "Failed to list folder contents",
                org_name=org_name,
                folder_path=folder_path,
                file_type=file_type,
                error=str(e),
            )
            raise GCSClientError(f"Failed to list folder contents: {e}")

    def list_files_in_path(self, folder_path: str) -> List[Dict[str, Any]]:
        """
        List files in a specific GCS path, returning detailed metadata.

        Args:
            folder_path: Full GCS folder path (e.g., "Tech Innovations Corp/original/control-docs")

        Returns:
            List of file metadata dictionaries with name, size, updated, etc.
        """
        self._ensure_initialized()
        try:
            # Ensure the path ends with a slash for proper prefix matching
            prefix = folder_path.rstrip("/") + "/"
            blobs = self.bucket.list_blobs(prefix=prefix, delimiter="/")

            files = []
            for blob in blobs:
                # Skip folder placeholders, .keep files, and directories
                if not blob.name.endswith(
                    (".folder_placeholder", ".keep")
                ) and not blob.name.endswith("/"):
                    # Get relative filename from the path
                    filename = blob.name.replace(prefix, "")
                    if filename:  # Skip empty names
                        file_metadata = {
                            "name": filename,
                            "storage_path": blob.name,
                            "size": blob.size,
                            "updated": (
                                blob.updated.isoformat() if blob.updated else None
                            ),
                            "content_type": blob.content_type,
                            "md5_hash": blob.md5_hash,
                        }
                        files.append(file_metadata)

            self.logger.debug(
                "Listed files in GCS path",
                folder_path=folder_path,
                file_count=len(files),
            )

            return files

        except GoogleAPIError as e:
            self.logger.error(
                "Failed to list files in path", folder_path=folder_path, error=str(e)
            )
            raise GCSClientError(f"Failed to list files in path: {e}")

    def health_check(self) -> bool:
        """
        Check if GCS client and bucket are accessible.

        Returns:
            True if healthy, False otherwise
        """
        if not self._initialized:
            return False

        try:
            # Try to access bucket metadata
            self.bucket.reload()
            return True
        except Exception as e:
            self.logger.error("GCS health check failed", error=str(e))
            return False


@lru_cache()
def get_gcs_client() -> GCSClient:
    """Get singleton GCS client instance."""
    return GCSClient()


# Global client instance
gcs_client = get_gcs_client()
