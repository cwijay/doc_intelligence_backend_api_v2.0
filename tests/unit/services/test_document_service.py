"""
Unit tests for the Document services.

Tests document management operations with mocked dependencies.
"""

import os
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, Mock

import pytest

# Set test environment
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-testing-purposes-only-32chars")


class TestDocumentBaseServiceExceptions:
    """Tests for document service exception classes."""

    @pytest.mark.unit
    def test_document_not_found_error(self):
        """Test DocumentNotFoundError exception."""
        from app.services.document.document_base_service import DocumentNotFoundError

        error = DocumentNotFoundError("Document not found")

        assert str(error) == "Document not found"
        assert isinstance(error, Exception)

    @pytest.mark.unit
    def test_document_validation_error(self):
        """Test DocumentValidationError exception."""
        from app.services.document.document_base_service import DocumentValidationError

        error = DocumentValidationError("Invalid file type")

        assert str(error) == "Invalid file type"
        assert isinstance(error, Exception)

    @pytest.mark.unit
    def test_document_upload_error(self):
        """Test DocumentUploadError exception."""
        from app.services.document.document_base_service import DocumentUploadError

        error = DocumentUploadError("Upload failed")

        assert str(error) == "Upload failed"
        assert isinstance(error, Exception)


class TestDocumentBaseServiceInit:
    """Tests for DocumentBaseService initialization."""

    @pytest.mark.unit
    def test_base_service_initialization(self):
        """Test DocumentBaseService initializes correctly."""
        from app.services.document.document_base_service import DocumentBaseService
        from app.models.document import FileType

        service = DocumentBaseService()

        assert service.max_file_size == 50 * 1024 * 1024  # 50MB
        assert FileType.PDF in service.allowed_file_types
        assert FileType.XLSX in service.allowed_file_types
        assert service.max_path_length == 1024

    @pytest.mark.unit
    def test_base_service_has_db_property(self):
        """Test DocumentBaseService has db property."""
        from app.services.document.document_base_service import DocumentBaseService

        service = DocumentBaseService()

        # Should have db property
        assert hasattr(service, 'db')


class TestDocumentBaseServiceOrganization:
    """Tests for organization name lookup."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_organization_name_success(self):
        """Test successful organization name lookup."""
        from app.services.document.document_base_service import DocumentBaseService

        service = DocumentBaseService()
        org_id = str(uuid.uuid4())

        mock_response = Mock()
        mock_response.name = "Test Organization"

        with patch.object(service.org_service, 'get_organization', return_value=mock_response):
            result = await service._get_organization_name(org_id)

            assert result == "Test Organization"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_organization_name_error(self):
        """Test organization name lookup error handling."""
        from app.services.document.document_base_service import (
            DocumentBaseService,
            DocumentValidationError,
        )

        service = DocumentBaseService()
        org_id = str(uuid.uuid4())

        with patch.object(
            service.org_service,
            'get_organization',
            side_effect=Exception("Org not found")
        ):
            with pytest.raises(DocumentValidationError):
                await service._get_organization_name(org_id)


class TestDocumentBaseServiceFolder:
    """Tests for folder name lookup."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_folder_name_none(self):
        """Test folder name lookup with None folder_id."""
        from app.services.document.document_base_service import DocumentBaseService

        service = DocumentBaseService()
        org_id = str(uuid.uuid4())

        result = await service._get_folder_name(org_id, None)

        assert result is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_folder_name_success(self):
        """Test successful folder name lookup."""
        from app.services.document.document_base_service import DocumentBaseService

        service = DocumentBaseService()
        org_id = str(uuid.uuid4())
        folder_id = str(uuid.uuid4())

        mock_response = Mock()
        mock_response.path = "/Documents/Reports"

        with patch.object(
            service.folder_service,
            'get_folder',
            return_value=mock_response
        ):
            result = await service._get_folder_name(org_id, folder_id)

            assert result == "Reports"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_folder_name_fallback_to_id(self):
        """Test folder name falls back to folder_id when lookup fails."""
        from app.services.document.document_base_service import DocumentBaseService

        service = DocumentBaseService()
        org_id = str(uuid.uuid4())
        folder_id = str(uuid.uuid4())

        with patch.object(
            service.folder_service,
            'get_folder',
            side_effect=Exception("Folder not found")
        ):
            result = await service._get_folder_name(org_id, folder_id)

            # Falls back to folder_id
            assert result == folder_id


