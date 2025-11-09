"""
Document Sync Service - Firestore-GCS content synchronization operations.

This service handles bi-directional content synchronization between Firestore and GCS:
- Sync content from GCS to Firestore for search and retrieval
- Sync content from Firestore to GCS for backup and processing
- Validate content synchronization and consistency
- Comprehensive sync validation and reporting
- Parsed content path generation and management
"""

from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
from google.cloud.firestore_v1 import FieldFilter

from app.models.document import Document
from app.core.firebase_client import firebase_manager
from app.core.gcs_client import gcs_client, GCSClientError
from .document_base_service import (
    DocumentBaseService, DocumentNotFoundError, DocumentUploadError
)


class DocumentSyncService(DocumentBaseService):
    """Service for Firestore-GCS content synchronization."""
    
    def __init__(self):
        """Initialize the sync service."""
        super().__init__()
        
        # Sync operation limits
        self.max_content_size = 10 * 1024 * 1024  # 10MB max content size
        self.max_sync_retries = 3
        self.sync_timeout_seconds = 60

    async def sync_content_to_firestore(
        self, 
        org_id: str, 
        document_id: str, 
        content: str,
        user_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Sync document content from GCS to Firestore with comprehensive validation.
        
        Args:
            org_id: Organization ID
            document_id: Document ID in Firestore
            content: Content to sync to Firestore
            user_id: User performing the sync operation
            metadata: Optional metadata to update alongside content
            
        Returns:
            Dictionary with sync result information
            
        Raises:
            DocumentNotFoundError: If document not found in Firestore
            DocumentUploadError: If sync operation fails
        """
        try:
            if not firebase_manager.is_initialized:
                error_msg = "Firebase not initialized, cannot sync content to Firestore"
                self.logger.warning(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "document_updated": False
                }
            
            # Validate content size
            content_size = len(content.encode('utf-8'))
            if content_size > self.max_content_size:
                max_mb = self.max_content_size // (1024 * 1024)
                error_msg = f"Content too large: {content_size} bytes (max {max_mb}MB)"
                raise DocumentUploadError(error_msg)
            
            # Validate content is not empty
            if not content or not content.strip():
                raise DocumentUploadError("Content cannot be empty")
            
            # Get document from Firestore
            doc_ref = self._get_collection(org_id).document(document_id)
            doc = await doc_ref.get()
            
            if not doc.exists:
                raise DocumentNotFoundError(f"Document with ID {document_id} not found")
            
            doc_data = doc.to_dict()
            document = Document.from_dict(doc_data, doc.id)
            
            if not document.is_active:
                raise DocumentNotFoundError(f"Document with ID {document_id} not found")
            
            # Prepare update data
            update_data = {
                "file_content": content.strip(),
                "content_synced_at": datetime.utcnow(),
                "content_synced_by": user_id,
                "updated_at": datetime.utcnow()
            }
            
            # Include metadata if provided (merge with existing)
            if metadata:
                existing_metadata = doc_data.get("metadata", {})
                merged_metadata = {**existing_metadata, **metadata}
                update_data["metadata"] = merged_metadata
            
            # Update document in Firestore
            await doc_ref.update(update_data)
            
            self.logger.info("Synced content to Firestore document", 
                           org_id=org_id,
                           document_id=document_id,
                           filename=document.filename,
                           content_length=content_size,
                           synced_by=user_id,
                           has_metadata_updates=bool(metadata))
            
            return {
                "success": True,
                "document_updated": True,
                "document_id": document_id,
                "content_length": content_size,
                "synced_at": update_data["content_synced_at"],
                "synced_by": user_id
            }
            
        except (DocumentNotFoundError, DocumentUploadError):
            raise
        except Exception as e:
            self.logger.error("Failed to sync content to Firestore", 
                            org_id=org_id,
                            document_id=document_id,
                            content_length=len(content.encode('utf-8')) if content else 0,
                            user_id=user_id,
                            error=str(e))
            return {
                "success": False,
                "error": str(e),
                "document_updated": False
            }

    async def sync_content_from_firestore_to_gcs(
        self, 
        org_id: str, 
        document_id: str,
        user_id: str,
        gcs_storage_path: Optional[str] = None,
        storage_service=None
    ) -> Dict[str, Any]:
        """
        Sync document content from Firestore to GCS with path generation.
        
        Args:
            org_id: Organization ID
            document_id: Document ID in Firestore
            user_id: User performing the sync operation
            gcs_storage_path: Optional GCS path override
            storage_service: Storage service dependency for path generation
            
        Returns:
            Dictionary with sync result information
            
        Raises:
            DocumentNotFoundError: If document not found
            DocumentUploadError: If sync operation fails
        """
        try:
            # Get document from Firestore
            doc_ref = self._get_collection(org_id).document(document_id)
            doc = await doc_ref.get()
            
            if not doc.exists:
                raise DocumentNotFoundError(f"Document with ID {document_id} not found")
            
            doc_data = doc.to_dict()
            document = Document.from_dict(doc_data, doc.id)
            
            if not document.is_active:
                raise DocumentNotFoundError(f"Document with ID {document_id} not found")
            
            file_content = doc_data.get("file_content")
            
            if not file_content:
                return {
                    "success": False,
                    "error": "Document has no file_content to sync",
                    "gcs_updated": False
                }
            
            # Validate content size
            content_size = len(file_content.encode('utf-8'))
            if content_size > self.max_content_size:
                max_mb = self.max_content_size // (1024 * 1024)
                error_msg = f"Content too large: {content_size} bytes (max {max_mb}MB)"
                raise DocumentUploadError(error_msg)
            
            # Determine storage path
            if not gcs_storage_path:
                gcs_storage_path = doc_data.get("parsed_storage_path")
                if not gcs_storage_path:
                    # Generate parsed storage path from original
                    original_path = doc_data.get("storage_path")
                    if original_path:
                        if storage_service:
                            gcs_storage_path = storage_service._generate_parsed_storage_path(original_path)
                        else:
                            gcs_storage_path = self._generate_parsed_storage_path(original_path)
                    else:
                        return {
                            "success": False,
                            "error": "Cannot determine GCS storage path",
                            "gcs_updated": False
                        }
            
            # Ensure GCS is available
            if not gcs_client.is_initialized:
                error_msg = "GCS client not initialized"
                if gcs_client.initialization_error:
                    error_msg += f": {gcs_client.initialization_error}"
                raise DocumentUploadError(error_msg)
            
            # Upload content to GCS with retry logic
            retry_count = 0
            last_error = None
            
            while retry_count < self.max_sync_retries:
                try:
                    content_bytes = file_content.encode('utf-8')
                    gcs_client.upload_file_to_path(
                        storage_path=gcs_storage_path,
                        content=content_bytes,
                        content_type="text/markdown"
                    )
                    
                    # Update Firestore with the parsed_storage_path if it wasn't set
                    update_data = {}
                    if not doc_data.get("parsed_storage_path"):
                        update_data["parsed_storage_path"] = gcs_storage_path
                    
                    update_data.update({
                        "gcs_synced_at": datetime.utcnow(),
                        "gcs_synced_by": user_id,
                        "updated_at": datetime.utcnow()
                    })
                    
                    await doc_ref.update(update_data)
                    
                    self.logger.info("Synced content from Firestore to GCS", 
                                   org_id=org_id,
                                   document_id=document_id,
                                   filename=document.filename,
                                   gcs_storage_path=gcs_storage_path,
                                   content_length=len(content_bytes),
                                   synced_by=user_id,
                                   retry_attempt=retry_count)
                    
                    return {
                        "success": True,
                        "gcs_updated": True,
                        "gcs_storage_path": gcs_storage_path,
                        "content_length": len(content_bytes),
                        "synced_at": update_data["gcs_synced_at"],
                        "synced_by": user_id,
                        "retry_attempts": retry_count
                    }
                    
                except GCSClientError as e:
                    retry_count += 1
                    last_error = e
                    self.logger.warning("GCS sync attempt failed, retrying", 
                                      org_id=org_id,
                                      document_id=document_id,
                                      gcs_storage_path=gcs_storage_path,
                                      retry_attempt=retry_count,
                                      max_retries=self.max_sync_retries,
                                      error=str(e))
                    
                    if retry_count >= self.max_sync_retries:
                        break
            
            # All retries failed
            error_msg = f"GCS sync failed after {self.max_sync_retries} attempts: {str(last_error)}"
            self.logger.error("Failed to sync content to GCS after retries", 
                            org_id=org_id,
                            document_id=document_id,
                            gcs_storage_path=gcs_storage_path,
                            retry_attempts=retry_count,
                            final_error=str(last_error))
            
            return {
                "success": False,
                "error": error_msg,
                "gcs_updated": False,
                "retry_attempts": retry_count
            }
            
        except (DocumentNotFoundError, DocumentUploadError):
            raise
        except Exception as e:
            self.logger.error("Failed to sync content from Firestore to GCS", 
                            org_id=org_id,
                            document_id=document_id,
                            user_id=user_id,
                            error=str(e))
            return {
                "success": False,
                "error": str(e),
                "gcs_updated": False
            }

    def _generate_parsed_storage_path(self, original_path: str) -> str:
        """
        Generate storage path for parsed content from original path.
        
        Args:
            original_path: Original GCS path (e.g., "Google/original/invoices/file.pdf")
            
        Returns:
            Parsed storage path (e.g., "Google/parsed/invoices/file.md")
        """
        path_parts = original_path.split('/')
        
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
            base_path = original_path.replace('/original/', '/parsed/')
            return str(Path(base_path).with_suffix('.md'))

    async def validate_sync(self, org_id: str, folder_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Comprehensive validation of sync status across documents.
        
        Args:
            org_id: Organization ID
            folder_id: Optional folder ID to limit validation scope
            
        Returns:
            Dictionary with comprehensive sync validation results
        """
        try:
            # Get documents to validate
            collection = self._get_collection(org_id)
            query = collection.where(filter=FieldFilter("is_active", "==", True))
            
            if folder_id:
                query = query.where(filter=FieldFilter("folder_id", "==", folder_id))
            
            docs = query.stream()
            
            validation_results = {
                "org_id": org_id,
                "folder_id": folder_id,
                "validation_timestamp": datetime.utcnow(),
                "total_documents": 0,
                "documents_with_content": 0,
                "documents_synchronized": 0,
                "documents_out_of_sync": 0,
                "documents_with_errors": 0,
                "sync_issues": [],
                "recommendations": [],
                "summary": "unknown"
            }
            
            async for doc in docs:
                try:
                    validation_results["total_documents"] += 1
                    
                    doc_data = doc.to_dict()
                    document_id = doc.id
                    filename = doc_data.get("filename", "unknown")
                    
                    # Check if document has content
                    firestore_content = doc_data.get("file_content")
                    parsed_storage_path = doc_data.get("parsed_storage_path")
                    
                    if not firestore_content and not parsed_storage_path:
                        # No content in either location - this is normal for unparsed documents
                        continue
                    
                    validation_results["documents_with_content"] += 1
                    
                    # Validate content sync using storage service method
                    doc_sync_result = await self.validate_content_sync(
                        org_id, document_id=document_id
                    )
                    
                    if doc_sync_result.get("valid") and doc_sync_result.get("synchronized"):
                        validation_results["documents_synchronized"] += 1
                    elif doc_sync_result.get("valid") and not doc_sync_result.get("synchronized"):
                        validation_results["documents_out_of_sync"] += 1
                        validation_results["sync_issues"].append({
                            "document_id": document_id,
                            "filename": filename,
                            "issue_type": "out_of_sync",
                            "description": doc_sync_result.get("note", "Content differs between stores"),
                            "firestore_content_length": doc_sync_result.get("firestore_content_length", 0),
                            "gcs_content_length": doc_sync_result.get("gcs_content_length", 0)
                        })
                    else:
                        validation_results["documents_with_errors"] += 1
                        validation_results["sync_issues"].append({
                            "document_id": document_id,
                            "filename": filename,
                            "issue_type": "validation_error",
                            "description": doc_sync_result.get("error", "Unknown validation error")
                        })
                
                except Exception as e:
                    validation_results["documents_with_errors"] += 1
                    validation_results["sync_issues"].append({
                        "document_id": getattr(doc, 'id', 'unknown'),
                        "filename": "unknown",
                        "issue_type": "processing_error",
                        "description": f"Error processing document: {e}"
                    })
                    
                    self.logger.error("Error validating document sync", 
                                    org_id=org_id,
                                    document_id=getattr(doc, 'id', 'unknown'),
                                    error=str(e))
            
            # Generate recommendations
            if validation_results["documents_out_of_sync"] > 0:
                validation_results["recommendations"].append(
                    f"Resync {validation_results['documents_out_of_sync']} out-of-sync documents"
                )
            
            if validation_results["documents_with_errors"] > 0:
                validation_results["recommendations"].append(
                    f"Investigate {validation_results['documents_with_errors']} documents with validation errors"
                )
            
            if validation_results["documents_synchronized"] == validation_results["documents_with_content"]:
                validation_results["summary"] = "all_synchronized"
            elif validation_results["documents_with_errors"] > 0:
                validation_results["summary"] = "has_errors"
            elif validation_results["documents_out_of_sync"] > 0:
                validation_results["summary"] = "partially_synchronized"
            else:
                validation_results["summary"] = "no_content_to_sync"
            
            self.logger.info("Sync validation completed", 
                           org_id=org_id,
                           folder_id=folder_id,
                           total_documents=validation_results["total_documents"],
                           synchronized=validation_results["documents_synchronized"],
                           out_of_sync=validation_results["documents_out_of_sync"],
                           errors=validation_results["documents_with_errors"],
                           summary=validation_results["summary"])
            
            return validation_results
            
        except Exception as e:
            self.logger.error("Error validating sync status", 
                            org_id=org_id,
                            folder_id=folder_id,
                            error=str(e))
            return {
                "org_id": org_id,
                "folder_id": folder_id,
                "validation_timestamp": datetime.utcnow(),
                "success": False,
                "error": str(e),
                "issues": [{
                    "type": "validation_error",
                    "description": f"Sync validation failed: {e}"
                }],
                "recommendations": ["Fix the underlying error and retry validation"],
                "summary": "validation_failed"
            }

    async def validate_content_sync(
        self, 
        org_id: str, 
        document_id: Optional[str] = None,
        storage_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validate synchronization between Firestore content and GCS content for a specific document.
        
        This method is delegated to the storage service for consistency with existing implementation.
        
        Args:
            org_id: Organization ID
            document_id: Document ID (optional, used if storage_path not provided)
            storage_path: Storage path to validate (optional, used if document_id not provided)
            
        Returns:
            Dictionary with validation results
        """
        try:
            # Get document data
            if document_id:
                doc_ref = self._get_collection(org_id).document(document_id)
                doc = await doc_ref.get()
                if not doc.exists:
                    return {"valid": False, "error": "Document not found in Firestore"}
                doc_data = doc.to_dict()
                storage_path = doc_data.get("storage_path")
            elif storage_path:
                # Find document by storage path
                collection = self._get_collection(org_id)
                query = collection.where(filter=FieldFilter("storage_path", "==", storage_path))
                docs = query.stream()
                
                doc_data = None
                async for doc in docs:
                    doc_data = doc.to_dict()
                    document_id = doc.id
                    break
                
                if not doc_data:
                    return {"valid": False, "error": "Document not found in Firestore"}
            else:
                return {"valid": False, "error": "Either document_id or storage_path must be provided"}
            
            # Get content from both sources
            firestore_content = doc_data.get("file_content")
            parsed_storage_path = doc_data.get("parsed_storage_path")
            
            if not parsed_storage_path:
                if not firestore_content:
                    return {
                        "valid": True,
                        "synchronized": True,
                        "note": "No content in either location (expected for unparsed documents)"
                    }
                else:
                    return {
                        "valid": False,
                        "synchronized": False,
                        "error": "Content exists in Firestore but no parsed_storage_path"
                    }
            
            # Check GCS content
            try:
                gcs_content_bytes = gcs_client.download_document_file(parsed_storage_path)
                gcs_content = gcs_content_bytes.decode('utf-8')
            except Exception as e:
                if firestore_content:
                    return {
                        "valid": False,
                        "synchronized": False,
                        "error": f"Content exists in Firestore but GCS file not accessible: {e}",
                        "firestore_content_length": len(firestore_content),
                        "parsed_storage_path": parsed_storage_path
                    }
                else:
                    return {
                        "valid": True,
                        "synchronized": True,
                        "note": "No content in either location"
                    }
            
            # Compare content
            if not firestore_content:
                if gcs_content:
                    return {
                        "valid": False,
                        "synchronized": False,
                        "error": "Content exists in GCS but not in Firestore",
                        "gcs_content_length": len(gcs_content),
                        "parsed_storage_path": parsed_storage_path
                    }
                else:
                    return {
                        "valid": True,
                        "synchronized": True,
                        "note": "No content in either location"
                    }
            
            # Both have content, compare
            content_matches = firestore_content.strip() == gcs_content.strip()
            
            return {
                "valid": True,
                "synchronized": content_matches,
                "firestore_content_length": len(firestore_content),
                "gcs_content_length": len(gcs_content),
                "parsed_storage_path": parsed_storage_path,
                "content_matches": content_matches,
                "note": "Content synchronized" if content_matches else "Content differs between Firestore and GCS"
            }
            
        except Exception as e:
            self.logger.error("Error validating content sync", 
                            org_id=org_id,
                            document_id=document_id,
                            storage_path=storage_path,
                            error=str(e))
            return {
                "valid": False,
                "error": f"Validation failed: {e}"
            }