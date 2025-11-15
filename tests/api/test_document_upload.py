"""
Document Upload API Tests

Tests for document upload functionality including various file types,
validation, and error handling.
"""

import pytest
import sys
from pathlib import Path

# Add tests directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.test_helpers import upload_document, create_test_user_session
from test_config import config


@pytest.mark.document
@pytest.mark.upload
class TestDocumentUpload:
    """Test document upload operations."""

    @pytest.mark.asyncio
    async def test_01_upload_pdf_document(self, http_client, sample_pdf_file, resource_tracker):
        """Test uploading a PDF document."""
        org_id, credentials = await create_test_user_session(http_client)
        resource_tracker.add_organization(org_id)

        result = await upload_document(
            http_client,
            credentials,
            sample_pdf_file.read(),
            "test_document.pdf",
            "application/pdf"
        )

        assert "id" in result or "document_id" in result
        assert "filename" in result or "file_name" in result
        assert "storage_path" in result or "gcs_path" in result

        doc_id = result.get("id") or result.get("document_id")
        resource_tracker.add_document(org_id, doc_id)

    @pytest.mark.asyncio
    async def test_02_upload_txt_document(self, http_client, sample_txt_file, resource_tracker):
        """Test uploading a text document."""
        org_id, credentials = await create_test_user_session(http_client)
        resource_tracker.add_organization(org_id)

        result = await upload_document(
            http_client,
            credentials,
            sample_txt_file.read(),
            "test_document.txt",
            "text/plain"
        )

        assert "id" in result or "document_id" in result
        doc_id = result.get("id") or result.get("document_id")
        resource_tracker.add_document(org_id, doc_id)

    @pytest.mark.asyncio
    async def test_03_upload_with_target_path(self, http_client, sample_pdf_file, resource_tracker):
        """Test uploading document with specific target path."""
        org_id, credentials = await create_test_user_session(http_client)
        resource_tracker.add_organization(org_id)

        target_path = f"{org_id}/documents/invoices/invoice_001.pdf"

        result = await upload_document(
            http_client,
            credentials,
            sample_pdf_file.read(),
            "invoice_001.pdf",
            "application/pdf",
            target_path=target_path
        )

        assert "storage_path" in result or "gcs_path" in result
        doc_id = result.get("id") or result.get("document_id")
        resource_tracker.add_document(org_id, doc_id)

    @pytest.mark.asyncio
    async def test_04_upload_with_metadata(self, http_client, sample_pdf_file, resource_tracker):
        """Test uploading document with custom metadata."""
        org_id, credentials = await create_test_user_session(http_client)
        resource_tracker.add_organization(org_id)

        metadata = {
            "category": "invoice",
            "department": "finance",
            "year": "2024"
        }

        result = await upload_document(
            http_client,
            credentials,
            sample_pdf_file.read(),
            "invoice.pdf",
            "application/pdf",
            metadata=metadata
        )

        assert "id" in result or "document_id" in result
        doc_id = result.get("id") or result.get("document_id")
        resource_tracker.add_document(org_id, doc_id)

    @pytest.mark.asyncio
    async def test_05_upload_without_authentication(self, http_client, sample_pdf_file):
        """Test uploading document without authentication (should fail)."""
        files = {"file": ("test.pdf", sample_pdf_file, "application/pdf")}

        response = await http_client.post(
            f"{config.api_prefix}/documents/upload",
            files=files
        )
        assert response.status_code in [401, 403], "Should require authentication"

    @pytest.mark.asyncio
    async def test_06_upload_empty_file(self, http_client, resource_tracker):
        """Test uploading empty file (should fail)."""
        org_id, credentials = await create_test_user_session(http_client)
        resource_tracker.add_organization(org_id)

        import io
        empty_file = io.BytesIO(b"")
        files = {"file": ("empty.pdf", empty_file, "application/pdf")}

        response = await http_client.post(
            f"{config.api_prefix}/documents/upload",
            headers=credentials.auth_headers,
            files=files
        )
        # Should fail with validation error or bad request
        assert response.status_code in [400, 422], "Should reject empty file"

    @pytest.mark.asyncio
    async def test_07_upload_unsupported_file_type(self, http_client, resource_tracker):
        """Test uploading unsupported file type."""
        org_id, credentials = await create_test_user_session(http_client)
        resource_tracker.add_organization(org_id)

        import io
        # Pretend this is an executable file
        fake_exe = io.BytesIO(b"MZ\x90\x00\x03")  # EXE header
        files = {"file": ("malware.exe", fake_exe, "application/x-msdownload")}

        response = await http_client.post(
            f"{config.api_prefix}/documents/upload",
            headers=credentials.auth_headers,
            files=files
        )
        # Should reject based on file type or extension
        assert response.status_code in [400, 422, 415], "Should reject unsupported file type"

    @pytest.mark.asyncio
    async def test_08_upload_duplicate_filename_same_path(
        self,
        http_client,
        sample_pdf_file,
        resource_tracker
    ):
        """Test uploading file with same name to same path."""
        org_id, credentials = await create_test_user_session(http_client)
        resource_tracker.add_organization(org_id)

        filename = "duplicate_test.pdf"
        target_path = f"{org_id}/documents/{filename}"

        # Upload first file
        result1 = await upload_document(
            http_client,
            credentials,
            sample_pdf_file.read(),
            filename,
            "application/pdf",
            target_path=target_path
        )
        doc_id1 = result1.get("id") or result1.get("document_id")
        resource_tracker.add_document(org_id, doc_id1)

        # Upload again with same filename
        sample_pdf_file.seek(0)  # Reset file pointer
        result2 = await upload_document(
            http_client,
            credentials,
            sample_pdf_file.read(),
            filename,
            "application/pdf",
            target_path=target_path
        )
        doc_id2 = result2.get("id") or result2.get("document_id")
        resource_tracker.add_document(org_id, doc_id2)

        # Should either:
        # 1. Create new document with versioned name
        # 2. Replace existing document
        # 3. Return error
        # All are valid depending on implementation
        assert doc_id2 is not None


@pytest.mark.document
@pytest.mark.upload
class TestDocumentUploadLimits:
    """Test upload size limits and constraints."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_upload_large_file(self, http_client, resource_tracker):
        """Test uploading a large file (near size limit)."""
        org_id, credentials = await create_test_user_session(http_client)
        resource_tracker.add_organization(org_id)

        import io
        # Create a 5MB file
        large_content = b"X" * (5 * 1024 * 1024)
        large_file = io.BytesIO(large_content)

        files = {"file": ("large_file.txt", large_file, "text/plain")}

        response = await http_client.post(
            f"{config.api_prefix}/documents/upload",
            headers=credentials.auth_headers,
            files=files,
            timeout=60.0
        )

        # Should either succeed or fail with size limit error
        assert response.status_code in [200, 201, 413], (
            f"Unexpected status for large file: {response.status_code}"
        )

        if response.status_code in [200, 201]:
            result = response.json()
            doc_id = result.get("id") or result.get("document_id")
            resource_tracker.add_document(org_id, doc_id)
