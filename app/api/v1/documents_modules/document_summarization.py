"""
Document Summarization Endpoints - Simplified Implementation.

This module provides simplified AI-powered document summarization endpoints:
- Generate summaries from document content
- Retrieve existing summaries
- Update/regenerate summaries with custom prompts
- Simple, focused approach following your requirements
"""

from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.models.schemas import (
    DocumentSummarizeRequest,
    DocumentSummarizeResponse,
    DocumentSummaryUpdateRequest,
    DocumentSummaryResponse,
)
from app.services.document.document_ai_service import (
    document_ai_service,
    ContentNotFoundError,
    SummarizationError,
)
from app.services.document_service import DocumentNotFoundError, DocumentValidationError
from app.core.simple_auth import get_current_user_dict
from app.core.logging import get_api_logger

logger = get_api_logger()
router = APIRouter()


@router.post(
    "/summarize",
    response_model=DocumentSummarizeResponse,
    summary="🤖 Generate AI Summary",
    description="""Generate an AI-powered summary for a document by filename.
    
**Authentication Required:** Session token in `Authorization: Bearer <token>` header
    
**Query Parameters:**
- `file_name`: The filename of the document to summarize (e.g., "Sample2.pdf")

**Requirements:**
- Document must exist in your organization
- Document must have been parsed (file_content field populated)
- Document must be active (not deleted)

**Custom Prompts:**
You can optionally provide a custom prompt to guide the summarization:
- Brief summary: "Create a brief executive summary highlighting only the most critical points."
- Technical focus: "Focus on technical specifications, requirements, and implementation details."
- Business focus: "Emphasize business implications, costs, and strategic decisions."

**Example Request:**
```bash
curl -X POST "http://localhost:8000/api/v1/documents/summarize?file_name=Sample2.pdf" \\
  -H "Authorization: Bearer <session_token>" \\
  -H "Content-Type: application/json" \\
  -d '{"prompt": "Create a brief executive summary"}'
```

**Response:**
- Summary is stored in Firestore `ai_summary` field
- No GCS file storage required
- Immediate access to generated content
- Includes generation metadata (model, timing, etc.)
    """,
    status_code=status.HTTP_201_CREATED,
)
async def generate_document_summary(
    file_name: str = Query(
        ..., description="The filename of the document to summarize"
    ),
    request: DocumentSummarizeRequest = DocumentSummarizeRequest(),
    current_user: Dict[str, Any] = Depends(get_current_user_dict),
):
    """Generate AI-powered summary for a document."""
    try:
        # Get user/org info from session
        org_id = current_user["org_id"]

        logger.info(
            "Starting document summarization",
            org_id=org_id,
            filename=file_name,
            has_custom_prompt=bool(request.prompt),
        )

        # Generate summary using AI service
        result = await document_ai_service.generate_summary_by_filename(
            org_id=org_id, filename=file_name, custom_prompt=request.prompt
        )

        # Log the complete AI service response for debugging
        logger.debug(
            "AI service response structure",
            org_id=org_id,
            filename=file_name,
            result_keys=list(result.keys()) if isinstance(result, dict) else "not_dict",
            result_structure=(
                {k: type(v).__name__ for k, v in result.items()}
                if isinstance(result, dict)
                else "invalid"
            ),
        )

        # Validate and create response with detailed error handling
        try:
            response = DocumentSummarizeResponse(**result)
        except Exception as validation_error:
            logger.error(
                "Failed to create DocumentSummarizeResponse",
                org_id=org_id,
                filename=file_name,
                validation_error=str(validation_error),
                ai_service_result=(
                    result
                    if len(str(result)) < 1000
                    else f"result_too_large_{len(str(result))}_chars"
                ),
                result_keys=(
                    list(result.keys()) if isinstance(result, dict) else "not_dict"
                ),
            )

            # Return a formatted error response
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Response validation failed: {str(validation_error)}",
            )

        logger.info(
            "Document summarization completed successfully",
            org_id=org_id,
            filename=file_name,
            summary_length=len(result.get("ai_summary", "")),
        )

        return response

    except DocumentNotFoundError as e:
        logger.warning(
            "Document not found for summarization",
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
            "Document has no content for summarization",
            org_id=org_id,
            filename=file_name,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Document '{file_name}' has no parsed content. Please parse the document first.",
        )

    except SummarizationError as e:
        logger.error(
            "Summarization failed", org_id=org_id, filename=file_name, error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate summary: {str(e)}",
        )

    except Exception as e:
        logger.error(
            "Unexpected error during summarization",
            org_id=org_id,
            filename=file_name,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while generating document summary",
        )


