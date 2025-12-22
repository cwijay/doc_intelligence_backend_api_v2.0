"""
Unit tests for the AuditService.

Tests audit logging operations with mocked database.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch, Mock

import pytest

# Set test environment
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-testing-purposes-only-32chars")


class TestAuditServiceLogEvent:
    """Tests for audit event logging."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_log_event_success(self):
        """Test successful audit event logging."""
        from app.services.audit_service import AuditService
        from biz2bricks_core import AuditAction, AuditEntityType

        service = AuditService()
        org_id = str(uuid.uuid4())
        entity_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())

        with patch('app.services.audit_service.db') as mock_db:
            mock_session = AsyncMock()
            mock_session.add = Mock()
            mock_session.flush = AsyncMock()
            mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db.session.return_value.__aexit__ = AsyncMock()

            result = await service.log_event(
                org_id=org_id,
                action=AuditAction.CREATE,
                entity_type=AuditEntityType.USER,
                entity_id=entity_id,
                user_id=user_id,
                details={"operation": "create"},
                ip_address="192.168.1.1",
                session_id=str(uuid.uuid4()),
                user_agent="Test Agent",
            )

            assert result is not None
            mock_session.add.assert_called_once()
            mock_session.flush.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_log_event_database_error_returns_none(self):
        """Test that database errors return None instead of raising."""
        from app.services.audit_service import AuditService
        from biz2bricks_core import AuditAction, AuditEntityType
        from sqlalchemy.exc import SQLAlchemyError

        service = AuditService()
        org_id = str(uuid.uuid4())
        entity_id = str(uuid.uuid4())

        with patch('app.services.audit_service.db') as mock_db:
            mock_session = AsyncMock()
            mock_session.add = Mock(side_effect=SQLAlchemyError("Database error"))
            mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db.session.return_value.__aexit__ = AsyncMock()

            # Should NOT raise, should return None
            result = await service.log_event(
                org_id=org_id,
                action=AuditAction.CREATE,
                entity_type=AuditEntityType.USER,
                entity_id=entity_id,
            )

            assert result is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_log_event_unexpected_error_returns_none(self):
        """Test that unexpected errors return None instead of raising."""
        from app.services.audit_service import AuditService
        from biz2bricks_core import AuditAction, AuditEntityType

        service = AuditService()
        org_id = str(uuid.uuid4())
        entity_id = str(uuid.uuid4())

        with patch('app.services.audit_service.db') as mock_db:
            mock_session = AsyncMock()
            mock_session.add = Mock(side_effect=RuntimeError("Unexpected error"))
            mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db.session.return_value.__aexit__ = AsyncMock()

            # Should NOT raise, should return None
            result = await service.log_event(
                org_id=org_id,
                action=AuditAction.CREATE,
                entity_type=AuditEntityType.USER,
                entity_id=entity_id,
            )

            assert result is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_log_event_with_string_action(self):
        """Test logging with string action (not enum)."""
        from app.services.audit_service import AuditService

        service = AuditService()
        org_id = str(uuid.uuid4())
        entity_id = str(uuid.uuid4())

        with patch('app.services.audit_service.db') as mock_db:
            mock_session = AsyncMock()
            mock_session.add = Mock()
            mock_session.flush = AsyncMock()
            mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db.session.return_value.__aexit__ = AsyncMock()

            # Pass string instead of enum
            result = await service.log_event(
                org_id=org_id,
                action="CREATE",  # String instead of enum
                entity_type="USER",  # String instead of enum
                entity_id=entity_id,
            )

            assert result is not None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_log_event_without_optional_fields(self):
        """Test logging without optional fields."""
        from app.services.audit_service import AuditService
        from biz2bricks_core import AuditAction, AuditEntityType

        service = AuditService()
        org_id = str(uuid.uuid4())
        entity_id = str(uuid.uuid4())

        with patch('app.services.audit_service.db') as mock_db:
            mock_session = AsyncMock()
            mock_session.add = Mock()
            mock_session.flush = AsyncMock()
            mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db.session.return_value.__aexit__ = AsyncMock()

            result = await service.log_event(
                org_id=org_id,
                action=AuditAction.LOGIN,
                entity_type=AuditEntityType.USER,
                entity_id=entity_id,
                # No user_id, details, ip_address, session_id, user_agent
            )

            assert result is not None


