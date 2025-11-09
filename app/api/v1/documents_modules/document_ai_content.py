"""
Document AI content endpoints.

This module handles AI-generated content operations, focusing on:
- Retrieving AI content (summary, FAQ, questions)
- Updating AI content with validation
- Partial updates and content management
- Metadata tracking for AI content
"""

from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status

from app.models.schemas import (
    DocumentAIContentRequest,
    DocumentAIContentResponse,
    DocumentResponse
)
from app.services.document_service import DocumentNotFoundError
from .common import (
    get_document_dependencies,
    get_user_context,
    handle_document_not_found_error,
    handle_generic_error,
    log_operation_start,
    log_operation_success
)

router = APIRouter()


@router.get(
    "/{document_id}/ai-content",
    response_model=DocumentAIContentResponse,
    summary="🤖 Get AI Content",
    description="""Get AI-generated content (summary, FAQ, questions) for a document.

**Authentication Required:** Session token in `Authorization: Bearer <token>` header

**Path Parameters:**
- `document_id`: Document unique identifier

**Returns:**
- **Summary**: AI-generated document summary (if available)
- **FAQ**: List of question/answer pairs extracted from document content
- **Questions**: List of important questions identified in the document
- **Metadata**: Content size information and update timestamps

**Response Format:**
```json
{
  "document_id": "78258b82-db53-41a3-848a-ce45a32f99c7",
  "filename": "invoice-2025-001.pdf",
  "summary": "This invoice covers Q4 2024 services for Google...",
  "faq": [
    {
      "question": "What is the payment due date?",
      "answer": "Payment is due within 30 days of invoice date."
    },
    {
      "question": "What services were provided?",
      "answer": "Professional consulting services for Q4 2024."
    }
  ],
  "questions": [
    "What is the total amount due?",
    "Are there any late payment penalties?",
    "What is the service period covered?"
  ],
  "has_ai_content": true,
  "ai_content_size": 2450,
  "updated_at": "2025-08-15T10:12:36.993659"
}
```

**Example Request:**
```bash
curl -X GET "http://localhost:8000/api/v1/documents/doc123/ai-content" \\
  -H "Authorization: Bearer <session_token>"
```

**Use Cases:**
- **Content Preview**: Display AI-generated insights in document viewers
- **Search Enhancement**: Use questions for improved document search
- **Quick Reference**: Show FAQ for common document questions
- **Content Management**: Check AI content status before updates
- **Quality Assurance**: Review AI-generated content for accuracy

**AI Content Availability:**
- `has_ai_content`: Boolean flag indicating if any AI content exists
- `ai_content_size`: Total size of all AI content fields combined
- Individual fields may be null/empty even when has_ai_content is true
- Content is generated through document processing or manual updates""",
    responses={
        200: {
            "description": "AI content retrieved successfully",
            "content": {
                "application/json": {
                    "examples": {
                        "with_content": {
                            "summary": "Document with AI content",
                            "value": {
                                "document_id": "78258b82-db53-41a3-848a-ce45a32f99c7",
                                "filename": "invoice-2025-001.pdf",
                                "summary": "This invoice covers Q4 2024 services...",
                                "faq": [
                                    {
                                        "question": "What is the payment due date?",
                                        "answer": "Payment is due within 30 days."
                                    }
                                ],
                                "questions": [
                                    "What is the total amount due?",
                                    "What services were provided?"
                                ],
                                "has_ai_content": True,
                                "ai_content_size": 1250,
                                "updated_at": "2025-08-15T10:12:36.993659"
                            }
                        },
                        "no_content": {
                            "summary": "Document without AI content",
                            "value": {
                                "document_id": "abc12345-def6-789a-bcde-123456789abc",
                                "filename": "document.pdf",
                                "summary": None,
                                "faq": [],
                                "questions": [],
                                "has_ai_content": False,
                                "ai_content_size": 0,
                                "updated_at": "2025-08-15T10:12:36.993659"
                            }
                        }
                    }
                }
            }
        },
        404: {
            "description": "Document not found",
            "content": {
                "application/json": {
                    "example": {"detail": "Document not found"}
                }
            }
        },
        500: {
            "description": "Server error retrieving AI content",
            "content": {
                "application/json": {
                    "example": {"detail": "An error occurred while retrieving AI content"}
                }
            }
        }
    }
)
async def get_document_ai_content(
    document_id: str,
    user_context: Dict[str, str] = Depends(get_user_context),
    deps = Depends(get_document_dependencies)
) -> DocumentAIContentResponse:
    """
    Get AI-generated content for a document.
    
    Retrieves all available AI-generated content including summary, FAQ items,
    and questions with metadata about content availability and freshness.
    """
    document_service = deps["document_service"]
    org_id = user_context["org_id"]
    
    try:
        log_operation_start("AI content retrieval", document_id=document_id, **user_context)
        
        # Get AI content using DocumentService
        ai_content = await document_service.get_document_ai_content(
            org_id=org_id,
            document_id=document_id
        )
        
        log_operation_success(
            "AI content retrieval",
            document_id=document_id,
            has_summary=ai_content["summary"] is not None,
            faq_count=len(ai_content["faq"]),
            question_count=len(ai_content["questions"]),
            **user_context
        )
        
        return DocumentAIContentResponse(**ai_content)
        
    except DocumentNotFoundError as e:
        raise handle_document_not_found_error(e, "AI content retrieval", **user_context)
    except Exception as e:
        raise handle_generic_error(e, "AI content retrieval", **user_context)


