"""
Audit Service - Non-blocking audit logging for compliance and debugging.

Design principles:
- Non-blocking: Audit failures should NEVER fail the main operation
- Async-first: All database operations are async
- Flexible: JSONB details field supports any audit metadata
- Queryable: Indexed for common query patterns
"""

import math
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select, and_, func
from sqlalchemy.exc import SQLAlchemyError

from biz2bricks_core import db, AuditLogModel, AuditAction, AuditEntityType
from app.core.logging import get_service_logger
from app.models.schemas import PaginationParams

logger = get_service_logger("audit")


class AuditService:
    """
    Service for non-blocking audit logging.

    Key features:
    - Fire-and-forget logging (non-blocking)
    - Comprehensive query capabilities for admin dashboards
    - User activity filtering for self-service access
    """

    def __init__(self):
        self.logger = logger

    async def log_event(
        self,
        org_id: str,
        action: AuditAction,
        entity_type: AuditEntityType,
        entity_id: str,
        user_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        session_id: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Optional[str]:
        """
        Log an audit event (non-blocking).

        This method should NEVER raise exceptions to the caller.
        Failures are logged but don't propagate.

        Args:
            org_id: Organization ID
            action: Action type (CREATE, UPDATE, DELETE, etc.)
            entity_type: Entity type (ORGANIZATION, USER, FOLDER, DOCUMENT)
            entity_id: ID of the affected entity
            user_id: ID of user who performed the action (optional for system actions)
            details: Additional details as JSON (old_values, new_values, metadata)
            ip_address: Client IP address
            session_id: Session identifier
            user_agent: Client user agent string

        Returns:
            Audit log ID if successful, None if failed
        """
        try:
            async with db.session() as session:
                audit_id = str(uuid4())

                # Convert enums to string values
                action_value = (
                    action.value if isinstance(action, AuditAction) else action
                )
                entity_type_value = (
                    entity_type.value
                    if isinstance(entity_type, AuditEntityType)
                    else entity_type
                )

                audit_log = AuditLogModel(
                    id=audit_id,
                    organization_id=org_id,
                    user_id=user_id,
                    action=action_value,
                    entity_type=entity_type_value,
                    entity_id=entity_id,
                    details=details or {},
                    ip_address=ip_address,
                    session_id=session_id,
                    user_agent=user_agent,
                    created_at=datetime.now(timezone.utc),
                )

                session.add(audit_log)
                await session.flush()

                self.logger.debug(
                    "Audit event logged",
                    audit_id=audit_id,
                    org_id=org_id,
                    action=action_value,
                    entity_type=entity_type_value,
                    entity_id=entity_id,
                )

                return audit_id

        except SQLAlchemyError as e:
            # Log the error but DON'T propagate - audit failures shouldn't break operations
            self.logger.error(
                "Failed to log audit event",
                org_id=org_id,
                action=action.value if isinstance(action, AuditAction) else action,
                entity_type=(
                    entity_type.value
                    if isinstance(entity_type, AuditEntityType)
                    else entity_type
                ),
                entity_id=entity_id,
                error=str(e),
            )
            return None
        except Exception as e:
            self.logger.error(
                "Unexpected error logging audit event",
                org_id=org_id,
                error=str(e),
            )
            return None

    async def get_audit_logs(
        self,
        org_id: str,
        pagination: PaginationParams,
        entity_type: Optional[AuditEntityType] = None,
        entity_id: Optional[str] = None,
        user_id: Optional[str] = None,
        action: Optional[AuditAction] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        restrict_to_user: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Query audit logs with filtering and pagination.

        Args:
            org_id: Organization ID (required for multi-tenant isolation)
            pagination: Pagination parameters
            entity_type: Filter by entity type
            entity_id: Filter by specific entity ID
            user_id: Filter by user who performed actions
            action: Filter by action type
            start_date: Filter by start date
            end_date: Filter by end date
            restrict_to_user: If set, only return logs where user_id matches this value
                              (used for non-admin users viewing their own activity)

        Returns:
            Dictionary with audit logs and pagination info
        """
        try:
            async with db.session() as session:
                # Build base query
                stmt = select(AuditLogModel).where(
                    AuditLogModel.organization_id == org_id
                )

                # Apply user restriction for non-admin users
                if restrict_to_user:
                    stmt = stmt.where(AuditLogModel.user_id == restrict_to_user)

                # Apply filters
                if entity_type:
                    type_value = (
                        entity_type.value
                        if isinstance(entity_type, AuditEntityType)
                        else entity_type
                    )
                    stmt = stmt.where(AuditLogModel.entity_type == type_value)

                if entity_id:
                    stmt = stmt.where(AuditLogModel.entity_id == entity_id)

                if user_id:
                    stmt = stmt.where(AuditLogModel.user_id == user_id)

                if action:
                    action_value = (
                        action.value if isinstance(action, AuditAction) else action
                    )
                    stmt = stmt.where(AuditLogModel.action == action_value)

                if start_date:
                    stmt = stmt.where(AuditLogModel.created_at >= start_date)

                if end_date:
                    stmt = stmt.where(AuditLogModel.created_at <= end_date)

                # Get total count
                count_stmt = select(func.count()).select_from(stmt.subquery())
                count_result = await session.execute(count_stmt)
                total = count_result.scalar() or 0

                # Apply ordering and pagination
                stmt = stmt.order_by(AuditLogModel.created_at.desc())
                stmt = stmt.offset(pagination.offset).limit(pagination.per_page)

                result = await session.execute(stmt)
                audit_logs = result.scalars().all()

                total_pages = math.ceil(total / pagination.per_page) if total > 0 else 0

                return {
                    "audit_logs": [log.to_dict() for log in audit_logs],
                    "total": total,
                    "page": pagination.page,
                    "per_page": pagination.per_page,
                    "total_pages": total_pages,
                }

        except Exception as e:
            self.logger.error(
                "Error querying audit logs",
                org_id=org_id,
                error=str(e),
            )
            raise

    async def get_entity_history(
        self,
        org_id: str,
        entity_type: AuditEntityType,
        entity_id: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Get complete history of a specific entity.

        Useful for viewing all changes to a document, user, or folder.

        Args:
            org_id: Organization ID
            entity_type: Entity type
            entity_id: Entity ID
            limit: Maximum number of records to return

        Returns:
            List of audit log entries for the entity
        """
        try:
            async with db.session() as session:
                type_value = (
                    entity_type.value
                    if isinstance(entity_type, AuditEntityType)
                    else entity_type
                )

                stmt = (
                    select(AuditLogModel)
                    .where(
                        and_(
                            AuditLogModel.organization_id == org_id,
                            AuditLogModel.entity_type == type_value,
                            AuditLogModel.entity_id == entity_id,
                        )
                    )
                    .order_by(AuditLogModel.created_at.desc())
                    .limit(limit)
                )

                result = await session.execute(stmt)
                audit_logs = result.scalars().all()

                return [log.to_dict() for log in audit_logs]

        except Exception as e:
            self.logger.error(
                "Error getting entity history",
                org_id=org_id,
                entity_type=entity_type,
                entity_id=entity_id,
                error=str(e),
            )
            raise

    async def get_user_activity(
        self,
        org_id: str,
        user_id: str,
        pagination: PaginationParams,
        action: Optional[AuditAction] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Get activity history for a specific user.

        Convenience method for users viewing their own activity.

        Args:
            org_id: Organization ID
            user_id: User ID to get activity for
            pagination: Pagination parameters
            action: Filter by action type
            start_date: Filter by start date
            end_date: Filter by end date

        Returns:
            Dictionary with audit logs and pagination info
        """
        return await self.get_audit_logs(
            org_id=org_id,
            pagination=pagination,
            user_id=user_id,
            action=action,
            start_date=start_date,
            end_date=end_date,
        )


# Global service instance
audit_service = AuditService()
