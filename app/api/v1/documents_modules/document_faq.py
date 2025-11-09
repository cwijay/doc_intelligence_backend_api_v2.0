"""
Document FAQ Endpoints - LangChain-based Implementation.

This module provides AI-powered document FAQ generation endpoints:
- Generate FAQs with custom count and prompts
- Retrieve existing FAQs  
- Update/regenerate FAQs with custom parameters
- LangChain integration for robust FAQ generation
"""

from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.models.schemas import (
    DocumentFAQRequest,
    DocumentFAQResponse,
    DocumentFAQUpdateRequest,
    DocumentFAQRetrievalResponse
)
from app.services.document.document_ai_service import (
    document_ai_service,
    DocumentFAQError,
    FAQGenerationError,
    ContentNotFoundError
)
from app.services.document_service import (
    DocumentNotFoundError,
    DocumentValidationError
)
from app.core.simple_auth import get_current_user_dict
from app.core.logging import get_api_logger

logger = get_api_logger()
router = APIRouter()


@router.post(
    "/faq",
    response_model=DocumentFAQResponse,
    summary="🤖 Generate AI FAQ",
    description="""Generate AI-powered FAQ items for a document by filename using LangChain.
    
**Authentication Required:** Session token in `Authorization: Bearer <token>` header
    
**Query Parameters:**
- `file_name`: The filename of the document to generate FAQ for (e.g., "Sample2.pdf")

**Request Body (Optional):**
- `prompt`: Custom prompt to guide FAQ generation (optional)
- `faq_count`: Number of FAQ items to generate (1-10, default: 5)

**Requirements:**
- Document must exist in your organization
- Document must have been parsed (file_content field populated)
- Document must be active (not deleted)

**Custom Prompts:**
You can optionally provide a custom prompt to guide FAQ generation:
- Technical focus: "Generate FAQs focusing on technical specifications and implementation details."
- Business focus: "Create FAQs emphasizing business implications, costs, and strategic decisions."
- User-focused: "Generate FAQs that end users would commonly ask about this document."

**FAQ Count:**
- Minimum: 1 FAQ item
- Maximum: 10 FAQ items
- Default: 5 FAQ items if not specified

**Example Request:**
```bash
curl -X POST "http://localhost:8000/api/v1/documents/faq?file_name=Sample2.pdf" \\
  -H "Authorization: Bearer <session_token>" \\
  -H "Content-Type: application/json" \\
  -d '{"prompt": "Focus on technical aspects", "faq_count": 7}'
```

**Response:**
- FAQ items stored in Firestore `ai_faq` field
- Each FAQ item contains 'question' and 'answer' fields
- Immediate access to generated content
- Includes generation metadata (model, timing, count, etc.)
- LangChain-powered generation for higher quality results
    """,
    status_code=status.HTTP_201_CREATED
)
async def generate_document_faq(
    file_name: str = Query(..., description="The filename of the document to generate FAQ for"),
    request: DocumentFAQRequest = DocumentFAQRequest(),
    current_user: Dict[str, Any] = Depends(get_current_user_dict)
):
    """Generate AI-powered FAQ for a document using LangChain."""
    try:
        # Get user/org info from session
        org_id = current_user["org_id"]
        
        logger.info("Starting document FAQ generation", 
                   org_id=org_id,
                   filename=file_name,
                   faq_count=request.faq_count,
                   has_custom_prompt=bool(request.prompt))
        
        # Generate FAQ using AI service
        result = await document_ai_service.generate_faq_by_filename(
            org_id=org_id,
            filename=file_name,
            faq_count=request.faq_count,
            custom_prompt=request.prompt
        )
        
        response = DocumentFAQResponse(**result)
        
        logger.info("Document FAQ generation completed successfully", 
                   org_id=org_id,
                   filename=file_name,
                   faq_count=len(result.get("ai_faq", [])))
        
        return response
        
    except DocumentNotFoundError as e:
        logger.warning("Document not found for FAQ generation", 
                      org_id=org_id,
                      filename=file_name,
                      error=str(e))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with filename '{file_name}' not found"
        )
        
    except ContentNotFoundError as e:
        logger.warning("Document has no content for FAQ generation", 
                      org_id=org_id,
                      filename=file_name,
                      error=str(e))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Document '{file_name}' has no parsed content. Please parse the document first."
        )
        
    except FAQGenerationError as e:
        logger.error("FAQ generation failed", 
                    org_id=org_id,
                    filename=file_name,
                    error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate FAQ: {str(e)}"
        )
        
    except Exception as e:
        logger.error("Unexpected error during FAQ generation", 
                    org_id=org_id,
                    filename=file_name,
                    error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while generating document FAQ"
        )


