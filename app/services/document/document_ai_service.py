"""
Document AI Service - Simplified AI summarization service.

This service handles AI-powered document summarization:
- Generate summaries from document content
- Update existing summaries
- Custom prompt support
- Simple, focused approach following biz_to_bricks_v3 patterns
"""

import os
from typing import Optional, Dict, Any, List
from datetime import datetime

try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    from langchain_openai import ChatOpenAI
    from langchain.schema import HumanMessage, SystemMessage
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False

from app.models.document import Document
from app.core.config import settings
from .document_base_service import (
    DocumentBaseService, DocumentNotFoundError, 
    DocumentValidationError, DocumentUploadError
)


class DocumentSummarizationError(Exception):
    """Base exception for document summarization errors."""
    pass


class ContentNotFoundError(DocumentSummarizationError):
    """Document content not found in file_content field."""
    pass


class SummarizationError(DocumentSummarizationError):
    """Error during AI summarization process."""
    pass


class DocumentFAQError(Exception):
    """Base exception for document FAQ generation errors."""
    pass


class FAQGenerationError(DocumentFAQError):
    """Error during AI FAQ generation process."""
    pass


class DocumentQuestionsError(Exception):
    """Base exception for document questions generation errors."""
    pass


class QuestionsGenerationError(DocumentQuestionsError):
    """Error during AI questions generation process."""
    pass


