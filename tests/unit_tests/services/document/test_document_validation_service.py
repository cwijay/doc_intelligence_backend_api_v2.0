"""
Unit tests for app/services/document/document_validation_service.py

Tests document validation service functionality.
"""

import pytest
from unittest.mock import Mock, AsyncMock
from io import BytesIO

from app.services.document.document_validation_service import DocumentValidationService
from app.services.document.document_base_service import DocumentValidationError
from app.models.document import FileType


class TestFileUploadValidation:
    """Test file upload validation."""

    def test_validate_file_upload_valid_pdf(self):
        """Test validating a valid PDF upload."""
        service = DocumentValidationService()

        mock_file = Mock()
        mock_file.filename = "test.pdf"
        mock_file.size = 1024 * 1024  # 1MB
        mock_file.content_type = "application/pdf"

        file_type, content_type = service._validate_file_upload(mock_file)

        assert file_type == FileType.PDF
        assert content_type == "application/pdf"

    def test_validate_file_upload_valid_xlsx(self):
        """Test validating a valid XLSX upload."""
        service = DocumentValidationService()

        mock_file = Mock()
        mock_file.filename = "test.xlsx"
        mock_file.size = 1024 * 1024  # 1MB
        mock_file.content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

        file_type, content_type = service._validate_file_upload(mock_file)

        assert file_type == FileType.XLSX

    def test_validate_file_upload_no_filename(self):
        """Test validating upload without filename."""
        service = DocumentValidationService()

        mock_file = Mock()
        mock_file.filename = None

        with pytest.raises(DocumentValidationError) as exc_info:
            service._validate_file_upload(mock_file)

        assert "Filename is required" in str(exc_info.value)

    def test_validate_file_upload_unsupported_type(self):
        """Test validating unsupported file type."""
        service = DocumentValidationService()

        mock_file = Mock()
        mock_file.filename = "test.exe"
        mock_file.size = 1024
        mock_file.content_type = "application/octet-stream"

        with pytest.raises(DocumentValidationError) as exc_info:
            service._validate_file_upload(mock_file)

        assert "Unsupported file type" in str(exc_info.value)

    def test_validate_file_upload_exceeds_size_limit(self):
        """Test validating file that exceeds size limit."""
        service = DocumentValidationService()

        mock_file = Mock()
        mock_file.filename = "test.pdf"
        mock_file.size = 51 * 1024 * 1024  # 51MB (over 50MB limit)
        mock_file.content_type = "application/pdf"

        with pytest.raises(DocumentValidationError) as exc_info:
            service._validate_file_upload(mock_file)

        assert "exceeds maximum limit" in str(exc_info.value)


class TestVirusScan:
    """Test basic virus scanning."""

    @pytest.mark.asyncio
    async def test_virus_scan_clean_file(self):
        """Test scanning a clean file."""
        service = DocumentValidationService()

        clean_content = b"This is clean PDF content with no threats"
        result = await service._basic_virus_scan(clean_content, "test.pdf")

        assert result is True

    @pytest.mark.asyncio
    async def test_virus_scan_detects_script_tag(self):
        """Test scanning file with script tag."""
        service = DocumentValidationService()

        suspicious_content = b"Some content <script>alert('xss')</script>"
        result = await service._basic_virus_scan(suspicious_content, "test.pdf")

        assert result is False

    @pytest.mark.asyncio
    async def test_virus_scan_detects_javascript(self):
        """Test scanning file with javascript: protocol."""
        service = DocumentValidationService()

        suspicious_content = b"javascript:maliciousCode()"
        result = await service._basic_virus_scan(suspicious_content, "test.pdf")

        assert result is False

    @pytest.mark.asyncio
    async def test_virus_scan_detects_onload(self):
        """Test scanning file with onload event handler."""
        service = DocumentValidationService()

        suspicious_content = b'<img src="x" onload="malicious()">'
        result = await service._basic_virus_scan(suspicious_content, "test.pdf")

        assert result is False