@router.get(
    "/summarize",
    response_model=DocumentSummaryResponse,
    summary="📄 Get Document Summary",
    description="""Retrieve existing AI summary for a document by filename.
    
**Authentication Required:** Session token in `Authorization: Bearer <token>` header
    
**Query Parameters:**
- `file_name`: The filename of the document to retrieve summary for (e.g., "Sample2.pdf")

**Example Request:**
```bash
curl -X GET "http://localhost:8000/api/v1/documents/summarize?file_name=Sample2.pdf" \\
  -H "Authorization: Bearer <session_token>"
```

**Response includes:**
- Current AI summary content (if available)
- Summary metadata (generation time, model used, etc.)
- Summary preview (first 150 characters)
- Whether document has a summary available
    """,
    status_code=status.HTTP_200_OK,
)
async def get_document_summary(
    file_name: str = Query(
        ..., description="The filename of the document to retrieve summary for"
    ),
    current_user: Dict[str, Any] = Depends(get_current_user_dict),
):
    """Get existing AI summary for a document."""
    try:
        # Get user/org info from session
        org_id = current_user["org_id"]

        logger.debug("Retrieving document summary", org_id=org_id, filename=file_name)

        # Get summary using AI service
        result = await document_ai_service.get_summary_by_filename(
            org_id=org_id, filename=file_name
        )

        response = DocumentSummaryResponse(**result)

        logger.debug(
            "Document summary retrieved successfully",
            org_id=org_id,
            filename=file_name,
            has_summary=result.get("has_summary", False),
        )

        return response

    except DocumentNotFoundError as e:
        logger.warning(
            "Document not found for summary retrieval",
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
            "Error retrieving document summary",
            org_id=org_id,
            filename=file_name,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving document summary",
        )


@router.put(
    "/summarize",
    response_model=DocumentSummarizeResponse,
    summary="✏️ Update Document Summary",
    description="""Update or regenerate AI summary for a document.
    
**Authentication Required:** Session token in `Authorization: Bearer <token>` header
    
**Query Parameters:**
- `file_name`: The filename of the document to update summary for (e.g., "Sample2.pdf")

**Two update modes:**
1. **Direct Update**: Provide `summary` field with new content
2. **Regenerate**: Provide `prompt` field to regenerate with custom prompt

**Example Requests:**
```bash
# Direct update
curl -X PUT "http://localhost:8000/api/v1/documents/summarize?file_name=Sample2.pdf" \\
  -H "Authorization: Bearer <session_token>" \\
  -H "Content-Type: application/json" \\
  -d '{"summary": "This document discusses..."}'

# Regenerate with custom prompt
curl -X PUT "http://localhost:8000/api/v1/documents/summarize?file_name=Sample2.pdf" \\
  -H "Authorization: Bearer <session_token>" \\
  -H "Content-Type: application/json" \\
  -d '{"prompt": "Create a technical summary focusing on implementation details"}'
```

**Note:** You must provide either `summary` OR `prompt`, not both.
    """,
    status_code=status.HTTP_200_OK,
)
async def update_document_summary(
    request: DocumentSummaryUpdateRequest,
    file_name: str = Query(
        ..., description="The filename of the document to update summary for"
    ),
    current_user: Dict[str, Any] = Depends(get_current_user_dict),
):
    """Update or regenerate AI summary for a document."""
    try:
        # Get user/org info from session
        org_id = current_user["org_id"]

        # Validate that either summary or prompt is provided
        if not request.summary and not request.prompt:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Either 'summary' or 'prompt' must be provided",
            )

        if request.summary and request.prompt:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Provide either 'summary' OR 'prompt', not both",
            )

        logger.info(
            "Updating document summary",
            org_id=org_id,
            filename=file_name,
            update_type="direct" if request.summary else "regenerate",
        )

        # Update summary using AI service
        result = await document_ai_service.update_summary_by_filename(
            org_id=org_id,
            filename=file_name,
            summary=request.summary,
            custom_prompt=request.prompt,
        )

        # Log the complete AI service response for debugging
        logger.debug(
            "AI service update response structure",
            org_id=org_id,
            filename=file_name,
            result_keys=list(result.keys()) if isinstance(result, dict) else "not_dict",
            result_structure=(
                {k: type(v).__name__ for k, v in result.items()}
                if isinstance(result, dict)
                else "invalid"
            ),
        )

        # Validate and create response with detailed error handling
        try:
            response = DocumentSummarizeResponse(**result)
        except Exception as validation_error:
            logger.error(
                "Failed to create DocumentSummarizeResponse during update",
                org_id=org_id,
                filename=file_name,
                validation_error=str(validation_error),
                ai_service_result=(
                    result
                    if len(str(result)) < 1000
                    else f"result_too_large_{len(str(result))}_chars"
                ),
                result_keys=(
                    list(result.keys()) if isinstance(result, dict) else "not_dict"
                ),
            )

            # Return a formatted error response
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Response validation failed during update: {str(validation_error)}",
            )

        logger.info(
            "Document summary updated successfully",
            org_id=org_id,
            filename=file_name,
            summary_length=len(result.get("ai_summary", "")),
        )

        return response

    except DocumentNotFoundError as e:
        logger.warning(
            "Document not found for summary update",
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
            "Invalid request for summary update",
            org_id=org_id,
            filename=file_name,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )

    except ContentNotFoundError as e:
        logger.warning(
            "Document has no content for summary regeneration",
            org_id=org_id,
            filename=file_name,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Document '{file_name}' has no parsed content. Cannot regenerate summary.",
        )

    except SummarizationError as e:
        logger.error(
            "Summary update failed", org_id=org_id, filename=file_name, error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update summary: {str(e)}",
        )

    except Exception as e:
        logger.error(
            "Unexpected error during summary update",
            org_id=org_id,
            filename=file_name,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating document summary",
        )