@router.patch(
    "/{document_id}/ai-content",
    response_model=DocumentResponse,
    summary="🤖 Update AI Content",
    description="""Update AI-generated content fields for a document.

**Authentication Required:** Session token in `Authorization: Bearer <token>` header

**Path Parameters:**
- `document_id`: Document unique identifier

**Request Body:** Any combination of AI content fields:
- `summary`: AI-generated document summary (string, optional)
- `faq`: List of FAQ items with question/answer structure (optional)
- `questions`: List of questions extracted from document (optional)

**Features:**
- **Partial Updates**: Only provided fields are updated, others remain unchanged
- **Validation**: FAQ structure validation and content size limits enforced
- **Atomic Operation**: All updates succeed together or all fail
- **Metadata Tracking**: Update timestamps and content size automatically managed
- **Content Limits**: Size limits enforced per field and total AI content

**FAQ Structure:**
Each FAQ item must have:
- `question`: String containing the question text
- `answer`: String containing the answer text

**Example Request:**
```bash
curl -X PATCH "http://localhost:8000/api/v1/documents/doc123/ai-content" \\
  -H "Authorization: Bearer <session_token>" \\
  -H "Content-Type: application/json" \\
  -d '{
    "summary": "This document covers quarterly sales data with key performance metrics and insights.",
    "faq": [
      {
        "question": "What was the total revenue for Q4?",
        "answer": "$2.5M total revenue, representing 15% growth over Q3."
      },
      {
        "question": "Which product line performed best?",
        "answer": "Enterprise solutions showed 25% growth, leading all segments."
      }
    ],
    "questions": [
      "What are the key performance indicators?",
      "How did Q4 compare to previous quarters?",
      "What are the revenue projections for next year?"
    ]
  }'
```

**Content Size Limits:**
- **Summary**: Maximum 10KB per summary
- **FAQ**: Maximum 5KB total for all FAQ items
- **Questions**: Maximum 3KB total for all questions
- **Total AI Content**: Maximum 15KB combined

**Use Cases:**
- **Manual Content Creation**: Add human-curated summaries and FAQ
- **AI Content Refinement**: Update auto-generated content with corrections
- **Content Management**: Maintain accurate, up-to-date document insights
- **Workflow Integration**: Update content as part of document processing pipelines
- **Quality Control**: Replace low-quality AI content with manually reviewed versions

**Response:**
Returns the complete updated document with all fields including the new AI content.""",
    responses={
        200: {
            "description": "AI content updated successfully",
            "content": {
                "application/json": {
                    "example": {
                        "id": "78258b82-db53-41a3-848a-ce45a32f99c7",
                        "filename": "invoice-2025-001.pdf",
                        "summary": "Updated summary content...",
                        "faq": [
                            {
                                "question": "What is the payment due date?",
                                "answer": "Payment is due within 30 days."
                            }
                        ],
                        "questions": [
                            "What is the total amount due?",
                            "What services were provided?"
                        ],
                        "updated_at": "2025-08-15T10:12:36.993659"
                    }
                }
            }
        },
        400: {
            "description": "Validation error",
            "content": {
                "application/json": {
                    "examples": {
                        "invalid_faq": {
                            "summary": "Invalid FAQ structure",
                            "value": {"detail": "FAQ items must have both 'question' and 'answer' fields"}
                        },
                        "content_too_large": {
                            "summary": "Content size limit exceeded",
                            "value": {"detail": "Summary content exceeds maximum size limit of 10KB"}
                        },
                        "empty_request": {
                            "summary": "No content provided",
                            "value": {"detail": "At least one AI content field (summary, faq, or questions) must be provided"}
                        }
                    }
                }
            }
        },
        404: {
            "description": "Document not found",
            "content": {
                "application/json": {
                    "example": {"detail": "Document not found"}
                }
            }
        },
        500: {
            "description": "Server error updating AI content",
            "content": {
                "application/json": {
                    "example": {"detail": "An error occurred while updating AI content"}
                }
            }
        }
    }
)
async def update_document_ai_content(
    document_id: str,
    request: DocumentAIContentRequest,
    user_context: Dict[str, str] = Depends(get_user_context),
    deps = Depends(get_document_dependencies)
) -> DocumentResponse:
    """
    Update AI-generated content for a document.
    
    Performs partial updates of AI content fields with comprehensive validation,
    size limits, and atomic operation guarantees. All provided fields are
    validated before any updates are made.
    """
    document_service = deps["document_service"]
    org_id = user_context["org_id"]
    
    try:
        # Validate that at least one field is provided
        if not any([
            request.summary is not None,
            request.faq is not None and len(request.faq) > 0,
            request.questions is not None and len(request.questions) > 0
        ]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one AI content field (summary, faq, or questions) must be provided"
            )
        
        log_operation_start(
            "AI content update",
            document_id=document_id,
            has_summary=request.summary is not None,
            has_faq=request.faq is not None and len(request.faq) > 0,
            has_questions=request.questions is not None and len(request.questions) > 0,
            **user_context
        )
        
        # Update AI content using DocumentService
        updated_document = await document_service.update_document_ai_content(
            org_id=org_id,
            document_id=document_id,
            summary=request.summary,
            faq=request.faq,
            questions=request.questions
        )
        
        log_operation_success(
            "AI content update",
            document_id=document_id,
            has_ai_content=updated_document.has_ai_content,
            ai_content_size=updated_document.ai_content_size,
            **user_context
        )
        
        return updated_document
        
    except DocumentNotFoundError as e:
        raise handle_document_not_found_error(e, "AI content update", **user_context)
    except Exception as e:
        raise handle_generic_error(e, "AI content update", **user_context)


