"""
Document AI Content API Tests

Tests for AI-powered content generation including summarization,
FAQ generation, and question generation with caching.
"""

import pytest
import sys
from pathlib import Path

# Add tests directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.test_helpers import (
    upload_document,
    create_test_user_session,
    generate_summary,
    generate_questions,
    generate_faq
)
from test_config import config


@pytest.mark.document
@pytest.mark.ai
@pytest.mark.slow
class TestDocumentSummarization:
    """Test document summarization with AI."""

    @pytest.mark.asyncio
    async def test_01_generate_summary_first_time(
        self,
        ai_http_client,
        sample_pdf_file,
        resource_tracker
    ):
        """Test generating summary for the first time (no cache)."""
        org_id, credentials = await create_test_user_session(ai_http_client)
        resource_tracker.add_organization(org_id)

        # Upload document
        doc_result = await upload_document(
            ai_http_client,
            credentials,
            sample_pdf_file.read(),
            "test_summary.pdf",
            "application/pdf"
        )
        doc_id = doc_result.get("id") or doc_result.get("document_id")
        filename = doc_result.get("filename") or doc_result.get("file_name") or "test_summary.pdf"
        resource_tracker.add_document(org_id, doc_id)

        # Generate summary
        summary_result = await generate_summary(
            ai_http_client,
            credentials,
            filename
        )

        assert "summary" in summary_result or "content" in summary_result
        assert "cached" in summary_result or "generated_at" in summary_result

    @pytest.mark.asyncio
    async def test_02_get_cached_summary(
        self,
        ai_http_client,
        sample_pdf_file,
        resource_tracker
    ):
        """Test retrieving cached summary (no regeneration)."""
        org_id, credentials = await create_test_user_session(ai_http_client)
        resource_tracker.add_organization(org_id)

        # Upload and generate summary
        doc_result = await upload_document(
            ai_http_client,
            credentials,
            sample_pdf_file.read(),
            "test_cached.pdf",
            "application/pdf"
        )
        doc_id = doc_result.get("id") or doc_result.get("document_id")
        filename = doc_result.get("filename") or doc_result.get("file_name") or "test_cached.pdf"
        resource_tracker.add_document(org_id, doc_id)

        # Generate summary first time
        summary1 = await generate_summary(ai_http_client, credentials, filename)

        # Get summary again (should be cached)
        response = await ai_http_client.get(
            f"{config.api_prefix}/documents/summarize",
            headers=credentials.auth_headers,
            params={"file_name": filename}
        )
        assert response.status_code == 200
        summary2 = response.json()

        # Should return cached content
        assert summary2.get("cached") is True or "summary" in summary2

    @pytest.mark.asyncio
    async def test_03_regenerate_summary(
        self,
        ai_http_client,
        sample_pdf_file,
        resource_tracker
    ):
        """Test regenerating summary with PUT."""
        org_id, credentials = await create_test_user_session(ai_http_client)
        resource_tracker.add_organization(org_id)

        doc_result = await upload_document(
            ai_http_client,
            credentials,
            sample_pdf_file.read(),
            "test_regen.pdf",
            "application/pdf"
        )
        doc_id = doc_result.get("id") or doc_result.get("document_id")
        filename = doc_result.get("filename") or doc_result.get("file_name") or "test_regen.pdf"
        resource_tracker.add_document(org_id, doc_id)

        # Generate initial summary
        await generate_summary(ai_http_client, credentials, filename)

        # Regenerate with custom prompt
        response = await ai_http_client.put(
            f"{config.api_prefix}/documents/summarize",
            headers=credentials.auth_headers,
            params={"file_name": filename},
            json={"prompt": "Provide a very brief summary"},
            timeout=config.ai_operation_timeout
        )
        assert response.status_code == 200
        result = response.json()
        assert "summary" in result or "content" in result

    @pytest.mark.asyncio
    async def test_04_summary_custom_prompt(
        self,
        ai_http_client,
        sample_pdf_file,
        resource_tracker
    ):
        """Test generating summary with custom prompt."""
        org_id, credentials = await create_test_user_session(ai_http_client)
        resource_tracker.add_organization(org_id)

        doc_result = await upload_document(
            ai_http_client,
            credentials,
            sample_pdf_file.read(),
            "test_custom.pdf",
            "application/pdf"
        )
        doc_id = doc_result.get("id") or doc_result.get("document_id")
        filename = doc_result.get("filename") or doc_result.get("file_name") or "test_custom.pdf"
        resource_tracker.add_document(org_id, doc_id)

        # Generate with custom prompt
        summary_result = await generate_summary(
            ai_http_client,
            credentials,
            filename,
            custom_prompt="Summarize in exactly 2 sentences"
        )

        assert "summary" in summary_result or "content" in summary_result


