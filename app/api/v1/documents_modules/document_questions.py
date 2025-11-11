"""
Document Questions Endpoints - LangChain-based Implementation.

This module provides AI-powered document questions generation endpoints:
- Generate questions with custom count and prompts
- Retrieve existing questions
- Update/regenerate questions with custom parameters
- LangChain integration for robust question generation
"""

from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.models.schemas import (
    DocumentQuestionsRequest,
    DocumentQuestionsResponse,
    DocumentQuestionsUpdateRequest,
    DocumentQuestionsRetrievalResponse,
)
from app.services.document.document_ai_service import (
    document_ai_service,
    QuestionsGenerationError,
    ContentNotFoundError,
)
from app.services.document_service import DocumentNotFoundError, DocumentValidationError
from app.core.simple_auth import get_current_user_dict
from app.core.logging import get_api_logger

logger = get_api_logger()
router = APIRouter()


@router.post(
    "/questions",
    response_model=DocumentQuestionsResponse,
    summary="🤖 Generate AI Questions",
    description="""Generate AI-powered questions for a document by filename using LangChain.
    
**Authentication Required:** Session token in `Authorization: Bearer <token>` header
    
**Query Parameters:**
- `file_name`: The filename of the document to generate questions for (e.g., "Sample2.pdf")

**Request Body (Optional):**
- `prompt`: Custom prompt to guide question generation (optional)
- `question_count`: Number of questions to generate (1-20, default: 5)

**Requirements:**
- Document must exist in your organization
- Document must have been parsed (file_content field populated)
- Document must be active (not deleted)

**Custom Prompts:**
You can optionally provide a custom prompt to guide question generation:
- Educational focus: "Generate questions suitable for testing comprehension of this material."
- Discussion focus: "Create questions that would spark meaningful discussion about this topic."
- Analysis focus: "Generate questions that encourage critical analysis of the content."

**Question Count:**
- Minimum: 1 question
- Maximum: 20 questions
- Default: 5 questions if not specified

**Example Request:**
```bash
curl -X POST "http://localhost:8000/api/v1/documents/questions?file_name=Sample2.pdf" \\
  -H "Authorization: Bearer <session_token>" \\
  -H "Content-Type: application/json" \\
  -d '{"prompt": "Focus on key concepts for understanding", "question_count": 8}'
```

**Response:**
- Questions stored in Firestore `ai_questions` field
- Each question is a string in the questions array
- Immediate access to generated content
- Includes generation metadata (model, timing, count, etc.)
- LangChain-powered generation for higher quality results
    """,
    status_code=status.HTTP_201_CREATED,
)
async def generate_document_questions(
    file_name: str = Query(
        ..., description="The filename of the document to generate questions for"
    ),
    request: DocumentQuestionsRequest = DocumentQuestionsRequest(),
    current_user: Dict[str, Any] = Depends(get_current_user_dict),
):
    """Generate AI-powered questions for a document using LangChain."""
    try:
        # Get user/org info from session
        org_id = current_user["org_id"]

        logger.info(
            "Starting document questions generation",
            org_id=org_id,
            filename=file_name,
            question_count=request.question_count,
            has_custom_prompt=bool(request.prompt),
        )

        # Generate questions using AI service
        result = await document_ai_service.generate_questions_by_filename(
            org_id=org_id,
            filename=file_name,
            question_count=request.question_count,
            custom_prompt=request.prompt,
        )

        response = DocumentQuestionsResponse(**result)

        logger.info(
            "Document questions generation completed successfully",
            org_id=org_id,
            filename=file_name,
            question_count=len(result.get("ai_questions", [])),
        )

        return response

    except DocumentNotFoundError as e:
        logger.warning(
            "Document not found for questions generation",
            org_id=org_id,
            filename=file_name,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with filename '{file_name}' not found",
        )

    except ContentNotFoundError as e:
        logger.warning(
            "Document has no content for questions generation",
            org_id=org_id,
            filename=file_name,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Document '{file_name}' has no parsed content. Please parse the document first.",
        )

    except QuestionsGenerationError as e:
        logger.error(
            "Questions generation failed",
            org_id=org_id,
            filename=file_name,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate questions: {str(e)}",
        )

    except Exception as e:
        logger.error(
            "Unexpected error during questions generation",
            org_id=org_id,
            filename=file_name,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while generating document questions",
        )