class TestDocumentServiceFacade:
    """Tests for DocumentService facade pattern."""

    @pytest.mark.unit
    def test_service_initialization_creates_specialized_services(self):
        """Test DocumentService initializes all specialized services."""
        from app.services.document.document_service import DocumentService

        service = DocumentService()

        assert hasattr(service, 'validation_service')
        assert hasattr(service, 'storage_service')
        assert hasattr(service, 'crud_service')
        assert hasattr(service, 'query_service')
        assert hasattr(service, 'download_service')


class TestDocumentServiceDelegation:
    """Tests for method delegation in DocumentService."""

    @pytest.mark.unit
    def test_validate_file_upload_delegates(self):
        """Test _validate_file_upload delegates to validation service."""
        from app.services.document.document_service import DocumentService
        from app.models.document import FileType

        service = DocumentService()

        mock_file = Mock()
        mock_file.filename = "test.pdf"
        mock_file.content_type = "application/pdf"
        mock_file.size = 1024

        expected_result = (FileType.PDF, "application/pdf")

        with patch.object(
            service.validation_service,
            '_validate_file_upload',
            return_value=expected_result
        ):
            result = service._validate_file_upload(mock_file)

            assert result == expected_result

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_basic_virus_scan_delegates(self):
        """Test _basic_virus_scan delegates to validation service."""
        from app.services.document.document_service import DocumentService

        service = DocumentService()

        with patch.object(
            service.validation_service,
            '_basic_virus_scan',
            return_value=True
        ) as mock_scan:
            result = await service._basic_virus_scan(b"test content", "test.pdf")

            assert result is True
            mock_scan.assert_called_once_with(b"test content", "test.pdf")

    @pytest.mark.unit
    def test_validate_target_path_delegates(self):
        """Test _validate_target_path delegates to validation service."""
        from app.services.document.document_service import DocumentService

        service = DocumentService()

        with patch.object(
            service.validation_service,
            '_validate_target_path',
            return_value="/safe/path/file.pdf"
        ) as mock_validate:
            result = service._validate_target_path("/some/path", "file.pdf")

            assert result == "/safe/path/file.pdf"
            mock_validate.assert_called_once()

    @pytest.mark.unit
    def test_extract_folder_from_storage_path_delegates(self):
        """Test _extract_folder_from_storage_path delegates to validation service."""
        from app.services.document.document_service import DocumentService

        service = DocumentService()

        with patch.object(
            service.validation_service,
            '_extract_folder_from_storage_path',
            return_value="documents"
        ) as mock_extract:
            result = service._extract_folder_from_storage_path("org/documents/file.pdf")

            assert result == "documents"
            mock_extract.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_storage_path_exists_delegates(self):
        """Test _check_storage_path_exists delegates to storage service."""
        from app.services.document.document_service import DocumentService

        service = DocumentService()
        org_id = str(uuid.uuid4())

        with patch.object(
            service.storage_service,
            '_check_storage_path_exists',
            return_value=True
        ) as mock_check:
            result = await service._check_storage_path_exists(org_id, "test/path")

            assert result is True
            mock_check.assert_called_once()