class TestTargetPathValidation:
    """Test target path validation and sanitization."""

    def test_validate_target_path_valid(self):
        """Test validating a valid target path."""
        service = DocumentValidationService()

        target_path = "MyOrg/original/invoices/document.pdf"
        result = service._validate_target_path(target_path, "document.pdf")

        assert result == "MyOrg/original/invoices/document.pdf"

    def test_validate_target_path_empty(self):
        """Test validating empty target path."""
        service = DocumentValidationService()

        with pytest.raises(DocumentValidationError) as exc_info:
            service._validate_target_path("", "document.pdf")

        assert "cannot be empty" in str(exc_info.value)

    def test_validate_target_path_whitespace_only(self):
        """Test validating whitespace-only target path."""
        service = DocumentValidationService()

        with pytest.raises(DocumentValidationError) as exc_info:
            service._validate_target_path("   ", "document.pdf")

        assert "cannot be empty" in str(exc_info.value)

    def test_validate_target_path_too_long(self):
        """Test validating overly long target path."""
        service = DocumentValidationService()

        # Create a path longer than max_path_length (1024)
        long_path = "Org/original/folder/" + ("a" * 1100) + ".pdf"

        with pytest.raises(DocumentValidationError) as exc_info:
            service._validate_target_path(long_path, "document.pdf")

        assert "too long" in str(exc_info.value)

    def test_validate_target_path_directory_traversal(self):
        """Test rejecting path with directory traversal."""
        service = DocumentValidationService()

        malicious_paths = [
            "Org/original/../../../etc/passwd",
            "Org/original/folder/../../sensitive.pdf",
            "Org/original/folder/..\\..\\sensitive.pdf",
            "~/sensitive/document.pdf",
        ]

        for path in malicious_paths:
            with pytest.raises(DocumentValidationError) as exc_info:
                service._validate_target_path(path, "document.pdf")

            assert "unsafe" in str(exc_info.value).lower() or "not allowed" in str(exc_info.value).lower()

    def test_validate_target_path_null_bytes(self):
        """Test rejecting path with null bytes."""
        service = DocumentValidationService()

        malicious_path = "Org/original/folder/doc\x00.pdf"

        with pytest.raises(DocumentValidationError) as exc_info:
            service._validate_target_path(malicious_path, "document.pdf")

        assert "invalid characters" in str(exc_info.value)

    def test_validate_target_path_invalid_format(self):
        """Test rejecting path with invalid format."""
        service = DocumentValidationService()

        invalid_paths = [
            "Org/document.pdf",  # Too few segments
            "Org/original/document.pdf",  # Missing folder
            "Org/wrong/folder/document.pdf",  # Wrong second segment
        ]

        for path in invalid_paths:
            with pytest.raises(DocumentValidationError):
                service._validate_target_path(path, "document.pdf")

    def test_validate_target_path_empty_components(self):
        """Test rejecting path with empty components."""
        service = DocumentValidationService()

        invalid_paths = [
            "/original/folder/document.pdf",  # Empty org
            "Org/original//document.pdf",  # Empty folder
            "Org/original/folder/",  # Empty document name
        ]

        for path in invalid_paths:
            with pytest.raises(DocumentValidationError):
                service._validate_target_path(path, "document.pdf")

    def test_validate_target_path_sanitizes_document_name(self):
        """Test that document name gets sanitized."""
        service = DocumentValidationService()

        target_path = "Org/original/folder/document!@#$.pdf"
        result = service._validate_target_path(target_path, "document.pdf")

        # Document name should be sanitized
        assert "!" not in result
        assert "@" not in result
        assert "#" not in result


class TestFolderExtraction:
    """Test folder extraction from storage path."""

    def test_extract_folder_from_storage_path_valid(self):
        """Test extracting folder from valid storage path."""
        service = DocumentValidationService()

        storage_path = "MyOrg/original/invoices/document.pdf"
        folder = service._extract_folder_from_storage_path(storage_path)

        assert folder == "invoices"

    def test_extract_folder_from_storage_path_root(self):
        """Test extracting folder from root storage path."""
        service = DocumentValidationService()

        storage_path = "MyOrg/original/root/document.pdf"
        folder = service._extract_folder_from_storage_path(storage_path)

        assert folder is None  # 'root' is treated as None

    def test_extract_folder_from_storage_path_invalid_format(self):
        """Test extracting folder from invalid storage path."""
        service = DocumentValidationService()

        storage_path = "MyOrg/document.pdf"
        folder = service._extract_folder_from_storage_path(storage_path)

        assert folder is None

    def test_extract_folder_from_storage_path_empty(self):
        """Test extracting folder from empty storage path."""
        service = DocumentValidationService()

        folder = service._extract_folder_from_storage_path("")

        assert folder is None

    def test_extract_folder_from_storage_path_none(self):
        """Test extracting folder from None storage path."""
        service = DocumentValidationService()

        folder = service._extract_folder_from_storage_path(None)

        assert folder is None
