import os
from typing import Dict, Any, Optional, Tuple
from datetime import datetime

from app.core.logging import get_service_logger
from app.core.firebase_client import get_collection, firebase_manager
from app.core.gcs_client import gcs_client, GCSClientError
from app.core.config import settings
from google.cloud.firestore_v1 import FieldFilter
from google.api_core.exceptions import GoogleAPIError

# OpenAI for summarization
try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

logger = get_service_logger("document_summarization")


class DocumentSummarizationError(Exception):
    """Base exception for document summarization errors."""
    pass


class DocumentNotFoundError(DocumentSummarizationError):
    """Document not found in Firestore."""
    pass


class ContentNotFoundError(DocumentSummarizationError):
    """Document content not found in file_content field."""
    pass


class SummarizationError(DocumentSummarizationError):
    """Error during AI summarization process."""
    pass


class DocumentSummarizationService:
    """
    Service for AI-powered document content summarization.
    
    Follows SOLID principles:
    - Single Responsibility: Only handles document summarization
    - Open/Closed: Extensible for different AI providers
    - Liskov Substitution: Can be replaced with other summarization services
    - Interface Segregation: Focused interface for summarization only
    - Dependency Inversion: Depends on abstractions (OpenAI client, Firestore)
    """
    
    def __init__(self):
        self.logger = logger
        self._openai_client: Optional[AsyncOpenAI] = None
        self._initialize_ai_client()
    
    def _initialize_ai_client(self) -> None:
        """Initialize OpenAI client for summarization."""
        if not OPENAI_AVAILABLE:
            self.logger.error("OpenAI package not available")
            return
            
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            self.logger.warning("OPENAI_API_KEY not found in environment variables")
            return
            
        try:
            self._openai_client = AsyncOpenAI(api_key=openai_api_key)
            self.logger.info("OpenAI client initialized successfully")
        except Exception as e:
            self.logger.error("Failed to initialize OpenAI client", error=str(e))
    
    def _get_collection(self, org_id: str):
        """Get the documents collection for an organization."""
        return get_collection(f"organizations/{org_id}/documents")
    
    async def _find_document_by_filename(
        self, 
        org_id: str, 
        filename: str
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Find document in Firestore by filename.
        
        Args:
            org_id: Organization ID
            filename: Document filename to search for
            
        Returns:
            Tuple of (document_id, document_data)
            
        Raises:
            DocumentNotFoundError: If document not found
        """
        try:
            collection = self._get_collection(org_id)
            
            # Search by filename first
            query = collection.where(filter=FieldFilter("filename", "==", filename))
            docs = query.stream()
            
            async for doc in docs:
                doc_data = doc.to_dict()
                self.logger.info("Found document by filename", 
                               org_id=org_id,
                               document_id=doc.id,
                               filename=filename,
                               storage_path=doc_data.get("storage_path"))
                return doc.id, doc_data
            
            # If not found by filename, try searching by storage_path containing filename
            query = collection.where(filter=FieldFilter("storage_path", ">=", filename))
            docs = query.stream()
            
            async for doc in docs:
                doc_data = doc.to_dict()
                storage_path = doc_data.get("storage_path", "")
                if filename in storage_path:
                    self.logger.info("Found document by storage_path match", 
                                   org_id=org_id,
                                   document_id=doc.id,
                                   filename=filename,
                                   storage_path=storage_path)
                    return doc.id, doc_data
            
            raise DocumentNotFoundError(f"Document with filename '{filename}' not found in organization {org_id}")
            
        except GoogleAPIError as e:
            self.logger.error("Error searching for document", 
                            org_id=org_id,
                            filename=filename,
                            error=str(e))
            raise DocumentSummarizationError(f"Failed to search for document: {e}")
    
    async def _generate_summary(self, content: str, document_metadata: Dict[str, Any]) -> str:
        """
        Generate AI-powered summary of document content.
        
        Args:
            content: Document content to summarize
            document_metadata: Document metadata for context
            
        Returns:
            Markdown-formatted summary
            
        Raises:
            SummarizationError: If summarization fails
        """
        if not self._openai_client:
            raise SummarizationError("OpenAI client not initialized")
        
        if not content or len(content.strip()) == 0:
            raise ContentNotFoundError("Document content is empty")
        
        try:
            # Prepare document context
            filename = document_metadata.get("filename", "Unknown Document")
            file_type = document_metadata.get("file_type", "unknown")
            created_at = document_metadata.get("created_at", "")
            
            # Create comprehensive prompt for summarization
            system_prompt = """You are an expert document summarizer. Create comprehensive, structured summaries in markdown format.

REQUIREMENTS:
1. Extract and highlight key information, main points, and important details
2. Organize content with clear headings and subheadings
3. Use bullet points and numbered lists for clarity
4. Include any important data, numbers, dates, or references
5. Maintain the logical flow and structure of the original document
6. Identify document type and purpose in the summary
7. Format output in clean, readable markdown

STRUCTURE YOUR SUMMARY AS:
# Document Summary: [Document Name]

## Document Information
- **Type**: [Document type]
- **Created**: [Date if available]
- **Key Purpose**: [Main purpose/objective]

## Executive Summary
[Brief overview in 2-3 sentences]

## Key Points
[Main content organized by importance]

## Important Details
[Specific data, numbers, processes, etc.]

## Conclusion
[Final takeaways or action items if applicable]"""

            user_prompt = f"""Please summarize the following document:

**Document Name**: {filename}
**File Type**: {file_type}
**Created**: {created_at}

**Content to Summarize**:
{content}

Please provide a comprehensive markdown summary following the structure outlined in the system prompt."""

            # Generate summary using OpenAI
            response = await self._openai_client.chat.completions.create(
                model=settings.OPENAI_MODEL,  # Using configured model
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                # Note: Using default parameters for maximum compatibility with gpt-5-mini
            )
            
            summary = response.choices[0].message.content
            
            if not summary:
                raise SummarizationError("OpenAI returned empty summary")
            
            self.logger.info("Successfully generated summary", 
                           filename=filename,
                           content_length=len(content),
                           summary_length=len(summary),
                           model=settings.OPENAI_MODEL)
            
            return summary
            
        except Exception as e:
            self.logger.error("Failed to generate summary", 
                            filename=filename,
                            content_length=len(content),
                            error=str(e))
            raise SummarizationError(f"Failed to generate summary: {e}")
    
    async def _save_summary_to_gcs(
        self, 
        org_id: str, 
        original_storage_path: str, 
        summary: str
    ) -> str:
        """
        Save summary to GCS in the summaries folder.
        
        Args:
            org_id: Organization ID
            original_storage_path: Original document storage path
            summary: Markdown summary content
            
        Returns:
            GCS path of saved summary
            
        Raises:
            SummarizationError: If save fails
        """
        try:
            # Parse original storage path to construct summary path
            # Format: org_name/original/folder_name/filename.ext
            # Target: org_name/summaries/folder_name/filename.md
            
            path_parts = original_storage_path.split('/')
            if len(path_parts) < 3:
                raise SummarizationError(f"Invalid storage path format: {original_storage_path}")
            
            org_name = path_parts[0]
            folder_name = path_parts[2] if len(path_parts) > 3 else "general"
            original_filename = path_parts[-1]
            
            # Create summary filename
            base_filename = os.path.splitext(original_filename)[0]
            summary_filename = f"{base_filename}_summary.md"
            
            # Construct summary storage path
            summary_storage_path = f"{org_name}/summaries/{folder_name}/{summary_filename}"
            
            # Save to GCS
            summary_bytes = summary.encode('utf-8')
            gcs_client.upload_file_to_path(
                storage_path=summary_storage_path,
                content=summary_bytes,
                content_type="text/markdown"
            )
            
            self.logger.info("Saved summary to GCS", 
                           org_id=org_id,
                           original_storage_path=original_storage_path,
                           summary_storage_path=summary_storage_path,
                           summary_size=len(summary_bytes))
            
            return summary_storage_path
            
        except GCSClientError as e:
            self.logger.error("Failed to save summary to GCS", 
                            org_id=org_id,
                            original_storage_path=original_storage_path,
                            error=str(e))
            raise SummarizationError(f"Failed to save summary to GCS: {e}")
        except Exception as e:
            self.logger.error("Unexpected error saving summary", 
                            org_id=org_id,
                            original_storage_path=original_storage_path,
                            error=str(e))
            raise SummarizationError(f"Unexpected error saving summary: {e}")
    
    async def _update_document_with_summary(
        self, 
        org_id: str, 
        document_id: str, 
        summary_storage_path: str,
        summary_metadata: Dict[str, Any]
    ) -> None:
        """
        Update document in Firestore with summary information.
        
        Args:
            org_id: Organization ID
            document_id: Document ID to update
            summary_storage_path: GCS path of saved summary
            summary_metadata: Summary generation metadata
        """
        try:
            collection = self._get_collection(org_id)
            doc_ref = collection.document(document_id)
            
            update_data = {
                "summary_storage_path": summary_storage_path,
                "summary_metadata": summary_metadata,
                "has_summary": True,
                "updated_at": firebase_manager.get_server_timestamp()
            }
            
            await doc_ref.update(update_data)
            
            self.logger.info("Updated document with summary information", 
                           org_id=org_id,
                           document_id=document_id,
                           summary_storage_path=summary_storage_path)
            
        except Exception as e:
            self.logger.error("Failed to update document with summary", 
                            org_id=org_id,
                            document_id=document_id,
                            error=str(e))
            # Don't raise exception here - summary was created successfully
    
    async def summarize_document_content(
        self, 
        org_id: str, 
        filename: str
    ) -> Dict[str, Any]:
        """
        Summarize document content by filename.
        
        Args:
            org_id: Organization ID
            filename: Document filename or identifier
            
        Returns:
            Dictionary containing summary information
            
        Raises:
            DocumentNotFoundError: If document not found
            ContentNotFoundError: If document has no content
            SummarizationError: If summarization fails
        """
        try:
            self.logger.info("Starting document summarization", 
                           org_id=org_id,
                           filename=filename)
            
            # Step 1: Find document in Firestore
            document_id, document_data = await self._find_document_by_filename(org_id, filename)
            
            # Step 2: Extract content from file_content field
            content = document_data.get("file_content")
            if not content:
                raise ContentNotFoundError(
                    f"Document '{filename}' has no content in file_content field. "
                    "Ensure document has been parsed/processed first."
                )
            
            # Step 3: Generate AI summary
            summary = await self._generate_summary(content, document_data)
            
            # Step 4: Save summary to GCS
            original_storage_path = document_data.get("storage_path", "")
            summary_storage_path = await self._save_summary_to_gcs(
                org_id, original_storage_path, summary
            )
            
            # Step 5: Prepare summary metadata
            summary_metadata = {
                "created_at": datetime.utcnow().isoformat(),
                "model": settings.OPENAI_MODEL,
                "content_length": len(content),
                "summary_length": len(summary),
                "original_filename": document_data.get("filename"),
                "original_storage_path": original_storage_path
            }
            
            # Step 6: Update document in Firestore
            await self._update_document_with_summary(
                org_id, document_id, summary_storage_path, summary_metadata
            )
            
            # Step 7: Prepare response
            response = {
                "success": True,
                "document_id": document_id,
                "filename": filename,
                "original_storage_path": original_storage_path,
                "summary_storage_path": summary_storage_path,
                "summary_content": summary,
                "summary_metadata": summary_metadata,
                "gcs_url": f"https://storage.googleapis.com/{settings.GCS_BUCKET_NAME}/{summary_storage_path}",
                "timestamp": datetime.utcnow().isoformat()
            }
            
            self.logger.info("Document summarization completed successfully", 
                           org_id=org_id,
                           filename=filename,
                           document_id=document_id,
                           summary_storage_path=summary_storage_path,
                           summary_length=len(summary))
            
            return response
            
        except (DocumentNotFoundError, ContentNotFoundError, SummarizationError):
            raise
        except Exception as e:
            self.logger.error("Unexpected error during summarization", 
                            org_id=org_id,
                            filename=filename,
                            error=str(e))
            raise SummarizationError(f"Unexpected error during summarization: {e}")


# Create singleton instance
document_summarization_service = DocumentSummarizationService()