class TestDocumentServiceCRUDDelegation:
    """Tests for CRUD operation delegation."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_create_document_delegates(self):
        """Test create_document delegates to CRUD service."""
        from app.services.document.document_service import DocumentService
        from app.models.schemas import DocumentUploadResponse

        service = DocumentService()
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())

        mock_file = Mock()
        mock_file.filename = "test.pdf"

        mock_response = Mock(spec=DocumentUploadResponse)
        mock_response.id = str(uuid.uuid4())

        with patch.object(
            service.crud_service,
            'create_document',
            return_value=mock_response
        ) as mock_create:
            result = await service.create_document(
                org_id=org_id,
                file=mock_file,
                user_id=user_id,
            )

            assert result == mock_response
            mock_create.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_document_delegates(self):
        """Test get_document delegates to CRUD service."""
        from app.services.document.document_service import DocumentService
        from app.models.schemas import DocumentResponse

        service = DocumentService()
        org_id = str(uuid.uuid4())
        doc_id = str(uuid.uuid4())

        mock_response = Mock(spec=DocumentResponse)
        mock_response.id = doc_id

        with patch.object(
            service.crud_service,
            'get_document',
            return_value=mock_response
        ) as mock_get:
            result = await service.get_document(org_id, doc_id)

            assert result == mock_response
            mock_get.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_delete_document_delegates(self):
        """Test delete_document delegates to CRUD service."""
        from app.services.document.document_service import DocumentService

        service = DocumentService()
        org_id = str(uuid.uuid4())
        doc_id = str(uuid.uuid4())

        expected_result = {"success": True, "message": "Document deleted"}

        with patch.object(
            service.crud_service,
            'delete_document',
            return_value=expected_result
        ) as mock_delete:
            result = await service.delete_document(org_id, doc_id)

            assert result == expected_result
            mock_delete.assert_called_once_with(org_id=org_id, document_id=doc_id)


class TestDocumentServiceQueryDelegation:
    """Tests for query operation delegation."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_list_documents_delegates(self):
        """Test list_documents delegates to query service."""
        from app.services.document.document_service import DocumentService
        from app.models.schemas import DocumentList, PaginationParams

        service = DocumentService()
        org_id = str(uuid.uuid4())
        pagination = PaginationParams(page=1, per_page=10)

        mock_response = Mock(spec=DocumentList)
        mock_response.documents = []
        mock_response.total = 0

        with patch.object(
            service.query_service,
            'list_documents',
            return_value=mock_response
        ) as mock_list:
            result = await service.list_documents(org_id, pagination)

            assert result == mock_response
            mock_list.assert_called_once()


class TestDocumentServiceDownloadDelegation:
    """Tests for download operation delegation."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_download_document_delegates(self):
        """Test download_document delegates to download service."""
        from app.services.document.document_service import DocumentService
        from app.models.schemas import DocumentDownloadResponse

        service = DocumentService()
        org_id = str(uuid.uuid4())
        doc_id = str(uuid.uuid4())

        mock_response = Mock(spec=DocumentDownloadResponse)
        mock_response.download_url = "https://signed-url.example.com"

        with patch.object(
            service.download_service,
            'download_document',
            return_value=mock_response
        ) as mock_download:
            result = await service.download_document(org_id, doc_id)

            assert result == mock_response
            mock_download.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_download_document_custom_expiration(self):
        """Test download_document with custom expiration."""
        from app.services.document.document_service import DocumentService
        from app.models.schemas import DocumentDownloadResponse

        service = DocumentService()
        org_id = str(uuid.uuid4())
        doc_id = str(uuid.uuid4())

        mock_response = Mock(spec=DocumentDownloadResponse)

        with patch.object(
            service.download_service,
            'download_document',
            return_value=mock_response
        ) as mock_download:
            await service.download_document(org_id, doc_id, expiration_minutes=120)

            # Verify expiration_minutes was passed
            call_kwargs = mock_download.call_args.kwargs
            assert call_kwargs['expiration_minutes'] == 120


class TestDocumentServiceGlobalInstance:
    """Tests for global service instance."""

    @pytest.mark.unit
    def test_global_document_service_exists(self):
        """Test global document_service instance exists."""
        from app.services.document.document_service import document_service

        assert document_service is not None

    @pytest.mark.unit
    def test_global_document_service_is_document_service(self):
        """Test global instance is DocumentService."""
        from app.services.document.document_service import (
            document_service,
            DocumentService,
        )

        assert isinstance(document_service, DocumentService)