class DocumentAIService(DocumentBaseService):
    """Simple service for AI-powered document summarization."""
    
    def __init__(self):
        """Initialize the AI service."""
        super().__init__()
        self._openai_client: Optional[AsyncOpenAI] = None
        self._langchain_client: Optional[ChatOpenAI] = None
        self._initialize_openai_client()
        self._initialize_langchain_client()

    def _initialize_openai_client(self) -> None:
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

    def _initialize_langchain_client(self) -> None:
        """Initialize LangChain client for FAQ generation."""
        if not LANGCHAIN_AVAILABLE:
            self.logger.error("LangChain package not available")
            return
            
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            self.logger.warning("OPENAI_API_KEY not found for LangChain client")
            return
            
        try:
            self._langchain_client = ChatOpenAI(
                model=settings.OPENAI_MODEL,
                openai_api_key=openai_api_key,
                # Note: Using default temperature for model compatibility with gpt-5-mini
            )
            self.logger.info("LangChain client initialized successfully")
        except Exception as e:
            self.logger.error("Failed to initialize LangChain client", error=str(e))

    async def _find_document_by_filename(
        self, 
        org_id: str, 
        filename: str
    ) -> tuple[str, Document]:
        """
        Find document in Firestore by filename.
        
        Args:
            org_id: Organization ID
            filename: Document filename to search for
            
        Returns:
            Tuple of (document_id, Document instance)
            
        Raises:
            DocumentNotFoundError: If document not found
        """
        try:
            from google.cloud.firestore_v1 import FieldFilter
            
            collection = self._get_collection(org_id)
            
            # Search by filename first
            query = collection.where(filter=FieldFilter("filename", "==", filename))
            docs = query.stream()
            
            async for doc in docs:
                doc_data = doc.to_dict()
                document = Document.from_dict(doc_data, doc.id)

                if document.is_active:
                    # DEBUG: Log document AI field states
                    self.logger.info("Found document by filename",
                                   org_id=org_id,
                                   document_id=doc.id,
                                   filename=filename,
                                   storage_path=document.storage_path)

                    self.logger.debug("Document AI fields state",
                                    document_id=doc.id,
                                    has_ai_summary=document.has_ai_summary,
                                    ai_summary_length=len(document.ai_summary) if document.ai_summary else 0,
                                    has_ai_faq=document.has_ai_faq,
                                    faq_count=len(document.ai_faq) if document.ai_faq else 0,
                                    has_ai_questions=document.has_ai_questions,
                                    questions_count=len(document.ai_questions) if document.ai_questions else 0)

                    return doc.id, document
            
            raise DocumentNotFoundError(f"Document with filename '{filename}' not found in organization {org_id}")
            
        except Exception as e:
            self.logger.error("Error searching for document", 
                            org_id=org_id,
                            filename=filename,
                            error=str(e))
            raise DocumentNotFoundError(f"Failed to search for document: {e}")

    async def _generate_summary(
        self, 
        content: str, 
        document: Document, 
        custom_prompt: Optional[str] = None
    ) -> str:
        """
        Generate AI-powered summary of document content.
        
        Args:
            content: Document content to summarize
            document: Document instance for context
            custom_prompt: Optional custom prompt for summarization
            
        Returns:
            AI-generated summary in markdown format
            
        Raises:
            SummarizationError: If summarization fails
        """
        if not self._openai_client:
            raise SummarizationError("OpenAI client not initialized")
        
        if not content or len(content.strip()) == 0:
            raise ContentNotFoundError("Document content is empty")
        
        try:
            # Default system prompt (following biz_to_bricks_v3 approach)
            default_system_prompt = """You are an expert document summarizer. Create comprehensive, structured summaries in markdown format.

REQUIREMENTS:
1. Extract and highlight key information, main points, and important details
2. Organize content with clear headings and subheadings  
3. Use bullet points and numbered lists for clarity
4. Include any important data, numbers, dates, or references
5. Maintain the logical flow and structure of the original document
6. Identify document type and purpose in the summary
7. Format output in clean, readable markdown

Write a concise summary of the following document without losing any important information."""

            # Use custom prompt if provided, otherwise use default
            system_prompt = custom_prompt if custom_prompt else default_system_prompt
            
            # Prepare document context
            filename = document.filename
            file_type = str(document.file_type)  # Handle both string and enum values
            created_at = document.created_at.isoformat() if document.created_at else ""
            
            user_prompt = f"""Please summarize the following document:

**Document Name**: {filename}
**File Type**: {file_type}
**Created**: {created_at}

**Content to Summarize**:
{content}"""

            # Generate summary using OpenAI
            response = await self._openai_client.chat.completions.create(
                model=settings.OPENAI_MODEL,  # Using cost-effective model
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

    async def _generate_faq(
        self, 
        content: str, 
        document: Document, 
        faq_count: int = 5,
        custom_prompt: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """
        Generate AI-powered FAQ from document content using LangChain.
        
        Args:
            content: Document content to generate FAQ from
            document: Document instance for context
            faq_count: Number of FAQ items to generate (1-10)
            custom_prompt: Optional custom prompt for FAQ generation
            
        Returns:
            List of FAQ items as dictionaries with 'question' and 'answer' keys
            
        Raises:
            FAQGenerationError: If FAQ generation fails
        """
        if not self._langchain_client:
            raise FAQGenerationError("LangChain client not initialized")
        
        if not content or len(content.strip()) == 0:
            raise ContentNotFoundError("Document content is empty")
        
        # Validate FAQ count
        if faq_count < 1 or faq_count > 10:
            raise FAQGenerationError("FAQ count must be between 1 and 10")
        
        try:
            # Default system prompt for FAQ generation
            default_system_prompt = f"""You are an expert FAQ generator. Create exactly {faq_count} frequently asked questions and comprehensive answers based on the provided document content.

REQUIREMENTS:
1. Generate exactly {faq_count} question-answer pairs
2. Questions should be the most likely questions readers would ask
3. Answers should be comprehensive and based solely on the document content
4. Questions should cover different aspects of the document (overview, details, implications, etc.)
5. Format each FAQ as a JSON object with 'question' and 'answer' keys
6. Return ONLY a valid JSON array with no additional text or formatting
7. Keep answers concise but informative (2-4 sentences each)
8. Ensure questions are clear and specific

EXAMPLE FORMAT:
[
    {{"question": "What is this document about?", "answer": "This document discusses..."}},
    {{"question": "Who is the target audience?", "answer": "The target audience includes..."}}
]

Generate {faq_count} FAQs that provide maximum value to readers."""

            # Use custom prompt if provided, otherwise use default
            system_prompt = custom_prompt if custom_prompt else default_system_prompt
            
            # Prepare document context
            filename = document.filename
            file_type = str(document.file_type)
            created_at = document.created_at.isoformat() if document.created_at else ""
            
            user_prompt = f"""Generate {faq_count} FAQs for the following document:

**Document Name**: {filename}
**File Type**: {file_type}
**Created**: {created_at}

**Content**:
{content}

Return exactly {faq_count} FAQ items as a valid JSON array."""

            # Create messages
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            
            # Generate FAQ using LangChain
            response = self._langchain_client.invoke(messages)
            
            if not response or not response.content:
                raise FAQGenerationError("LangChain returned empty response")
            
            # Parse JSON response
            import json
            try:
                faq_data = json.loads(response.content.strip())
            except json.JSONDecodeError as e:
                self.logger.error("Failed to parse FAQ JSON", 
                                content=response.content[:200],
                                error=str(e))
                raise FAQGenerationError(f"Failed to parse FAQ JSON: {e}")
            
            # Validate response structure
            if not isinstance(faq_data, list):
                raise FAQGenerationError("FAQ response must be a list")
            
            if len(faq_data) != faq_count:
                self.logger.warning("FAQ count mismatch", 
                                  expected=faq_count,
                                  received=len(faq_data))
            
            # Validate each FAQ item
            validated_faqs = []
            for i, item in enumerate(faq_data):
                if not isinstance(item, dict):
                    raise FAQGenerationError(f"FAQ item {i} must be a dictionary")
                
                if 'question' not in item or 'answer' not in item:
                    raise FAQGenerationError(f"FAQ item {i} missing required keys")
                
                if not isinstance(item['question'], str) or not isinstance(item['answer'], str):
                    raise FAQGenerationError(f"FAQ item {i} values must be strings")
                
                if not item['question'].strip() or not item['answer'].strip():
                    raise FAQGenerationError(f"FAQ item {i} cannot have empty values")
                
                validated_faqs.append({
                    'question': item['question'].strip(),
                    'answer': item['answer'].strip()
                })
            
            self.logger.info("Successfully generated FAQ", 
                           filename=filename,
                           content_length=len(content),
                           faq_count=len(validated_faqs),
                           model=settings.OPENAI_MODEL)
            
            return validated_faqs
            
        except json.JSONDecodeError as e:
            self.logger.error("Failed to parse FAQ response", 
                            filename=filename,
                            error=str(e))
            raise FAQGenerationError(f"Failed to parse FAQ response: {e}")
        except Exception as e:
            self.logger.error("Failed to generate FAQ", 
                            filename=filename,
                            content_length=len(content),
                            faq_count=faq_count,
                            error=str(e))
            raise FAQGenerationError(f"Failed to generate FAQ: {e}")

    async def _generate_questions(
        self, 
        content: str, 
        document: Document, 
        question_count: int = 5,
        custom_prompt: Optional[str] = None
    ) -> List[str]:
        """
        Generate AI-powered questions from document content using LangChain.
        
        Args:
            content: Document content to generate questions from
            document: Document instance for context
            question_count: Number of questions to generate (1-20)
            custom_prompt: Optional custom prompt for question generation
            
        Returns:
            List of questions as strings
            
        Raises:
            QuestionsGenerationError: If question generation fails
        """
        if not self._langchain_client:
            raise QuestionsGenerationError("LangChain client not initialized")
        
        if not content or len(content.strip()) == 0:
            raise ContentNotFoundError("Document content is empty")
        
        # Validate question count
        if question_count < 1 or question_count > 20:
            raise QuestionsGenerationError("Question count must be between 1 and 20")
        
        try:
            # Default system prompt for question generation
            default_system_prompt = f"""You are an expert question generator. Create exactly {question_count} insightful and thought-provoking questions based on the provided document content.

REQUIREMENTS:
1. Generate exactly {question_count} questions
2. Questions should be relevant and encourage deep thinking about the document
3. Questions should cover different aspects of the document (key concepts, implications, applications, etc.)
4. Each question should be clear, specific, and standalone
5. Questions should be appropriate for someone who has read the document
6. Return ONLY a valid JSON array of strings with no additional text or formatting
7. Each question should be concise but meaningful
8. Avoid yes/no questions - prefer open-ended questions that require explanation

EXAMPLE FORMAT:
[
    "What are the key benefits mentioned in this document?",
    "How does this approach compare to traditional methods?",
    "What challenges might arise during implementation?"
]

Generate {question_count} high-quality questions that would be valuable for understanding and discussing this document."""
            
            # Use custom prompt if provided, otherwise use default
            system_prompt = custom_prompt if custom_prompt else default_system_prompt
            
            # Prepare document context
            filename = document.filename
            file_type = str(document.file_type)
            created_at = document.created_at.isoformat() if document.created_at else ""
            
            user_prompt = f"""Generate {question_count} thoughtful questions for the following document:

**Document Name**: {filename}
**File Type**: {file_type}
**Created**: {created_at}

**Content**:
{content}

Return exactly {question_count} questions as a valid JSON array of strings."""

            # Create messages
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            
            # Generate questions using LangChain
            response = self._langchain_client.invoke(messages)
            
            if not response or not response.content:
                self.logger.error("LangChain returned empty response", 
                                response=str(response),
                                has_content=bool(response and response.content if response else False))
                raise QuestionsGenerationError("LangChain returned empty response")
            
            # Log the raw response for debugging
            self.logger.debug("Raw LangChain response", 
                            content=response.content[:500])
            
            # Parse JSON response
            import json
            try:
                # Clean the response content - remove markdown code blocks if present
                content = response.content.strip()
                if content.startswith('```json'):
                    content = content[7:]
                if content.startswith('```'):
                    content = content[3:]
                if content.endswith('```'):
                    content = content[:-3]
                content = content.strip()
                
                questions_data = json.loads(content)
            except json.JSONDecodeError as e:
                self.logger.error("Failed to parse questions JSON", 
                                raw_content=response.content[:500],
                                cleaned_content=content[:500],
                                error=str(e))
                raise QuestionsGenerationError(f"Failed to parse questions JSON: {e}")
            
            # Validate response structure
            if not isinstance(questions_data, list):
                raise QuestionsGenerationError("Questions response must be a list")
            
            if len(questions_data) != question_count:
                self.logger.warning("Question count mismatch", 
                                  expected=question_count,
                                  received=len(questions_data))
            
            # Validate each question
            validated_questions = []
            for i, question in enumerate(questions_data):
                if not isinstance(question, str):
                    raise QuestionsGenerationError(f"Question {i} must be a string")
                
                if not question.strip():
                    raise QuestionsGenerationError(f"Question {i} cannot be empty")
                
                validated_questions.append(question.strip())
            
            self.logger.info("Successfully generated questions", 
                           filename=filename,
                           content_length=len(content),
                           question_count=len(validated_questions),
                           model=settings.OPENAI_MODEL)
            
            return validated_questions
            
        except json.JSONDecodeError as e:
            self.logger.error("Failed to parse questions response", 
                            filename=filename,
                            error=str(e))
            raise QuestionsGenerationError(f"Failed to parse questions response: {e}")
        except Exception as e:
            self.logger.error("Failed to generate questions", 
                            filename=filename,
                            content_length=len(content),
                            question_count=question_count,
                            error=str(e))
            raise QuestionsGenerationError(f"Failed to generate questions: {e}")

    async def generate_summary_by_filename(
        self, 
        org_id: str, 
        filename: str,
        custom_prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate AI summary for a document by filename.
        
        Args:
            org_id: Organization ID
            filename: Document filename
            custom_prompt: Optional custom prompt for summarization
            
        Returns:
            Dictionary containing summary and metadata
            
        Raises:
            DocumentNotFoundError: If document not found
            ContentNotFoundError: If document has no content
            SummarizationError: If summarization fails
        """
        try:
            self.logger.info("Starting document summarization",
                           org_id=org_id,
                           filename=filename,
                           has_custom_prompt=bool(custom_prompt))

            # Find document in Firestore
            document_id, document = await self._find_document_by_filename(org_id, filename)

            # Check if summary already exists
            if document.has_ai_summary:
                self.logger.info("Summary already exists for document, returning existing summary",
                               org_id=org_id,
                               filename=filename,
                               summary_length=len(document.ai_summary))

                # Return existing summary
                response = {
                    "success": True,
                    "document_id": document_id,
                    "filename": filename,
                    "ai_summary": document.ai_summary,
                    "summary_metadata": document.summary_metadata or {},
                    "timestamp": datetime.utcnow().isoformat()
                }

                return response

            # Extract content from file_content field
            content = document.file_content
            if not content:
                raise ContentNotFoundError(
                    f"Document '{filename}' has no content in file_content field. "
                    "Ensure document has been parsed/processed first."
                )
            
            # Generate AI summary
            summary = await self._generate_summary(content, document, custom_prompt)
            
            # Prepare summary metadata
            summary_metadata = {
                "generated_at": datetime.utcnow().isoformat(),
                "model": settings.OPENAI_MODEL,
                "content_length": len(content),
                "summary_length": len(summary),
                "has_custom_prompt": bool(custom_prompt)
            }
            
            # Update document with new summary
            document.update_ai_summary(summary, summary_metadata)

            # Debug: Log what we're about to save
            doc_dict = document.to_dict()
            self.logger.debug("Summary - About to save to Firestore",
                            org_id=org_id,
                            filename=filename,
                            document_id=document_id,
                            has_ai_summary_in_dict=bool(doc_dict.get("ai_summary")),
                            ai_summary_length=len(doc_dict.get("ai_summary", "")),
                            has_summary_metadata=bool(doc_dict.get("summary_metadata")))

            # Save to Firestore
            doc_ref = self._get_collection(org_id).document(document_id)
            await doc_ref.update(doc_dict)

            self.logger.info("Summary - Successfully saved to Firestore",
                           org_id=org_id,
                           filename=filename,
                           document_id=document_id,
                           summary_length=len(summary))
            
            # Prepare response
            response = {
                "success": True,
                "document_id": document_id,
                "filename": filename,
                "ai_summary": summary,
                "summary_metadata": summary_metadata,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            self.logger.info("Document summarization completed successfully", 
                           org_id=org_id,
                           filename=filename,
                           document_id=document_id,
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

    async def get_summary_by_filename(
        self, 
        org_id: str, 
        filename: str
    ) -> Dict[str, Any]:
        """
        Get existing AI summary for a document by filename.
        
        Args:
            org_id: Organization ID
            filename: Document filename
            
        Returns:
            Dictionary containing existing summary and metadata
            
        Raises:
            DocumentNotFoundError: If document not found
        """
        try:
            # Find document in Firestore
            document_id, document = await self._find_document_by_filename(org_id, filename)
            
            response = {
                "document_id": document_id,
                "filename": filename,
                "ai_summary": document.ai_summary,
                "summary_metadata": document.summary_metadata,
                "has_summary": document.has_ai_summary,
                "summary_preview": document.summary_preview,
                "updated_at": document.updated_at.isoformat() if document.updated_at else None
            }
            
            self.logger.debug("Retrieved document summary", 
                            org_id=org_id,
                            filename=filename,
                            document_id=document_id,
                            has_summary=document.has_ai_summary)
            
            return response
            
        except DocumentNotFoundError:
            raise
        except Exception as e:
            self.logger.error("Error retrieving document summary", 
                            org_id=org_id,
                            filename=filename,
                            error=str(e))
            raise DocumentUploadError(f"Failed to retrieve document summary: {e}")

    async def update_summary_by_filename(
        self, 
        org_id: str, 
        filename: str,
        summary: Optional[str] = None,
        custom_prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Update existing AI summary for a document.
        
        Args:
            org_id: Organization ID
            filename: Document filename
            summary: New summary content (if provided directly)
            custom_prompt: Custom prompt to regenerate summary
            
        Returns:
            Dictionary containing updated summary and metadata
            
        Raises:
            DocumentNotFoundError: If document not found
            DocumentValidationError: If neither summary nor prompt provided
        """
        try:
            if not summary and not custom_prompt:
                raise DocumentValidationError("Either summary or custom_prompt must be provided")
            
            # If direct summary provided, use it
            if summary:
                # Find document in Firestore
                document_id, document = await self._find_document_by_filename(org_id, filename)
                
                # Update summary metadata
                summary_metadata = {
                    "updated_at": datetime.utcnow().isoformat(),
                    "update_type": "direct_update",
                    "summary_length": len(summary)
                }
                
                # Update document
                document.update_ai_summary(summary, summary_metadata)

                # Debug: Log what we're about to save
                doc_dict = document.to_dict()
                self.logger.debug("Summary Update - About to save to Firestore",
                                org_id=org_id,
                                filename=filename,
                                document_id=document_id,
                                has_ai_summary_in_dict=bool(doc_dict.get("ai_summary")),
                                ai_summary_length=len(doc_dict.get("ai_summary", "")),
                                has_summary_metadata=bool(doc_dict.get("summary_metadata")))

                # Save to Firestore
                doc_ref = self._get_collection(org_id).document(document_id)
                await doc_ref.update(doc_dict)

                self.logger.info("Summary Update - Successfully saved to Firestore",
                               org_id=org_id,
                               filename=filename,
                               document_id=document_id,
                               summary_length=len(summary))
                
                response = {
                    "success": True,
                    "document_id": document_id,
                    "filename": filename,
                    "ai_summary": summary,
                    "summary_metadata": summary_metadata,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
            else:
                # Regenerate with custom prompt
                response = await self.generate_summary_by_filename(org_id, filename, custom_prompt)
            
            self.logger.info("Document summary updated",
                           org_id=org_id,
                           filename=filename,
                           summary_length=len(response.get("ai_summary", "")))
            
            return response
            
        except (DocumentNotFoundError, DocumentValidationError):
            raise
        except Exception as e:
            self.logger.error("Error updating document summary", 
                            org_id=org_id,
                            filename=filename,
                            error=str(e))
            raise DocumentUploadError(f"Failed to update document summary: {e}")

    async def generate_faq_by_filename(
        self, 
        org_id: str, 
        filename: str,
        faq_count: int = 5,
        custom_prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate AI FAQ for a document by filename.
        
        Args:
            org_id: Organization ID
            filename: Document filename
            faq_count: Number of FAQ items to generate (1-10)
            custom_prompt: Optional custom prompt for FAQ generation
            
        Returns:
            Dictionary containing FAQ and metadata
            
        Raises:
            DocumentNotFoundError: If document not found
            ContentNotFoundError: If document has no content
            FAQGenerationError: If FAQ generation fails
        """
        try:
            self.logger.info("Starting document FAQ generation",
                           org_id=org_id,
                           filename=filename,
                           faq_count=faq_count,
                           has_custom_prompt=bool(custom_prompt))

            # Find document in Firestore
            document_id, document = await self._find_document_by_filename(org_id, filename)

            # Check if FAQ already exists
            if document.has_ai_faq:
                self.logger.info("FAQ already exists for document, returning existing FAQ",
                               org_id=org_id,
                               filename=filename,
                               existing_count=document.faq_count)

                # Return existing FAQ
                response = {
                    "success": True,
                    "document_id": document_id,
                    "filename": filename,
                    "ai_faq": document.ai_faq,
                    "faq_metadata": document.faq_metadata or {},
                    "timestamp": datetime.utcnow().isoformat()
                }

                return response

            # Extract content from file_content field
            content = document.file_content
            if not content:
                raise ContentNotFoundError(
                    f"Document '{filename}' has no content in file_content field. "
                    "Ensure document has been parsed/processed first."
                )
            
            # Generate AI FAQ
            faq_items = await self._generate_faq(content, document, faq_count, custom_prompt)
            
            # Prepare FAQ metadata
            faq_metadata = {
                "generated_at": datetime.utcnow().isoformat(),
                "model": settings.OPENAI_MODEL,
                "faq_count": len(faq_items),
                "content_length": len(content),
                "has_custom_prompt": bool(custom_prompt)
            }
            
            # Update document with new FAQ
            document.update_ai_faq(faq_items, faq_metadata)

            # Debug: Log what we're about to save
            doc_dict = document.to_dict()
            self.logger.debug("FAQ - About to save to Firestore",
                            org_id=org_id,
                            filename=filename,
                            document_id=document_id,
                            has_ai_faq_in_dict=bool(doc_dict.get("ai_faq")),
                            ai_faq_count=len(doc_dict.get("ai_faq", [])),
                            has_faq_metadata=bool(doc_dict.get("faq_metadata")))

            # Save to Firestore
            doc_ref = self._get_collection(org_id).document(document_id)
            await doc_ref.update(doc_dict)

            self.logger.info("FAQ - Successfully saved to Firestore",
                           org_id=org_id,
                           filename=filename,
                           document_id=document_id,
                           faq_count=len(faq_items))
            
            # Prepare response
            response = {
                "success": True,
                "document_id": document_id,
                "filename": filename,
                "ai_faq": faq_items,
                "faq_metadata": faq_metadata,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            self.logger.info("Document FAQ generation completed successfully", 
                           org_id=org_id,
                           filename=filename,
                           document_id=document_id,
                           faq_count=len(faq_items))
            
            return response
            
        except (DocumentNotFoundError, ContentNotFoundError, FAQGenerationError):
            raise
        except Exception as e:
            self.logger.error("Unexpected error during FAQ generation", 
                            org_id=org_id,
                            filename=filename,
                            error=str(e))
            raise FAQGenerationError(f"Unexpected error during FAQ generation: {e}")

    async def get_faq_by_filename(
        self, 
        org_id: str, 
        filename: str
    ) -> Dict[str, Any]:
        """
        Get existing AI FAQ for a document by filename.
        
        Args:
            org_id: Organization ID
            filename: Document filename
            
        Returns:
            Dictionary containing existing FAQ and metadata
            
        Raises:
            DocumentNotFoundError: If document not found
        """
        try:
            # Find document in Firestore
            document_id, document = await self._find_document_by_filename(org_id, filename)
            
            response = {
                "document_id": document_id,
                "filename": filename,
                "ai_faq": document.ai_faq,
                "faq_metadata": document.faq_metadata,
                "has_faq": document.has_ai_faq,
                "faq_count": document.faq_count,
                "faq_preview": document.faq_preview,
                "updated_at": document.updated_at.isoformat() if document.updated_at else None
            }
            
            self.logger.debug("Retrieved document FAQ", 
                            org_id=org_id,
                            filename=filename,
                            document_id=document_id,
                            has_faq=document.has_ai_faq)
            
            return response
            
        except DocumentNotFoundError:
            raise
        except Exception as e:
            self.logger.error("Error retrieving document FAQ", 
                            org_id=org_id,
                            filename=filename,
                            error=str(e))
            raise DocumentUploadError(f"Failed to retrieve document FAQ: {e}")

    async def update_faq_by_filename(
        self, 
        org_id: str, 
        filename: str,
        faq: Optional[List[Dict[str, str]]] = None,
        custom_prompt: Optional[str] = None,
        faq_count: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Update existing AI FAQ for a document.
        
        Args:
            org_id: Organization ID
            filename: Document filename
            faq: New FAQ content (if provided directly)
            custom_prompt: Custom prompt to regenerate FAQ
            faq_count: Number of FAQs to generate with custom prompt
            
        Returns:
            Dictionary containing updated FAQ and metadata
            
        Raises:
            DocumentNotFoundError: If document not found
            DocumentValidationError: If neither FAQ nor prompt provided
        """
        try:
            if not faq and not custom_prompt:
                raise DocumentValidationError("Either faq or custom_prompt must be provided")
            
            # If direct FAQ provided, use it
            if faq:
                # Find document in Firestore
                document_id, document = await self._find_document_by_filename(org_id, filename)
                
                # Update FAQ metadata
                faq_metadata = {
                    "updated_at": datetime.utcnow().isoformat(),
                    "update_type": "direct_update",
                    "faq_count": len(faq)
                }
                
                # Update document
                document.update_ai_faq(faq, faq_metadata)

                # Debug: Log what we're about to save
                doc_dict = document.to_dict()
                self.logger.debug("FAQ Update - About to save to Firestore",
                                org_id=org_id,
                                filename=filename,
                                document_id=document_id,
                                has_ai_faq_in_dict=bool(doc_dict.get("ai_faq")),
                                ai_faq_count=len(doc_dict.get("ai_faq", [])),
                                has_faq_metadata=bool(doc_dict.get("faq_metadata")))

                # Save to Firestore
                doc_ref = self._get_collection(org_id).document(document_id)
                await doc_ref.update(doc_dict)

                self.logger.info("FAQ Update - Successfully saved to Firestore",
                               org_id=org_id,
                               filename=filename,
                               document_id=document_id,
                               faq_count=len(faq))
                
                response = {
                    "success": True,
                    "document_id": document_id,
                    "filename": filename,
                    "ai_faq": faq,
                    "faq_metadata": faq_metadata,
                    "update_type": "direct_update",
                    "timestamp": datetime.utcnow().isoformat()
                }
                
            else:
                # Regenerate with custom prompt
                response = await self.generate_faq_by_filename(
                    org_id, 
                    filename, 
                    faq_count or 5,
                    custom_prompt
                )
                response["update_type"] = "regenerated"
            
            self.logger.info("Document FAQ updated", 
                           org_id=org_id,
                           filename=filename,
                           update_type=response.get("update_type"),
                           faq_count=len(response.get("ai_faq", [])))
            
            return response
            
        except (DocumentNotFoundError, DocumentValidationError):
            raise
        except Exception as e:
            self.logger.error("Error updating document FAQ", 
                            org_id=org_id,
                            filename=filename,
                            error=str(e))
            raise DocumentUploadError(f"Failed to update document FAQ: {e}")

    async def generate_questions_by_filename(
        self, 
        org_id: str, 
        filename: str,
        question_count: int = 5,
        custom_prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate AI questions for a document by filename.
        
        If questions already exist in Firestore, returns the existing questions.
        Otherwise, generates new questions and saves them.
        
        Args:
            org_id: Organization ID
            filename: Document filename
            question_count: Number of questions to generate (1-20)
            custom_prompt: Optional custom prompt for question generation
            
        Returns:
            Dictionary containing questions and metadata
            
        Raises:
            DocumentNotFoundError: If document not found
            ContentNotFoundError: If document has no content
            QuestionsGenerationError: If question generation fails
        """
        try:
            self.logger.info("Starting document questions generation", 
                           org_id=org_id,
                           filename=filename,
                           question_count=question_count,
                           has_custom_prompt=bool(custom_prompt))
            
            # Find document in Firestore
            document_id, document = await self._find_document_by_filename(org_id, filename)
            
            # Check if questions already exist
            if document.has_ai_questions:
                self.logger.info("Questions already exist for document, returning existing questions", 
                               org_id=org_id,
                               filename=filename,
                               existing_count=document.questions_count)
                
                # Return existing questions
                response = {
                    "success": True,
                    "document_id": document_id,
                    "filename": filename,
                    "ai_questions": document.ai_questions,
                    "questions_metadata": document.questions_metadata or {},
                    "timestamp": datetime.utcnow().isoformat(),
                    "source": "existing"
                }
                
                return response
            
            # Extract content from file_content field
            content = document.file_content
            if not content:
                raise ContentNotFoundError(
                    f"Document '{filename}' has no content in file_content field. "
                    "Ensure document has been parsed/processed first."
                )
            
            # Generate AI questions
            questions = await self._generate_questions(content, document, question_count, custom_prompt)
            
            # Prepare questions metadata
            questions_metadata = {
                "generated_at": datetime.utcnow().isoformat(),
                "model": settings.OPENAI_MODEL,
                "question_count": len(questions),
                "content_length": len(content),
                "has_custom_prompt": bool(custom_prompt)
            }
            
            # Update document with new questions
            document.update_ai_questions(questions, questions_metadata)

            # Debug: Log what we're about to save
            doc_dict = document.to_dict()
            self.logger.debug("Questions - About to save to Firestore",
                            org_id=org_id,
                            filename=filename,
                            document_id=document_id,
                            has_ai_questions_in_dict=bool(doc_dict.get("ai_questions")),
                            ai_questions_count=len(doc_dict.get("ai_questions", [])),
                            has_questions_metadata=bool(doc_dict.get("questions_metadata")))

            # Save to Firestore
            doc_ref = self._get_collection(org_id).document(document_id)
            await doc_ref.update(doc_dict)

            self.logger.info("Questions - Successfully saved to Firestore",
                           org_id=org_id,
                           filename=filename,
                           document_id=document_id,
                           question_count=len(questions))
            
            # Prepare response
            response = {
                "success": True,
                "document_id": document_id,
                "filename": filename,
                "ai_questions": questions,
                "questions_metadata": questions_metadata,
                "timestamp": datetime.utcnow().isoformat(),
                "source": "generated"
            }
            
            self.logger.info("Document questions generation completed successfully", 
                           org_id=org_id,
                           filename=filename,
                           document_id=document_id,
                           question_count=len(questions))
            
            return response
            
        except (DocumentNotFoundError, ContentNotFoundError, QuestionsGenerationError):
            raise
        except Exception as e:
            self.logger.error("Unexpected error during questions generation", 
                            org_id=org_id,
                            filename=filename,
                            error=str(e))
            raise QuestionsGenerationError(f"Unexpected error during questions generation: {e}")

    async def get_questions_by_filename(
        self, 
        org_id: str, 
        filename: str
    ) -> Dict[str, Any]:
        """
        Get existing AI questions for a document by filename.
        
        Args:
            org_id: Organization ID
            filename: Document filename
            
        Returns:
            Dictionary containing existing questions and metadata
            
        Raises:
            DocumentNotFoundError: If document not found
        """
        try:
            # Find document in Firestore
            document_id, document = await self._find_document_by_filename(org_id, filename)
            
            response = {
                "document_id": document_id,
                "filename": filename,
                "ai_questions": document.ai_questions,
                "questions_metadata": document.questions_metadata,
                "has_questions": document.has_ai_questions,
                "questions_count": document.questions_count,
                "questions_preview": document.questions_preview,
                "updated_at": document.updated_at.isoformat() if document.updated_at else None
            }
            
            self.logger.debug("Retrieved questions for document", 
                            org_id=org_id,
                            filename=filename,
                            has_questions=document.has_ai_questions,
                            question_count=document.questions_count)
            
            return response
            
        except DocumentNotFoundError:
            raise
        except Exception as e:
            self.logger.error("Error retrieving document questions", 
                            org_id=org_id,
                            filename=filename,
                            error=str(e))
            raise DocumentUploadError(f"Failed to retrieve document questions: {e}")

    async def update_questions_by_filename(
        self, 
        org_id: str, 
        filename: str,
        questions: Optional[List[str]] = None,
        custom_prompt: Optional[str] = None,
        question_count: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Update existing AI questions for a document.
        
        Args:
            org_id: Organization ID
            filename: Document filename
            questions: New questions content (if provided directly)
            custom_prompt: Custom prompt to regenerate questions
            question_count: Number of questions to generate with custom prompt
            
        Returns:
            Dictionary containing updated questions and metadata
            
        Raises:
            DocumentNotFoundError: If document not found
            DocumentValidationError: If neither questions nor prompt provided
        """
        try:
            if questions is None and not custom_prompt:
                raise DocumentValidationError("Either questions or custom_prompt must be provided")
            
            # If direct questions provided, use them
            if questions is not None:
                # Find document in Firestore
                document_id, document = await self._find_document_by_filename(org_id, filename)
                
                # Update questions metadata
                questions_metadata = {
                    "updated_at": datetime.utcnow().isoformat(),
                    "update_type": "direct_update",
                    "question_count": len(questions)
                }
                
                # Update document
                document.update_ai_questions(questions, questions_metadata)

                # Debug: Log what we're about to save
                doc_dict = document.to_dict()
                self.logger.debug("Questions Update - About to save to Firestore",
                                org_id=org_id,
                                filename=filename,
                                document_id=document_id,
                                has_ai_questions_in_dict=bool(doc_dict.get("ai_questions")),
                                ai_questions_count=len(doc_dict.get("ai_questions", [])),
                                has_questions_metadata=bool(doc_dict.get("questions_metadata")))

                # Save to Firestore
                doc_ref = self._get_collection(org_id).document(document_id)
                await doc_ref.update(doc_dict)

                self.logger.info("Questions Update - Successfully saved to Firestore",
                               org_id=org_id,
                               filename=filename,
                               document_id=document_id,
                               question_count=len(questions))
                
                response = {
                    "success": True,
                    "document_id": document_id,
                    "filename": filename,
                    "ai_questions": questions,
                    "questions_metadata": questions_metadata,
                    "update_type": "direct_update",
                    "timestamp": datetime.utcnow().isoformat()
                }
                
            else:
                # Regenerate with custom prompt - bypass existing questions check
                # Find document in Firestore
                document_id, document = await self._find_document_by_filename(org_id, filename)
                
                # Extract content from file_content field
                content = document.file_content
                if not content:
                    raise ContentNotFoundError(
                        f"Document '{filename}' has no content in file_content field. "
                        "Ensure document has been parsed/processed first."
                    )
                
                # Generate AI questions (force regeneration)
                questions = await self._generate_questions(content, document, question_count or 5, custom_prompt)
                
                # Prepare questions metadata
                questions_metadata = {
                    "generated_at": datetime.utcnow().isoformat(),
                    "model": settings.OPENAI_MODEL,
                    "question_count": len(questions),
                    "content_length": len(content),
                    "has_custom_prompt": bool(custom_prompt),
                    "update_type": "regenerated"
                }
                
                # Update document with new questions
                document.update_ai_questions(questions, questions_metadata)

                # Debug: Log what we're about to save
                doc_dict = document.to_dict()
                self.logger.debug("Questions Regenerate - About to save to Firestore",
                                org_id=org_id,
                                filename=filename,
                                document_id=document_id,
                                has_ai_questions_in_dict=bool(doc_dict.get("ai_questions")),
                                ai_questions_count=len(doc_dict.get("ai_questions", [])),
                                has_questions_metadata=bool(doc_dict.get("questions_metadata")))

                # Save to Firestore
                doc_ref = self._get_collection(org_id).document(document_id)
                await doc_ref.update(doc_dict)

                self.logger.info("Questions Regenerate - Successfully saved to Firestore",
                               org_id=org_id,
                               filename=filename,
                               document_id=document_id,
                               question_count=len(questions))
                
                # Prepare response
                response = {
                    "success": True,
                    "document_id": document_id,
                    "filename": filename,
                    "ai_questions": questions,
                    "questions_metadata": questions_metadata,
                    "timestamp": datetime.utcnow().isoformat(),
                    "source": "generated",
                    "update_type": "regenerated"
                }
            
            self.logger.info("Document questions updated", 
                           org_id=org_id,
                           filename=filename,
                           update_type=response.get("update_type"),
                           question_count=len(response.get("ai_questions", [])))
            
            return response
            
        except (DocumentNotFoundError, DocumentValidationError):
            raise
        except Exception as e:
            self.logger.error("Error updating document questions", 
                            org_id=org_id,
                            filename=filename,
                            error=str(e))
            raise DocumentUploadError(f"Failed to update document questions: {e}")


# Create singleton instance
document_ai_service = DocumentAIService()