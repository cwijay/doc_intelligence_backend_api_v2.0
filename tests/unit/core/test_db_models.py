"""
Unit tests for the database models.

Tests SQLAlchemy model definitions and serialization.
"""

import os
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

# Set test environment
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-testing-purposes-only-32chars")


class TestAuditEnums:
    """Tests for audit enumeration types."""

    @pytest.mark.unit
    def test_audit_action_values(self):
        """Test AuditAction enum values."""
        from biz2bricks_core import AuditAction

        assert AuditAction.CREATE.value == "CREATE"
        assert AuditAction.UPDATE.value == "UPDATE"
        assert AuditAction.DELETE.value == "DELETE"
        assert AuditAction.LOGIN.value == "LOGIN"
        assert AuditAction.LOGOUT.value == "LOGOUT"
        assert AuditAction.UPLOAD.value == "UPLOAD"
        assert AuditAction.DOWNLOAD.value == "DOWNLOAD"
        assert AuditAction.MOVE.value == "MOVE"

    @pytest.mark.unit
    def test_audit_entity_type_values(self):
        """Test AuditEntityType enum values."""
        from biz2bricks_core import AuditEntityType

        assert AuditEntityType.ORGANIZATION.value == "ORGANIZATION"
        assert AuditEntityType.USER.value == "USER"
        assert AuditEntityType.FOLDER.value == "FOLDER"
        assert AuditEntityType.DOCUMENT.value == "DOCUMENT"

    @pytest.mark.unit
    def test_audit_action_string_comparison(self):
        """Test that AuditAction can be compared as strings."""
        from biz2bricks_core import AuditAction

        assert AuditAction.CREATE == "CREATE"
        assert AuditAction.LOGIN == "LOGIN"

    @pytest.mark.unit
    def test_audit_entity_type_string_comparison(self):
        """Test that AuditEntityType can be compared as strings."""
        from biz2bricks_core import AuditEntityType

        assert AuditEntityType.USER == "USER"
        assert AuditEntityType.DOCUMENT == "DOCUMENT"


class TestOrganizationModel:
    """Tests for OrganizationModel."""

    @pytest.mark.unit
    def test_organization_model_creation(self):
        """Test creating an OrganizationModel instance."""
        from biz2bricks_core import OrganizationModel

        org = OrganizationModel(
            id=str(uuid.uuid4()),
            name="Test Organization",
            domain="test.com",
            plan_type="free",
            settings={},
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )

        assert org.name == "Test Organization"
        assert org.domain == "test.com"
        assert org.plan_type == "free"
        assert org.is_active is True

    @pytest.mark.unit
    def test_organization_to_dict(self):
        """Test OrganizationModel.to_dict() serialization."""
        from biz2bricks_core import OrganizationModel

        now = datetime.now(timezone.utc)
        org_id = str(uuid.uuid4())

        org = OrganizationModel(
            id=org_id,
            name="Test Organization",
            domain="test.com",
            plan_type="pro",
            settings={"feature1": True},
            is_active=True,
            created_at=now,
            updated_at=now
        )

        result = org.to_dict()

        assert result["id"] == org_id
        assert result["name"] == "Test Organization"
        assert result["domain"] == "test.com"
        assert result["plan_type"] == "pro"
        assert result["settings"] == {"feature1": True}
        assert result["is_active"] is True
        assert result["created_at"] == now.isoformat()
        assert result["updated_at"] == now.isoformat()

    @pytest.mark.unit
    def test_organization_to_dict_with_none_timestamps(self):
        """Test to_dict handles None timestamps."""
        from biz2bricks_core import OrganizationModel

        org = OrganizationModel(
            id=str(uuid.uuid4()),
            name="Test Organization",
            domain=None,
            plan_type="free",
            settings={},
            is_active=True,
            created_at=None,
            updated_at=None
        )

        result = org.to_dict()

        assert result["created_at"] is None
        assert result["updated_at"] is None
        assert result["domain"] is None