@router.get(
    "/questions",
    response_model=DocumentQuestionsRetrievalResponse,
    summary="📄 Get Document Questions",
    description="""Retrieve existing AI-generated questions for a document by filename.
    
**Authentication Required:** Session token in `Authorization: Bearer <token>` header
    
**Query Parameters:**
- `file_name`: The filename of the document to retrieve questions for (e.g., "Sample2.pdf")

**Example Request:**
```bash
curl -X GET "http://localhost:8000/api/v1/documents/questions?file_name=Sample2.pdf" \\
  -H "Authorization: Bearer <session_token>"
```

**Response includes:**
- Current AI questions (if available)
- Questions metadata (generation time, model used, count, etc.)
- Questions preview (first 3 questions)
- Questions count and availability status
- Whether document has questions available
    """,
    status_code=status.HTTP_200_OK,
)
async def get_document_questions(
    file_name: str = Query(
        ..., description="The filename of the document to retrieve questions for"
    ),
    current_user: Dict[str, Any] = Depends(get_current_user_dict),
):
    """Get existing AI questions for a document."""
    try:
        # Get user/org info from session
        org_id = current_user["org_id"]

        logger.debug("Retrieving document questions", org_id=org_id, filename=file_name)

        # Get questions using AI service
        result = await document_ai_service.get_questions_by_filename(
            org_id=org_id, filename=file_name
        )

        response = DocumentQuestionsRetrievalResponse(**result)

        logger.debug(
            "Document questions retrieved successfully",
            org_id=org_id,
            filename=file_name,
            has_questions=result.get("has_questions", False),
        )

        return response

    except DocumentNotFoundError as e:
        logger.warning(
            "Document not found for questions retrieval",
            org_id=org_id,
            filename=file_name,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with filename '{file_name}' not found",
        )

    except Exception as e:
        logger.error(
            "Error retrieving document questions",
            org_id=org_id,
            filename=file_name,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving document questions",
        )


@router.put(
    "/questions",
    response_model=DocumentQuestionsResponse,
    summary="✏️ Update Document Questions",
    description="""Update or regenerate AI questions for a document.
    
**Authentication Required:** Session token in `Authorization: Bearer <token>` header
    
**Query Parameters:**
- `file_name`: The filename of the document to update questions for (e.g., "Sample2.pdf")

**Three update modes:**
1. **Direct Update**: Provide `questions` field with new questions list
2. **Regenerate**: Provide `prompt` field to regenerate with custom prompt
3. **Regenerate with Count**: Provide both `prompt` and `question_count` for custom question count

**Example Requests:**
```bash
# Direct update with specific questions
curl -X PUT "http://localhost:8000/api/v1/documents/questions?file_name=Sample2.pdf" \\
  -H "Authorization: Bearer <session_token>" \\
  -H "Content-Type: application/json" \\
  -d '{
    "questions": [
      "What is the main purpose of this document?",
      "Who is the intended audience?",
      "What are the key takeaways?"
    ]
  }'

# Regenerate with custom prompt and count
curl -X PUT "http://localhost:8000/api/v1/documents/questions?file_name=Sample2.pdf" \\
  -H "Authorization: Bearer <session_token>" \\
  -H "Content-Type: application/json" \\
  -d '{
    "prompt": "Create questions focusing on practical applications",
    "question_count": 10
  }'
```

**Note:** You must provide either `questions` OR (`prompt` with optional `question_count`), not both.
    """,
    status_code=status.HTTP_200_OK,
)
async def update_document_questions(
    request: DocumentQuestionsUpdateRequest,
    file_name: str = Query(
        ..., description="The filename of the document to update questions for"
    ),
    current_user: Dict[str, Any] = Depends(get_current_user_dict),
):
    """Update or regenerate AI questions for a document."""
    try:
        # Get user/org info from session
        org_id = current_user["org_id"]

        # Validate that either questions or prompt is provided
        if request.questions is None and not request.prompt:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Either 'questions' or 'prompt' must be provided",
            )

        if request.questions is not None and request.prompt:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Provide either 'questions' OR 'prompt', not both",
            )

        logger.info(
            "Updating document questions",
            org_id=org_id,
            filename=file_name,
            update_type="direct" if request.questions else "regenerate",
        )

        # Update questions using AI service
        result = await document_ai_service.update_questions_by_filename(
            org_id=org_id,
            filename=file_name,
            questions=request.questions,
            custom_prompt=request.prompt,
            question_count=request.question_count,
        )

        response = DocumentQuestionsResponse(**result)

        logger.info(
            "Document questions updated successfully",
            org_id=org_id,
            filename=file_name,
            update_type=result.get("update_type"),
            question_count=len(result.get("ai_questions", [])),
        )

        return response

    except DocumentNotFoundError as e:
        logger.warning(
            "Document not found for questions update",
            org_id=org_id,
            filename=file_name,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with filename '{file_name}' not found",
        )

    except DocumentValidationError as e:
        logger.warning(
            "Invalid request for questions update",
            org_id=org_id,
            filename=file_name,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )

    except ContentNotFoundError as e:
        logger.warning(
            "Document has no content for questions regeneration",
            org_id=org_id,
            filename=file_name,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Document '{file_name}' has no parsed content. Cannot regenerate questions.",
        )

    except QuestionsGenerationError as e:
        logger.error(
            "Questions update failed", org_id=org_id, filename=file_name, error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update questions: {str(e)}",
        )

    except HTTPException:
        raise  # Re-raise HTTPException to let FastAPI handle it properly
    except Exception as e:
        logger.error(
            "Unexpected error during questions update",
            org_id=org_id,
            filename=file_name,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating document questions",
        )
