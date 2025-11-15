"""
Unit tests for app/models/document.py

Tests Document model functionality including validation and AI content.
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

from app.models.document import Document, DocumentStatus, FileType


class TestDocumentModel:
    """Test Document model creation and validation."""

    def test_document_creation_with_required_fields(self, mock_document_data):
        """Test creating document with all required fields."""
        doc = Document(**mock_document_data)

        assert doc.id == "doc123"
        assert doc.org_id == "org123"
        assert doc.filename == "test.pdf"
        assert doc.original_filename == "test.pdf"
        assert doc.file_type == FileType.PDF
        assert doc.file_size == 1024
        assert doc.status == DocumentStatus.UPLOADED

    def test_document_creation_defaults(self):
        """Test document creation with default values."""
        doc = Document(
            org_id="org123",
            filename="test.pdf",
            original_filename="test.pdf",
            file_type=FileType.PDF,
            file_size=1024,
            storage_path="org123/test.pdf",
            uploaded_by="user123",
        )

        assert doc.status == DocumentStatus.UPLOADED
        assert doc.is_active is True
        assert isinstance(doc.metadata, dict)
        assert doc.ai_summary is None
        assert doc.ai_questions is None
        assert doc.ai_faq is None

    def test_document_status_enum(self):
        """Test DocumentStatus enum values."""
        assert DocumentStatus.UPLOADING == "uploading"
        assert DocumentStatus.UPLOADED == "uploaded"
        assert DocumentStatus.PARSING == "parsing"
        assert DocumentStatus.PARSED == "parsed"
        assert DocumentStatus.FAILED == "failed"

    def test_file_type_enum(self):
        """Test FileType enum values."""
        assert FileType.PDF == "pdf"
        assert FileType.XLSX == "xlsx"

    def test_document_to_dict(self, mock_document_data):
        """Test converting document to dictionary."""
        doc = Document(**mock_document_data)
        doc_dict = doc.to_dict()

        assert "id" not in doc_dict  # ID excluded
        assert doc_dict["org_id"] == "org123"
        assert doc_dict["filename"] == "test.pdf"
        assert isinstance(doc_dict["created_at"], str)  # ISO format


class TestDocumentFilenameValidation:
    """Test filename validation."""

    def test_valid_filename(self):
        """Test creating document with valid filename."""
        doc = Document(
            org_id="org123",
            filename="valid-file_123.pdf",
            original_filename="valid-file_123.pdf",
            file_type=FileType.PDF,
            file_size=1024,
            storage_path="org123/valid-file_123.pdf",
            uploaded_by="user123",
        )

        assert doc.filename == "valid-file_123.pdf"

    def test_filename_empty_raises_error(self):
        """Test that empty filename raises error."""
        with pytest.raises(ValidationError) as exc_info:
            Document(
                org_id="org123",
                filename="",
                original_filename="test.pdf",
                file_type=FileType.PDF,
                file_size=1024,
                storage_path="org123/test.pdf",
                uploaded_by="user123",
            )

        assert "Filename cannot be empty" in str(exc_info.value)

    def test_filename_too_long_raises_error(self):
        """Test that overly long filename raises error."""
        long_filename = "a" * 256 + ".pdf"

        with pytest.raises(ValidationError) as exc_info:
            Document(
                org_id="org123",
                filename=long_filename,
                original_filename=long_filename,
                file_type=FileType.PDF,
                file_size=1024,
                storage_path=f"org123/{long_filename}",
                uploaded_by="user123",
            )

        assert "must be between 1 and 255 characters" in str(exc_info.value)

    def test_filename_sanitization(self):
        """Test that filename gets sanitized."""
        doc = Document(
            org_id="org123",
            filename="test file!@#.pdf",
            original_filename="test file!@#.pdf",
            file_type=FileType.PDF,
            file_size=1024,
            storage_path="org123/test.pdf",
            uploaded_by="user123",
        )

        # Special characters should be replaced with underscores
        assert "!" not in doc.filename
        assert "@" not in doc.filename
        assert "#" not in doc.filename


class TestDocumentFileSizeValidation:
    """Test file size validation."""

    def test_valid_file_size(self):
        """Test creating document with valid file size."""
        doc = Document(
            org_id="org123",
            filename="test.pdf",
            original_filename="test.pdf",
            file_type=FileType.PDF,
            file_size=1024 * 1024,  # 1MB
            storage_path="org123/test.pdf",
            uploaded_by="user123",
        )

        assert doc.file_size == 1024 * 1024

    def test_file_size_negative_raises_error(self):
        """Test that negative file size raises error."""
        with pytest.raises(ValidationError) as exc_info:
            Document(
                org_id="org123",
                filename="test.pdf",
                original_filename="test.pdf",
                file_type=FileType.PDF,
                file_size=-1,
                storage_path="org123/test.pdf",
                uploaded_by="user123",
            )

        assert "File size cannot be negative" in str(exc_info.value)

    def test_file_size_exceeds_limit_raises_error(self):
        """Test that file size exceeding limit raises error."""
        with pytest.raises(ValidationError) as exc_info:
            Document(
                org_id="org123",
                filename="test.pdf",
                original_filename="test.pdf",
                file_type=FileType.PDF,
                file_size=51 * 1024 * 1024,  # 51MB (over 50MB limit)
                storage_path="org123/test.pdf",
                uploaded_by="user123",
            )

        assert "cannot exceed" in str(exc_info.value)


class TestDocumentStoragePathValidation:
    """Test storage path validation."""

    def test_valid_storage_path(self):
        """Test creating document with valid storage path."""
        doc = Document(
            org_id="org123",
            filename="test.pdf",
            original_filename="test.pdf",
            file_type=FileType.PDF,
            file_size=1024,
            storage_path="org123/documents/test.pdf",
            uploaded_by="user123",
        )

        assert doc.storage_path == "org123/documents/test.pdf"

    def test_storage_path_empty_raises_error(self):
        """Test that empty storage path raises error."""
        with pytest.raises(ValidationError) as exc_info:
            Document(
                org_id="org123",
                filename="test.pdf",
                original_filename="test.pdf",
                file_type=FileType.PDF,
                file_size=1024,
                storage_path="",
                uploaded_by="user123",
            )

        assert "Storage path cannot be empty" in str(exc_info.value)

    def test_storage_path_with_leading_slash_raises_error(self):
        """Test that storage path with leading slash raises error."""
        with pytest.raises(ValidationError) as exc_info:
            Document(
                org_id="org123",
                filename="test.pdf",
                original_filename="test.pdf",
                file_type=FileType.PDF,
                file_size=1024,
                storage_path="/org123/test.pdf",
                uploaded_by="user123",
            )

        assert "should not start or end with '/'" in str(exc_info.value)

    def test_storage_path_with_trailing_slash_raises_error(self):
        """Test that storage path with trailing slash raises error."""
        with pytest.raises(ValidationError) as exc_info:
            Document(
                org_id="org123",
                filename="test.pdf",
                original_filename="test.pdf",
                file_type=FileType.PDF,
                file_size=1024,
                storage_path="org123/test.pdf/",
                uploaded_by="user123",
            )

        assert "should not start or end with '/'" in str(exc_info.value)


class TestDocumentMetadataValidation:
    """Test metadata validation."""

    def test_valid_metadata(self):
        """Test creating document with valid metadata."""
        doc = Document(
            org_id="org123",
            filename="test.pdf",
            original_filename="test.pdf",
            file_type=FileType.PDF,
            file_size=1024,
            storage_path="org123/test.pdf",
            uploaded_by="user123",
            metadata={"pages": 10, "author": "Test Author"},
        )

        assert doc.metadata["pages"] == 10
        assert doc.metadata["author"] == "Test Author"

    def test_metadata_not_dict_raises_error(self):
        """Test that non-dict metadata raises error."""
        with pytest.raises(ValidationError):
            Document(
                org_id="org123",
                filename="test.pdf",
                original_filename="test.pdf",
                file_type=FileType.PDF,
                file_size=1024,
                storage_path="org123/test.pdf",
                uploaded_by="user123",
                metadata="not a dict",  # type: ignore
            )

    def test_metadata_with_sensitive_keys_raises_error(self):
        """Test that metadata with sensitive keys raises error."""
        sensitive_keys = ["password", "secret", "key", "token", "credential"]

        for sensitive_key in sensitive_keys:
            with pytest.raises(ValidationError) as exc_info:
                Document(
                    org_id="org123",
                    filename="test.pdf",
                    original_filename="test.pdf",
                    file_type=FileType.PDF,
                    file_size=1024,
                    storage_path="org123/test.pdf",
                    uploaded_by="user123",
                    metadata={sensitive_key: "value"},
                )

            assert "cannot contain sensitive key" in str(exc_info.value)


class TestDocumentAIContent:
    """Test AI content fields."""

    def test_document_with_ai_summary(self):
        """Test document with AI summary."""
        doc = Document(
            org_id="org123",
            filename="test.pdf",
            original_filename="test.pdf",
            file_type=FileType.PDF,
            file_size=1024,
            storage_path="org123/test.pdf",
            uploaded_by="user123",
            ai_summary="This is a test summary.",
        )

        assert doc.ai_summary == "This is a test summary."
        assert doc.has_ai_summary is True

    def test_document_with_ai_questions(self):
        """Test document with AI questions."""
        questions = ["Question 1?", "Question 2?", "Question 3?"]

        doc = Document(
            org_id="org123",
            filename="test.pdf",
            original_filename="test.pdf",
            file_type=FileType.PDF,
            file_size=1024,
            storage_path="org123/test.pdf",
            uploaded_by="user123",
            ai_questions=questions,
        )

        assert len(doc.ai_questions) == 3
        assert doc.has_ai_questions is True

    def test_document_with_ai_faq(self):
        """Test document with AI FAQ."""
        faq = [
            {"question": "Q1?", "answer": "A1"},
            {"question": "Q2?", "answer": "A2"},
        ]

        doc = Document(
            org_id="org123",
            filename="test.pdf",
            original_filename="test.pdf",
            file_type=FileType.PDF,
            file_size=1024,
            storage_path="org123/test.pdf",
            uploaded_by="user123",
            ai_faq=faq,
        )

        assert len(doc.ai_faq) == 2
        assert doc.has_ai_faq is True

    def test_has_ai_summary_false_when_none(self):
        """Test has_ai_summary is False when summary is None."""
        doc = Document(
            org_id="org123",
            filename="test.pdf",
            original_filename="test.pdf",
            file_type=FileType.PDF,
            file_size=1024,
            storage_path="org123/test.pdf",
            uploaded_by="user123",
        )

        assert doc.has_ai_summary is False

    def test_has_ai_summary_false_when_empty(self):
        """Test has_ai_summary is False when summary is empty."""
        doc = Document(
            org_id="org123",
            filename="test.pdf",
            original_filename="test.pdf",
            file_type=FileType.PDF,
            file_size=1024,
            storage_path="org123/test.pdf",
            uploaded_by="user123",
            ai_summary="",
        )

        assert doc.has_ai_summary is False


class TestDocumentMethods:
    """Test document methods."""

    def test_update_timestamp(self, mock_document_data):
        """Test updating timestamp."""
        doc = Document(**mock_document_data)
        original_updated_at = doc.updated_at

        # Wait and update
        import time
        time.sleep(0.01)
        doc.update_timestamp()

        assert doc.updated_at > original_updated_at

    def test_update_summary(self):
        """Test updating AI summary."""
        doc = Document(
            org_id="org123",
            filename="test.pdf",
            original_filename="test.pdf",
            file_type=FileType.PDF,
            file_size=1024,
            storage_path="org123/test.pdf",
            uploaded_by="user123",
        )

        doc.update_ai_summary("New summary", model="gpt-5-mini")

        assert doc.ai_summary == "New summary"
        assert doc.has_ai_summary is True
        assert "model" in doc.summary_metadata
        assert doc.summary_metadata["model"] == "gpt-5-mini"

    def test_update_questions(self):
        """Test updating AI questions."""
        doc = Document(
            org_id="org123",
            filename="test.pdf",
            original_filename="test.pdf",
            file_type=FileType.PDF,
            file_size=1024,
            storage_path="org123/test.pdf",
            uploaded_by="user123",
        )

        questions = ["Q1?", "Q2?", "Q3?"]
        doc.update_ai_questions(questions, model="gpt-5-mini", count=3)

        assert doc.ai_questions == questions
        assert doc.has_ai_questions is True
        assert doc.questions_metadata["count"] == 3

    def test_update_faq(self):
        """Test updating AI FAQ."""
        doc = Document(
            org_id="org123",
            filename="test.pdf",
            original_filename="test.pdf",
            file_type=FileType.PDF,
            file_size=1024,
            storage_path="org123/test.pdf",
            uploaded_by="user123",
        )

        faq = [{"question": "Q1?", "answer": "A1"}]
        doc.update_ai_faq(faq, model="gpt-5-mini", count=1)

        assert doc.ai_faq == faq
        assert doc.has_ai_faq is True
        assert doc.faq_metadata["count"] == 1
