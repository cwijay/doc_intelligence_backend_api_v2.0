from typing import Optional
import math
import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

from app.models.organization import Organization
from app.models.schemas import (
    OrganizationCreate,
    OrganizationUpdate,
    OrganizationResponse,
    OrganizationList,
    PaginationParams,
    OrganizationFilters,
)
from biz2bricks_core import db, OrganizationModel, AuditAction, AuditEntityType
from app.core.logging import get_service_logger
from app.core.cache import cached_organizations, invalidate_organization
from app.services.audit_service import audit_service

logger = get_service_logger("organization")


class OrganizationNotFoundError(Exception):
    """Organization not found error."""

    pass


class OrganizationAlreadyExistsError(Exception):
    """Organization already exists error."""

    pass


class OrganizationService:
    """Service for managing organizations with multi-tenancy support."""

    def __init__(self):
        self.logger = logger

    def _model_to_pydantic(self, model: OrganizationModel) -> Organization:
        """Convert SQLAlchemy model to Pydantic model."""
        return Organization(
            id=model.id,
            name=model.name,
            domain=model.domain,
            plan_type=model.plan_type,
            settings=model.settings or {},
            is_active=model.is_active,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _ensure_response_model(
        self, data: OrganizationResponse | dict
    ) -> OrganizationResponse:
        """Ensure cached data is converted back to Pydantic model.

        fastapi-cache2 serializes responses to JSON dicts when caching.
        This method ensures we always return a proper Pydantic model.
        """
        if isinstance(data, dict):
            return OrganizationResponse.model_validate(data)
        return data

    async def create_organization(
        self,
        org_data: OrganizationCreate,
        created_by_user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        session_id: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> OrganizationResponse:
        """
        Create a new organization.

        Args:
            org_data: Organization creation data
            created_by_user_id: ID of user who created this org (for audit)
            ip_address: Client IP address (for audit)
            session_id: Session ID (for audit)
            user_agent: Client user agent (for audit)

        Returns:
            Created organization response

        Raises:
            OrganizationAlreadyExistsError: If organization name already exists
        """
        try:
            async with db.session() as session:
                # Check if organization with same name already exists
                stmt = select(OrganizationModel).where(
                    OrganizationModel.name == org_data.name,
                    OrganizationModel.is_active == True,
                )
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()

                if existing:
                    raise OrganizationAlreadyExistsError(
                        f"Organization with name '{org_data.name}' already exists"
                    )

                # Create new organization
                org_id = str(uuid4())
                now = datetime.now(timezone.utc)

                org_model = OrganizationModel(
                    id=org_id,
                    name=org_data.name,
                    domain=org_data.domain,
                    settings=org_data.settings or {},
                    plan_type=(
                        org_data.plan_type.value
                        if hasattr(org_data.plan_type, "value")
                        else org_data.plan_type
                    ),
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )

                session.add(org_model)
                await session.flush()

                org = self._model_to_pydantic(org_model)
                self.logger.info("Organization created", org_id=org_id, name=org.name)

                # Audit logging (non-blocking)
                asyncio.create_task(
                    audit_service.log_event(
                        org_id=org_id,
                        action=AuditAction.CREATE,
                        entity_type=AuditEntityType.ORGANIZATION,
                        entity_id=org_id,
                        user_id=created_by_user_id,
                        details={
                            "new_values": {
                                "name": org.name,
                                "domain": org.domain,
                                "plan_type": org.plan_type,
                            },
                            "operation": "create",
                        },
                        ip_address=ip_address,
                        session_id=session_id,
                        user_agent=user_agent,
                    )
                )

                return OrganizationResponse.model_validate(org)

        except OrganizationAlreadyExistsError:
            raise
        except IntegrityError as e:
            self.logger.error("Database integrity error", error=str(e))
            raise OrganizationAlreadyExistsError(
                f"Organization with name '{org_data.name}' already exists"
            )
        except Exception as e:
            self.logger.error("Error creating organization", error=str(e))
            raise

    async def get_organization(self, org_id: str) -> OrganizationResponse:
        """
        Get organization by ID.

        Args:
            org_id: Organization ID

        Returns:
            Organization response (cached for 30 minutes)

        Raises:
            OrganizationNotFoundError: If organization not found
        """
        result = await self._get_organization_cached(org_id)
        return self._ensure_response_model(result)

    @cached_organizations()
    async def _get_organization_cached(self, org_id: str) -> OrganizationResponse:
        """Internal cached method for fetching organization."""
        try:
            async with db.session() as session:
                stmt = select(OrganizationModel).where(
                    OrganizationModel.id == org_id, OrganizationModel.is_active == True
                )
                result = await session.execute(stmt)
                org_model = result.scalar_one_or_none()

                if not org_model:
                    raise OrganizationNotFoundError(
                        f"Organization with ID {org_id} not found"
                    )

                org = self._model_to_pydantic(org_model)
                self.logger.debug("Organization retrieved", org_id=org_id)

                return OrganizationResponse.model_validate(org)

        except OrganizationNotFoundError:
            raise
        except Exception as e:
            self.logger.error(
                "Error retrieving organization", org_id=org_id, error=str(e)
            )
            raise

    async def update_organization(
        self,
        org_id: str,
        update_data: OrganizationUpdate,
        updated_by_user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        session_id: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> OrganizationResponse:
        """
        Update organization.

        Args:
            org_id: Organization ID
            update_data: Update data
            updated_by_user_id: ID of user who updated this org (for audit)
            ip_address: Client IP address (for audit)
            session_id: Session ID (for audit)
            user_agent: Client user agent (for audit)

        Returns:
            Updated organization response

        Raises:
            OrganizationNotFoundError: If organization not found
            OrganizationAlreadyExistsError: If name conflict occurs
        """
        try:
            async with db.session() as session:
                # Get existing organization
                stmt = select(OrganizationModel).where(
                    OrganizationModel.id == org_id, OrganizationModel.is_active == True
                )
                result = await session.execute(stmt)
                org_model = result.scalar_one_or_none()

                if not org_model:
                    raise OrganizationNotFoundError(
                        f"Organization with ID {org_id} not found"
                    )

                # Capture old values for audit
                old_values = {
                    "name": org_model.name,
                    "domain": org_model.domain,
                    "plan_type": org_model.plan_type,
                }

                # Check name uniqueness if name is being updated
                if update_data.name and update_data.name != org_model.name:
                    name_check = select(OrganizationModel).where(
                        OrganizationModel.name == update_data.name,
                        OrganizationModel.id != org_id,
                        OrganizationModel.is_active == True,
                    )
                    name_result = await session.execute(name_check)
                    if name_result.scalar_one_or_none():
                        raise OrganizationAlreadyExistsError(
                            f"Organization with name '{update_data.name}' already exists"
                        )

                # Update fields
                update_fields = update_data.model_dump(exclude_unset=True)
                for field, value in update_fields.items():
                    if field == "plan_type" and hasattr(value, "value"):
                        value = value.value
                    setattr(org_model, field, value)

                org_model.updated_at = datetime.now(timezone.utc)
                await session.flush()

                org = self._model_to_pydantic(org_model)
                self.logger.info(
                    "Organization updated",
                    org_id=org_id,
                    updates=list(update_fields.keys()),
                )

                # Capture new values and calculate changes
                new_values = {
                    "name": org.name,
                    "domain": org.domain,
                    "plan_type": org.plan_type,
                }
                changes = {}
                for key in new_values:
                    if old_values.get(key) != new_values.get(key):
                        changes[key] = {
                            "old": old_values.get(key),
                            "new": new_values.get(key),
                        }

                # Invalidate cache
                asyncio.create_task(invalidate_organization(org_id))

                # Audit logging (non-blocking)
                asyncio.create_task(
                    audit_service.log_event(
                        org_id=org_id,
                        action=AuditAction.UPDATE,
                        entity_type=AuditEntityType.ORGANIZATION,
                        entity_id=org_id,
                        user_id=updated_by_user_id,
                        details={
                            "old_values": old_values,
                            "new_values": new_values,
                            "changes": changes,
                            "operation": "update",
                        },
                        ip_address=ip_address,
                        session_id=session_id,
                        user_agent=user_agent,
                    )
                )

                return OrganizationResponse.model_validate(org)

        except (OrganizationNotFoundError, OrganizationAlreadyExistsError):
            raise
        except Exception as e:
            self.logger.error(
                "Error updating organization", org_id=org_id, error=str(e)
            )
            raise

    async def list_organizations(
        self,
        pagination: PaginationParams,
        filters: Optional[OrganizationFilters] = None,
    ) -> OrganizationList:
        """
        List organizations with pagination and filtering.

        Args:
            pagination: Pagination parameters
            filters: Optional filters

        Returns:
            Paginated organization list
        """
        try:
            async with db.session() as session:
                # Build base query
                stmt = select(OrganizationModel).where(
                    OrganizationModel.is_active == True
                )

                # Apply filters
                if filters:
                    if filters.plan_type:
                        plan_value = (
                            filters.plan_type.value
                            if hasattr(filters.plan_type, "value")
                            else filters.plan_type
                        )
                        stmt = stmt.where(OrganizationModel.plan_type == plan_value)

                    if filters.is_active is not None:
                        stmt = stmt.where(
                            OrganizationModel.is_active == filters.is_active
                        )

                    if filters.name:
                        stmt = stmt.where(
                            OrganizationModel.name.ilike(f"%{filters.name}%")
                        )

                    if filters.domain:
                        stmt = stmt.where(
                            OrganizationModel.domain.ilike(f"%{filters.domain}%")
                        )

                # Get total count
                count_stmt = select(func.count()).select_from(stmt.subquery())
                count_result = await session.execute(count_stmt)
                total = count_result.scalar() or 0

                # Apply ordering and pagination
                stmt = stmt.order_by(OrganizationModel.created_at.desc())
                stmt = stmt.offset(pagination.offset).limit(pagination.per_page)

                result = await session.execute(stmt)
                org_models = result.scalars().all()

                # Convert to response models
                org_responses = [
                    OrganizationResponse.model_validate(self._model_to_pydantic(m))
                    for m in org_models
                ]

                # Calculate pagination info
                total_pages = math.ceil(total / pagination.per_page) if total > 0 else 0

                self.logger.debug(
                    "Organizations listed",
                    count=len(org_responses),
                    total=total,
                    page=pagination.page,
                )

                return OrganizationList(
                    items=org_responses,
                    total=total,
                    page=pagination.page,
                    per_page=pagination.per_page,
                    total_pages=total_pages,
                )

        except Exception as e:
            self.logger.error("Error listing organizations", error=str(e))
            raise

    async def delete_organization(
        self,
        org_id: str,
        deleted_by_user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        session_id: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> bool:
        """
        Soft delete organization (set is_active=False).

        Args:
            org_id: Organization ID
            deleted_by_user_id: ID of user who deleted this org (for audit)
            ip_address: Client IP address (for audit)
            session_id: Session ID (for audit)
            user_agent: Client user agent (for audit)

        Returns:
            True if deleted successfully

        Raises:
            OrganizationNotFoundError: If organization not found
        """
        try:
            async with db.session() as session:
                stmt = select(OrganizationModel).where(
                    OrganizationModel.id == org_id, OrganizationModel.is_active == True
                )
                result = await session.execute(stmt)
                org_model = result.scalar_one_or_none()

                if not org_model:
                    raise OrganizationNotFoundError(
                        f"Organization with ID {org_id} not found"
                    )

                # Capture org info for audit before delete
                deleted_org_info = {
                    "name": org_model.name,
                    "domain": org_model.domain,
                    "plan_type": org_model.plan_type,
                }

                # Soft delete
                org_model.is_active = False
                org_model.updated_at = datetime.now(timezone.utc)
                await session.flush()

                self.logger.info(
                    "Organization deleted", org_id=org_id, name=org_model.name
                )

                # Invalidate cache
                asyncio.create_task(invalidate_organization(org_id))

                # Audit logging (non-blocking)
                asyncio.create_task(
                    audit_service.log_event(
                        org_id=org_id,
                        action=AuditAction.DELETE,
                        entity_type=AuditEntityType.ORGANIZATION,
                        entity_id=org_id,
                        user_id=deleted_by_user_id,
                        details={
                            "deleted_values": deleted_org_info,
                            "operation": "delete",
                        },
                        ip_address=ip_address,
                        session_id=session_id,
                        user_agent=user_agent,
                    )
                )

                return True

        except OrganizationNotFoundError:
            raise
        except Exception as e:
            self.logger.error(
                "Error deleting organization", org_id=org_id, error=str(e)
            )
            raise

    async def get_organization_by_name(
        self, name: str
    ) -> Optional[OrganizationResponse]:
        """
        Get organization by name.

        Args:
            name: Organization name

        Returns:
            Organization response or None if not found
        """
        try:
            async with db.session() as session:
                stmt = select(OrganizationModel).where(
                    OrganizationModel.name == name, OrganizationModel.is_active == True
                )
                result = await session.execute(stmt)
                org_model = result.scalar_one_or_none()

                if not org_model:
                    return None

                org = self._model_to_pydantic(org_model)
                return OrganizationResponse.model_validate(org)

        except Exception as e:
            self.logger.error(
                "Error getting organization by name", name=name, error=str(e)
            )
            raise


# Global service instance
organization_service = OrganizationService()