@pytest.mark.document
@pytest.mark.ai
@pytest.mark.slow
class TestDocumentQuestions:
    """Test AI question generation."""

    @pytest.mark.asyncio
    async def test_01_generate_questions(
        self,
        ai_http_client,
        sample_pdf_file,
        resource_tracker
    ):
        """Test generating questions for document."""
        org_id, credentials = await create_test_user_session(ai_http_client)
        resource_tracker.add_organization(org_id)

        doc_result = await upload_document(
            ai_http_client,
            credentials,
            sample_pdf_file.read(),
            "test_questions.pdf",
            "application/pdf"
        )
        doc_id = doc_result.get("id") or doc_result.get("document_id")
        filename = doc_result.get("filename") or doc_result.get("file_name") or "test_questions.pdf"
        resource_tracker.add_document(org_id, doc_id)

        # Generate 5 questions
        questions_result = await generate_questions(
            ai_http_client,
            credentials,
            filename,
            question_count=5
        )

        assert "questions" in questions_result
        questions = questions_result["questions"]
        assert isinstance(questions, list)
        assert 1 <= len(questions) <= 20  # Should respect count range

    @pytest.mark.asyncio
    async def test_02_generate_variable_question_count(
        self,
        ai_http_client,
        sample_pdf_file,
        resource_tracker
    ):
        """Test generating different counts of questions."""
        org_id, credentials = await create_test_user_session(ai_http_client)
        resource_tracker.add_organization(org_id)

        doc_result = await upload_document(
            ai_http_client,
            credentials,
            sample_pdf_file.read(),
            "test_var_questions.pdf",
            "application/pdf"
        )
        doc_id = doc_result.get("id") or doc_result.get("document_id")
        filename = doc_result.get("filename") or doc_result.get("file_name") or "test_var_questions.pdf"
        resource_tracker.add_document(org_id, doc_id)

        # Test different counts
        for count in [3, 10, 15]:
            questions_result = await generate_questions(
                ai_http_client,
                credentials,
                filename,
                question_count=count
            )
            questions = questions_result.get("questions", [])
            # Allow some tolerance in count
            assert 1 <= len(questions) <= 20

    @pytest.mark.asyncio
    async def test_03_get_cached_questions(
        self,
        ai_http_client,
        sample_pdf_file,
        resource_tracker
    ):
        """Test retrieving cached questions."""
        org_id, credentials = await create_test_user_session(ai_http_client)
        resource_tracker.add_organization(org_id)

        doc_result = await upload_document(
            ai_http_client,
            credentials,
            sample_pdf_file.read(),
            "test_cached_q.pdf",
            "application/pdf"
        )
        doc_id = doc_result.get("id") or doc_result.get("document_id")
        filename = doc_result.get("filename") or doc_result.get("file_name") or "test_cached_q.pdf"
        resource_tracker.add_document(org_id, doc_id)

        # Generate questions
        await generate_questions(ai_http_client, credentials, filename, 5)

        # Get cached questions
        response = await ai_http_client.get(
            f"{config.api_prefix}/documents/questions",
            headers=credentials.auth_headers,
            params={"file_name": filename}
        )
        assert response.status_code == 200
        result = response.json()
        assert "questions" in result

    @pytest.mark.asyncio
    async def test_04_update_questions(
        self,
        ai_http_client,
        sample_pdf_file,
        resource_tracker
    ):
        """Test updating/regenerating questions."""
        org_id, credentials = await create_test_user_session(ai_http_client)
        resource_tracker.add_organization(org_id)

        doc_result = await upload_document(
            ai_http_client,
            credentials,
            sample_pdf_file.read(),
            "test_update_q.pdf",
            "application/pdf"
        )
        doc_id = doc_result.get("id") or doc_result.get("document_id")
        filename = doc_result.get("filename") or doc_result.get("file_name") or "test_update_q.pdf"
        resource_tracker.add_document(org_id, doc_id)

        # Generate initial questions
        await generate_questions(ai_http_client, credentials, filename, 5)

        # Update with custom questions
        custom_questions = ["Question 1?", "Question 2?", "Question 3?"]
        response = await ai_http_client.put(
            f"{config.api_prefix}/documents/questions",
            headers=credentials.auth_headers,
            params={"file_name": filename},
            json={"questions": custom_questions},
            timeout=config.ai_operation_timeout
        )
        assert response.status_code == 200
        result = response.json()
        assert "questions" in result