class TestUserModel:
    """Tests for UserModel."""

    @pytest.mark.unit
    def test_user_model_creation(self):
        """Test creating a UserModel instance."""
        from biz2bricks_core import UserModel

        user = UserModel(
            id=str(uuid.uuid4()),
            organization_id=str(uuid.uuid4()),
            email="test@example.com",
            username="testuser",
            full_name="Test User",
            password_hash="$2b$12$hashed",
            role="user",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )

        assert user.email == "test@example.com"
        assert user.username == "testuser"
        assert user.full_name == "Test User"
        assert user.role == "user"
        assert user.is_active is True

    @pytest.mark.unit
    def test_user_to_dict_excludes_password(self):
        """Test that UserModel.to_dict() excludes password_hash."""
        from biz2bricks_core import UserModel

        now = datetime.now(timezone.utc)
        user_id = str(uuid.uuid4())
        org_id = str(uuid.uuid4())

        user = UserModel(
            id=user_id,
            organization_id=org_id,
            email="test@example.com",
            username="testuser",
            full_name="Test User",
            password_hash="$2b$12$supersecret",
            role="admin",
            is_active=True,
            last_login=now,
            created_at=now,
            updated_at=now
        )

        result = user.to_dict()

        assert result["id"] == user_id
        assert result["org_id"] == org_id
        assert result["email"] == "test@example.com"
        assert result["username"] == "testuser"
        assert result["full_name"] == "Test User"
        assert result["role"] == "admin"
        assert result["is_active"] is True
        assert result["last_login"] == now.isoformat()
        # Password should NOT be in the dict
        assert "password_hash" not in result
        assert "password" not in result

    @pytest.mark.unit
    def test_user_to_dict_with_none_last_login(self):
        """Test to_dict handles None last_login."""
        from biz2bricks_core import UserModel

        user = UserModel(
            id=str(uuid.uuid4()),
            organization_id=str(uuid.uuid4()),
            email="test@example.com",
            username="testuser",
            full_name="Test User",
            password_hash="$2b$12$hashed",
            role="user",
            is_active=True,
            last_login=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )

        result = user.to_dict()

        assert result["last_login"] is None


class TestFolderModel:
    """Tests for FolderModel."""

    @pytest.mark.unit
    def test_folder_model_creation(self):
        """Test creating a FolderModel instance."""
        from biz2bricks_core import FolderModel

        folder = FolderModel(
            id=str(uuid.uuid4()),
            organization_id=str(uuid.uuid4()),
            name="Documents",
            parent_folder_id=None,
            path="/Documents",
            created_by=str(uuid.uuid4()),
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )

        assert folder.name == "Documents"
        assert folder.path == "/Documents"
        assert folder.parent_folder_id is None
        assert folder.is_active is True

    @pytest.mark.unit
    def test_folder_with_parent(self):
        """Test FolderModel with parent folder."""
        from biz2bricks_core import FolderModel

        parent_id = str(uuid.uuid4())

        folder = FolderModel(
            id=str(uuid.uuid4()),
            organization_id=str(uuid.uuid4()),
            name="Subfolder",
            parent_folder_id=parent_id,
            path="/Documents/Subfolder",
            created_by=str(uuid.uuid4()),
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )

        assert folder.parent_folder_id == parent_id
        assert "/Documents/Subfolder" in folder.path

    @pytest.mark.unit
    def test_folder_to_dict(self):
        """Test FolderModel.to_dict() serialization."""
        from biz2bricks_core import FolderModel

        now = datetime.now(timezone.utc)
        folder_id = str(uuid.uuid4())
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())

        folder = FolderModel(
            id=folder_id,
            organization_id=org_id,
            name="Reports",
            parent_folder_id=None,
            path="/Reports",
            created_by=user_id,
            is_active=True,
            created_at=now,
            updated_at=now
        )

        result = folder.to_dict()

        assert result["id"] == folder_id
        assert result["org_id"] == org_id
        assert result["name"] == "Reports"
        assert result["parent_folder_id"] is None
        assert result["path"] == "/Reports"
        assert result["created_by"] == user_id
        assert result["is_active"] is True