@router.get(
    "/faq",
    response_model=DocumentFAQRetrievalResponse,
    summary="📄 Get Document FAQ",
    description="""Retrieve existing AI-generated FAQ for a document by filename.
    
**Authentication Required:** Session token in `Authorization: Bearer <token>` header
    
**Query Parameters:**
- `file_name`: The filename of the document to retrieve FAQ for (e.g., "Sample2.pdf")

**Example Request:**
```bash
curl -X GET "http://localhost:8000/api/v1/documents/faq?file_name=Sample2.pdf" \\
  -H "Authorization: Bearer <session_token>"
```

**Response includes:**
- Current AI FAQ items (if available)
- FAQ metadata (generation time, model used, count, etc.)
- FAQ preview (first question and partial answer)
- FAQ count and availability status
- Whether document has FAQ available
    """,
    status_code=status.HTTP_200_OK
)
async def get_document_faq(
    file_name: str = Query(..., description="The filename of the document to retrieve FAQ for"),
    current_user: Dict[str, Any] = Depends(get_current_user_dict)
):
    """Get existing AI FAQ for a document."""
    try:
        # Get user/org info from session
        org_id = current_user["org_id"]
        
        logger.debug("Retrieving document FAQ", 
                    org_id=org_id,
                    filename=file_name)
        
        # Get FAQ using AI service
        result = await document_ai_service.get_faq_by_filename(
            org_id=org_id,
            filename=file_name
        )
        
        response = DocumentFAQRetrievalResponse(**result)
        
        logger.debug("Document FAQ retrieved successfully", 
                    org_id=org_id,
                    filename=file_name,
                    has_faq=result.get("has_faq", False))
        
        return response
        
    except DocumentNotFoundError as e:
        logger.warning("Document not found for FAQ retrieval", 
                      org_id=org_id,
                      filename=file_name,
                      error=str(e))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with filename '{file_name}' not found"
        )
        
    except Exception as e:
        logger.error("Error retrieving document FAQ", 
                    org_id=org_id,
                    filename=file_name,
                    error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving document FAQ"
        )


@router.put(
    "/faq",
    response_model=DocumentFAQResponse,
    summary="✏️ Update Document FAQ",
    description="""Update or regenerate AI FAQ for a document.
    
**Authentication Required:** Session token in `Authorization: Bearer <token>` header
    
**Query Parameters:**
- `file_name`: The filename of the document to update FAQ for (e.g., "Sample2.pdf")

**Three update modes:**
1. **Direct Update**: Provide `faq` field with new FAQ items
2. **Regenerate**: Provide `prompt` field to regenerate with custom prompt
3. **Regenerate with Count**: Provide both `prompt` and `faq_count` for custom FAQ count

**Example Requests:**
```bash
# Direct update with specific FAQ items
curl -X PUT "http://localhost:8000/api/v1/documents/faq?file_name=Sample2.pdf" \\
  -H "Authorization: Bearer <session_token>" \\
  -H "Content-Type: application/json" \\
  -d '{
    "faq": [
      {"question": "What is this document about?", "answer": "This document discusses..."},
      {"question": "Who should read this?", "answer": "This is intended for..."}
    ]
  }'

# Regenerate with custom prompt and count
curl -X PUT "http://localhost:8000/api/v1/documents/faq?file_name=Sample2.pdf" \\
  -H "Authorization: Bearer <session_token>" \\
  -H "Content-Type: application/json" \\
  -d '{
    "prompt": "Create FAQs focusing on implementation details",
    "faq_count": 8
  }'
```

**Note:** You must provide either `faq` OR (`prompt` with optional `faq_count`), not both.
    """,
    status_code=status.HTTP_200_OK
)
async def update_document_faq(
    request: DocumentFAQUpdateRequest,
    file_name: str = Query(..., description="The filename of the document to update FAQ for"),
    current_user: Dict[str, Any] = Depends(get_current_user_dict)
):
    """Update or regenerate AI FAQ for a document."""
    try:
        # Get user/org info from session
        org_id = current_user["org_id"]
        
        # Validate that either FAQ or prompt is provided
        if not request.faq and not request.prompt:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Either 'faq' or 'prompt' must be provided"
            )
        
        if request.faq and request.prompt:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Provide either 'faq' OR 'prompt', not both"
            )
        
        logger.info("Updating document FAQ", 
                   org_id=org_id,
                   filename=file_name,
                   update_type="direct" if request.faq else "regenerate")
        
        # Update FAQ using AI service
        result = await document_ai_service.update_faq_by_filename(
            org_id=org_id,
            filename=file_name,
            faq=request.faq,
            custom_prompt=request.prompt,
            faq_count=request.faq_count
        )
        
        response = DocumentFAQResponse(**result)
        
        logger.info("Document FAQ updated successfully", 
                   org_id=org_id,
                   filename=file_name,
                   update_type=result.get("update_type"),
                   faq_count=len(result.get("ai_faq", [])))
        
        return response
        
    except DocumentNotFoundError as e:
        logger.warning("Document not found for FAQ update", 
                      org_id=org_id,
                      filename=file_name,
                      error=str(e))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with filename '{file_name}' not found"
        )
        
    except DocumentValidationError as e:
        logger.warning("Invalid request for FAQ update", 
                      org_id=org_id,
                      filename=file_name,
                      error=str(e))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )
        
    except ContentNotFoundError as e:
        logger.warning("Document has no content for FAQ regeneration", 
                      org_id=org_id,
                      filename=file_name,
                      error=str(e))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Document '{file_name}' has no parsed content. Cannot regenerate FAQ."
        )
        
    except FAQGenerationError as e:
        logger.error("FAQ update failed", 
                    org_id=org_id,
                    filename=file_name,
                    error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update FAQ: {str(e)}"
        )
        
    except Exception as e:
        logger.error("Unexpected error during FAQ update", 
                    org_id=org_id,
                    filename=file_name,
                    error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating document FAQ"
        )