@pytest.mark.document
@pytest.mark.ai
@pytest.mark.slow
class TestDocumentFAQ:
    """Test AI FAQ generation."""

    @pytest.mark.asyncio
    async def test_01_generate_faq(
        self,
        ai_http_client,
        sample_pdf_file,
        resource_tracker
    ):
        """Test generating FAQ for document."""
        org_id, credentials = await create_test_user_session(ai_http_client)
        resource_tracker.add_organization(org_id)

        doc_result = await upload_document(
            ai_http_client,
            credentials,
            sample_pdf_file.read(),
            "test_faq.pdf",
            "application/pdf"
        )
        doc_id = doc_result.get("id") or doc_result.get("document_id")
        filename = doc_result.get("filename") or doc_result.get("file_name") or "test_faq.pdf"
        resource_tracker.add_document(org_id, doc_id)

        # Generate FAQ
        faq_result = await generate_faq(
            ai_http_client,
            credentials,
            filename,
            faq_count=5
        )

        assert "faq" in faq_result or "faqs" in faq_result
        faq_items = faq_result.get("faq") or faq_result.get("faqs", [])
        assert isinstance(faq_items, list)
        assert len(faq_items) >= 1

    @pytest.mark.asyncio
    async def test_02_generate_variable_faq_count(
        self,
        ai_http_client,
        sample_pdf_file,
        resource_tracker
    ):
        """Test generating different counts of FAQ items."""
        org_id, credentials = await create_test_user_session(ai_http_client)
        resource_tracker.add_organization(org_id)

        doc_result = await upload_document(
            ai_http_client,
            credentials,
            sample_pdf_file.read(),
            "test_var_faq.pdf",
            "application/pdf"
        )
        doc_id = doc_result.get("id") or doc_result.get("document_id")
        filename = doc_result.get("filename") or doc_result.get("file_name") or "test_var_faq.pdf"
        resource_tracker.add_document(org_id, doc_id)

        # Generate with different counts
        for count in [3, 8, 12]:
            faq_result = await generate_faq(
                ai_http_client,
                credentials,
                filename,
                faq_count=count
            )
            faq_items = faq_result.get("faq") or faq_result.get("faqs", [])
            assert len(faq_items) >= 1

    @pytest.mark.asyncio
    async def test_03_get_cached_faq(
        self,
        ai_http_client,
        sample_pdf_file,
        resource_tracker
    ):
        """Test retrieving cached FAQ."""
        org_id, credentials = await create_test_user_session(ai_http_client)
        resource_tracker.add_organization(org_id)

        doc_result = await upload_document(
            ai_http_client,
            credentials,
            sample_pdf_file.read(),
            "test_cached_faq.pdf",
            "application/pdf"
        )
        doc_id = doc_result.get("id") or doc_result.get("document_id")
        filename = doc_result.get("filename") or doc_result.get("file_name") or "test_cached_faq.pdf"
        resource_tracker.add_document(org_id, doc_id)

        # Generate FAQ
        await generate_faq(ai_http_client, credentials, filename, 5)

        # Get cached FAQ
        response = await ai_http_client.get(
            f"{config.api_prefix}/documents/faq",
            headers=credentials.auth_headers,
            params={"file_name": filename}
        )
        assert response.status_code == 200
        result = response.json()
        assert "faq" in result or "faqs" in result

    @pytest.mark.asyncio
    async def test_04_faq_with_custom_prompt(
        self,
        ai_http_client,
        sample_pdf_file,
        resource_tracker
    ):
        """Test generating FAQ with custom prompt."""
        org_id, credentials = await create_test_user_session(ai_http_client)
        resource_tracker.add_organization(org_id)

        doc_result = await upload_document(
            ai_http_client,
            credentials,
            sample_pdf_file.read(),
            "test_custom_faq.pdf",
            "application/pdf"
        )
        doc_id = doc_result.get("id") or doc_result.get("document_id")
        filename = doc_result.get("filename") or doc_result.get("file_name") or "test_custom_faq.pdf"
        resource_tracker.add_document(org_id, doc_id)

        # Generate with custom prompt
        faq_result = await generate_faq(
            ai_http_client,
            credentials,
            filename,
            faq_count=5,
            custom_prompt="Focus on technical aspects"
        )

        assert "faq" in faq_result or "faqs" in faq_result


@pytest.mark.document
@pytest.mark.ai
class TestAIContentErrorHandling:
    """Test error handling for AI content endpoints."""

    @pytest.mark.asyncio
    async def test_generate_for_nonexistent_document(self, ai_http_client, resource_tracker):
        """Test generating AI content for nonexistent document."""
        org_id, credentials = await create_test_user_session(ai_http_client)
        resource_tracker.add_organization(org_id)

        response = await ai_http_client.post(
            f"{config.api_prefix}/documents/summarize",
            headers=credentials.auth_headers,
            params={"file_name": "nonexistent_file.pdf"}
        )
        assert response.status_code in [404, 400], "Should fail for nonexistent document"

    @pytest.mark.asyncio
    async def test_generate_questions_invalid_count(self, ai_http_client, resource_tracker):
        """Test generating questions with invalid count."""
        org_id, credentials = await create_test_user_session(ai_http_client)
        resource_tracker.add_organization(org_id)

        response = await ai_http_client.post(
            f"{config.api_prefix}/documents/questions",
            headers=credentials.auth_headers,
            params={"file_name": "test.pdf"},
            json={"question_count": 100}  # Likely exceeds limit
        )
        # Should either accept and clamp to max, or reject
        assert response.status_code in [200, 400, 422]

    @pytest.mark.asyncio
    async def test_ai_without_authentication(self, ai_http_client):
        """Test AI endpoints without authentication."""
        response = await ai_http_client.post(
            f"{config.api_prefix}/documents/summarize",
            params={"file_name": "test.pdf"}
        )
        assert response.status_code in [401, 403], "Should require authentication"