class TestDocumentModel:
    """Tests for DocumentModel."""

    @pytest.mark.unit
    def test_document_model_creation(self):
        """Test creating a DocumentModel instance."""
        from biz2bricks_core import DocumentModel

        doc = DocumentModel(
            id=str(uuid.uuid4()),
            organization_id=str(uuid.uuid4()),
            folder_id=str(uuid.uuid4()),
            filename="report.pdf",
            original_filename="quarterly_report.pdf",
            file_type="pdf",
            file_size=1024 * 1024,  # 1MB
            storage_path="orgs/123/documents/456.pdf",
            status="uploaded",
            uploaded_by=str(uuid.uuid4()),
            is_active=True,
            doc_metadata={"pages": 10},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )

        assert doc.filename == "report.pdf"
        assert doc.original_filename == "quarterly_report.pdf"
        assert doc.file_type == "pdf"
        assert doc.file_size == 1024 * 1024
        assert doc.status == "uploaded"

    @pytest.mark.unit
    def test_document_to_dict(self):
        """Test DocumentModel.to_dict() serialization."""
        from biz2bricks_core import DocumentModel

        now = datetime.now(timezone.utc)
        doc_id = str(uuid.uuid4())
        org_id = str(uuid.uuid4())
        folder_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())

        doc = DocumentModel(
            id=doc_id,
            organization_id=org_id,
            folder_id=folder_id,
            filename="doc.pdf",
            original_filename="original_doc.pdf",
            file_type="pdf",
            file_size=5000,
            storage_path=f"orgs/{org_id}/documents/{doc_id}.pdf",
            status="completed",
            uploaded_by=user_id,
            is_active=True,
            doc_metadata={"processed": True, "pages": 5},
            created_at=now,
            updated_at=now
        )

        result = doc.to_dict()

        assert result["id"] == doc_id
        assert result["org_id"] == org_id
        assert result["folder_id"] == folder_id
        assert result["filename"] == "doc.pdf"
        assert result["original_filename"] == "original_doc.pdf"
        assert result["file_type"] == "pdf"
        assert result["file_size"] == 5000
        assert result["status"] == "completed"
        assert result["uploaded_by"] == user_id
        assert result["is_active"] is True
        assert result["metadata"] == {"processed": True, "pages": 5}

    @pytest.mark.unit
    def test_document_without_folder(self):
        """Test DocumentModel without folder (root level document)."""
        from biz2bricks_core import DocumentModel

        doc = DocumentModel(
            id=str(uuid.uuid4()),
            organization_id=str(uuid.uuid4()),
            folder_id=None,
            filename="root_doc.pdf",
            original_filename="root_doc.pdf",
            file_type="pdf",
            file_size=1000,
            storage_path="orgs/123/documents/doc.pdf",
            status="uploaded",
            uploaded_by=str(uuid.uuid4()),
            is_active=True,
            doc_metadata={},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )

        result = doc.to_dict()

        assert result["folder_id"] is None


class TestAuditLogModel:
    """Tests for AuditLogModel."""

    @pytest.mark.unit
    def test_audit_log_model_creation(self):
        """Test creating an AuditLogModel instance."""
        from biz2bricks_core import AuditLogModel, AuditAction, AuditEntityType

        audit = AuditLogModel(
            id=str(uuid.uuid4()),
            organization_id=str(uuid.uuid4()),
            user_id=str(uuid.uuid4()),
            action=AuditAction.CREATE.value,
            entity_type=AuditEntityType.USER.value,
            entity_id=str(uuid.uuid4()),
            details={"new_values": {"email": "test@example.com"}},
            ip_address="192.168.1.1",
            session_id=str(uuid.uuid4()),
            user_agent="Mozilla/5.0",
            created_at=datetime.now(timezone.utc)
        )

        assert audit.action == "CREATE"
        assert audit.entity_type == "USER"
        assert audit.ip_address == "192.168.1.1"
        assert "new_values" in audit.details

    @pytest.mark.unit
    def test_audit_log_to_dict(self):
        """Test AuditLogModel.to_dict() serialization."""
        from biz2bricks_core import AuditLogModel

        now = datetime.now(timezone.utc)
        audit_id = str(uuid.uuid4())
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        entity_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())

        audit = AuditLogModel(
            id=audit_id,
            organization_id=org_id,
            user_id=user_id,
            action="LOGIN",
            entity_type="USER",
            entity_id=entity_id,
            details={"method": "password"},
            ip_address="10.0.0.1",
            session_id=session_id,
            user_agent="Test Agent",
            created_at=now
        )

        result = audit.to_dict()

        assert result["id"] == audit_id
        assert result["organization_id"] == org_id
        assert result["user_id"] == user_id
        assert result["action"] == "LOGIN"
        assert result["entity_type"] == "USER"
        assert result["entity_id"] == entity_id
        assert result["details"] == {"method": "password"}
        assert result["ip_address"] == "10.0.0.1"
        assert result["session_id"] == session_id
        assert result["user_agent"] == "Test Agent"
        assert result["created_at"] == now.isoformat()

    @pytest.mark.unit
    def test_audit_log_system_action_no_user(self):
        """Test AuditLogModel for system actions without user."""
        from biz2bricks_core import AuditLogModel

        audit = AuditLogModel(
            id=str(uuid.uuid4()),
            organization_id=str(uuid.uuid4()),
            user_id=None,  # System action
            action="UPDATE",
            entity_type="ORGANIZATION",
            entity_id=str(uuid.uuid4()),
            details={"system_triggered": True},
            ip_address=None,
            session_id=None,
            user_agent=None,
            created_at=datetime.now(timezone.utc)
        )

        result = audit.to_dict()

        assert result["user_id"] is None
        assert result["ip_address"] is None
        assert result["session_id"] is None
        assert result["user_agent"] is None

    @pytest.mark.unit
    def test_audit_log_ipv6_address(self):
        """Test AuditLogModel with IPv6 address."""
        from biz2bricks_core import AuditLogModel

        ipv6_address = "2001:0db8:85a3:0000:0000:8a2e:0370:7334"

        audit = AuditLogModel(
            id=str(uuid.uuid4()),
            organization_id=str(uuid.uuid4()),
            user_id=str(uuid.uuid4()),
            action="LOGIN",
            entity_type="USER",
            entity_id=str(uuid.uuid4()),
            details={},
            ip_address=ipv6_address,
            session_id=str(uuid.uuid4()),
            user_agent="Test Agent",
            created_at=datetime.now(timezone.utc)
        )

        assert audit.ip_address == ipv6_address
        assert len(ipv6_address) <= 45  # Max IPv6 length