class TestAuditServiceGetAuditLogs:
    """Tests for querying audit logs."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_audit_logs_basic(self):
        """Test basic audit log query."""
        from app.services.audit_service import AuditService
        from app.models.schemas import PaginationParams
        from biz2bricks_core import AuditLogModel

        service = AuditService()
        org_id = str(uuid.uuid4())
        pagination = PaginationParams(page=1, per_page=10)

        # Mock audit logs
        mock_log = Mock(spec=AuditLogModel)
        mock_log.to_dict.return_value = {
            "id": str(uuid.uuid4()),
            "organization_id": org_id,
            "action": "CREATE",
            "entity_type": "USER",
        }

        mock_count_result = Mock()
        mock_count_result.scalar.return_value = 1

        mock_logs_result = Mock()
        mock_logs_result.scalars.return_value.all.return_value = [mock_log]

        call_count = 0
        def mock_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_count_result
            return mock_logs_result

        with patch('app.services.audit_service.db') as mock_db:
            mock_session = AsyncMock()
            mock_session.execute = AsyncMock(side_effect=mock_execute)
            mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db.session.return_value.__aexit__ = AsyncMock()

            result = await service.get_audit_logs(org_id, pagination)

            assert "audit_logs" in result
            assert "total" in result
            assert "page" in result
            assert "per_page" in result
            assert "total_pages" in result

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_audit_logs_with_filters(self):
        """Test audit log query with filters."""
        from app.services.audit_service import AuditService
        from app.models.schemas import PaginationParams
        from biz2bricks_core import AuditAction, AuditEntityType

        service = AuditService()
        org_id = str(uuid.uuid4())
        pagination = PaginationParams(page=1, per_page=10)

        mock_count_result = Mock()
        mock_count_result.scalar.return_value = 0

        mock_logs_result = Mock()
        mock_logs_result.scalars.return_value.all.return_value = []

        call_count = 0
        def mock_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_count_result
            return mock_logs_result

        with patch('app.services.audit_service.db') as mock_db:
            mock_session = AsyncMock()
            mock_session.execute = AsyncMock(side_effect=mock_execute)
            mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db.session.return_value.__aexit__ = AsyncMock()

            result = await service.get_audit_logs(
                org_id,
                pagination,
                entity_type=AuditEntityType.USER,
                action=AuditAction.CREATE,
                start_date=datetime.now(timezone.utc) - timedelta(days=7),
                end_date=datetime.now(timezone.utc),
            )

            assert result["total"] == 0
            assert result["audit_logs"] == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_audit_logs_with_user_restriction(self):
        """Test audit log query with user restriction."""
        from app.services.audit_service import AuditService
        from app.models.schemas import PaginationParams

        service = AuditService()
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        pagination = PaginationParams(page=1, per_page=10)

        mock_count_result = Mock()
        mock_count_result.scalar.return_value = 0

        mock_logs_result = Mock()
        mock_logs_result.scalars.return_value.all.return_value = []

        call_count = 0
        def mock_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_count_result
            return mock_logs_result

        with patch('app.services.audit_service.db') as mock_db:
            mock_session = AsyncMock()
            mock_session.execute = AsyncMock(side_effect=mock_execute)
            mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db.session.return_value.__aexit__ = AsyncMock()

            result = await service.get_audit_logs(
                org_id,
                pagination,
                restrict_to_user=user_id,
            )

            assert result["total"] == 0

class TestAuditServiceGetEntityHistory:
    """Tests for entity history queries."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_entity_history_success(self):
        """Test getting entity history."""
        from app.services.audit_service import AuditService
        from biz2bricks_core import AuditEntityType, AuditLogModel

        service = AuditService()
        org_id = str(uuid.uuid4())
        entity_id = str(uuid.uuid4())

        mock_log = Mock(spec=AuditLogModel)
        mock_log.to_dict.return_value = {
            "id": str(uuid.uuid4()),
            "entity_id": entity_id,
            "action": "CREATE",
        }

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mock_log]

        with patch('app.services.audit_service.db') as mock_db:
            mock_session = AsyncMock()
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db.session.return_value.__aexit__ = AsyncMock()

            result = await service.get_entity_history(
                org_id=org_id,
                entity_type=AuditEntityType.DOCUMENT,
                entity_id=entity_id,
            )

            assert len(result) == 1
            assert result[0]["entity_id"] == entity_id

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_entity_history_with_limit(self):
        """Test getting entity history with custom limit."""
        from app.services.audit_service import AuditService
        from biz2bricks_core import AuditEntityType

        service = AuditService()
        org_id = str(uuid.uuid4())
        entity_id = str(uuid.uuid4())

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []

        with patch('app.services.audit_service.db') as mock_db:
            mock_session = AsyncMock()
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db.session.return_value.__aexit__ = AsyncMock()

            result = await service.get_entity_history(
                org_id=org_id,
                entity_type=AuditEntityType.USER,
                entity_id=entity_id,
                limit=10,
            )

            assert result == []

class TestAuditServiceGetUserActivity:
    """Tests for user activity queries."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_user_activity_delegates_to_get_audit_logs(self):
        """Test that get_user_activity delegates to get_audit_logs."""
        from app.services.audit_service import AuditService
        from app.models.schemas import PaginationParams

        service = AuditService()
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        pagination = PaginationParams(page=1, per_page=10)

        expected_result = {
            "audit_logs": [],
            "total": 0,
            "page": 1,
            "per_page": 10,
            "total_pages": 0,
        }

        with patch.object(service, 'get_audit_logs', return_value=expected_result) as mock_get_logs:
            result = await service.get_user_activity(
                org_id=org_id,
                user_id=user_id,
                pagination=pagination,
            )

            mock_get_logs.assert_called_once_with(
                org_id=org_id,
                pagination=pagination,
                user_id=user_id,
                action=None,
                start_date=None,
                end_date=None,
            )
            assert result == expected_result


class TestAuditEnumConversion:
    """Tests for enum value conversion."""

    @pytest.mark.unit
    def test_audit_action_value_extraction(self):
        """Test extracting value from AuditAction enum."""
        from biz2bricks_core import AuditAction

        action = AuditAction.CREATE

        # When it's an enum
        if isinstance(action, AuditAction):
            value = action.value
        else:
            value = action

        assert value == "CREATE"

    @pytest.mark.unit
    def test_audit_entity_type_value_extraction(self):
        """Test extracting value from AuditEntityType enum."""
        from biz2bricks_core import AuditEntityType

        entity_type = AuditEntityType.USER

        # When it's an enum
        if isinstance(entity_type, AuditEntityType):
            value = entity_type.value
        else:
            value = entity_type

        assert value == "USER"

    @pytest.mark.unit
    def test_string_action_passthrough(self):
        """Test that string action passes through correctly."""
        action = "CREATE"

        # When it's already a string
        from biz2bricks_core import AuditAction
        if isinstance(action, AuditAction):
            value = action.value
        else:
            value = action

        assert value == "CREATE"