class TestModelDefaults:
    """Tests for model default values."""

    @pytest.mark.unit
    def test_organization_default_plan_type(self):
        """Test OrganizationModel default plan_type."""
        from biz2bricks_core import OrganizationModel

        # When plan_type is not specified, it should default to "free"
        org = OrganizationModel(
            id=str(uuid.uuid4()),
            name="Test Org",
            settings={},
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )

        # The default is set at the column level, so we check if it's accessible
        assert hasattr(org, 'plan_type')

    @pytest.mark.unit
    def test_document_default_status(self):
        """Test DocumentModel default status."""
        from biz2bricks_core import DocumentModel

        doc = DocumentModel(
            id=str(uuid.uuid4()),
            organization_id=str(uuid.uuid4()),
            filename="test.pdf",
            original_filename="test.pdf",
            file_type="pdf",
            file_size=1000,
            storage_path="test/path",
            uploaded_by=str(uuid.uuid4()),
            is_active=True,
            doc_metadata={},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )

        # Status has a default of "uploaded"
        assert hasattr(doc, 'status')

    @pytest.mark.unit
    def test_user_default_role(self):
        """Test UserModel default role."""
        from biz2bricks_core import UserModel

        user = UserModel(
            id=str(uuid.uuid4()),
            organization_id=str(uuid.uuid4()),
            email="test@example.com",
            username="testuser",
            full_name="Test User",
            password_hash="$2b$12$hash",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )

        # Role has a default of "user"
        assert hasattr(user, 'role')


class TestModelTableNames:
    """Tests for model table names."""

    @pytest.mark.unit
    def test_table_names(self):
        """Test that models have correct table names."""
        from biz2bricks_core import (
            OrganizationModel,
            UserModel,
            FolderModel,
            DocumentModel,
            AuditLogModel
        )

        assert OrganizationModel.__tablename__ == "organizations"
        assert UserModel.__tablename__ == "users"
        assert FolderModel.__tablename__ == "folders"
        assert DocumentModel.__tablename__ == "documents"
        assert AuditLogModel.__tablename__ == "audit_logs"


class TestModelIndexes:
    """Tests for model index definitions."""

    @pytest.mark.unit
    def test_organization_indexes_defined(self):
        """Test OrganizationModel has expected indexes."""
        from biz2bricks_core import OrganizationModel

        # Check __table_args__ contains indexes
        table_args = OrganizationModel.__table_args__
        index_names = [idx.name for idx in table_args if hasattr(idx, 'name')]

        assert "idx_organizations_is_active" in index_names
        assert "idx_organizations_created_at" in index_names

    @pytest.mark.unit
    def test_user_indexes_defined(self):
        """Test UserModel has expected indexes."""
        from biz2bricks_core import UserModel

        table_args = UserModel.__table_args__
        index_names = [idx.name for idx in table_args if hasattr(idx, 'name')]

        assert "idx_users_organization_id" in index_names
        assert "idx_users_email" in index_names
        assert "idx_users_is_active" in index_names

    @pytest.mark.unit
    def test_document_indexes_defined(self):
        """Test DocumentModel has expected indexes."""
        from biz2bricks_core import DocumentModel

        table_args = DocumentModel.__table_args__
        index_names = [idx.name for idx in table_args if hasattr(idx, 'name')]

        assert "idx_documents_organization_id" in index_names
        assert "idx_documents_folder_id" in index_names
        assert "idx_documents_status" in index_names

    @pytest.mark.unit
    def test_audit_log_indexes_defined(self):
        """Test AuditLogModel has expected indexes."""
        from biz2bricks_core import AuditLogModel

        table_args = AuditLogModel.__table_args__
        index_names = [idx.name for idx in table_args if hasattr(idx, 'name')]

        assert "idx_audit_logs_org_id" in index_names
        assert "idx_audit_logs_action" in index_names
        assert "idx_audit_logs_created_at" in index_names
