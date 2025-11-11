from typing import Optional
import math
from datetime import datetime

from google.cloud.firestore_v1 import FieldFilter

from app.models.organization import Organization
from app.models.schemas import (
    OrganizationCreate,
    OrganizationUpdate,
    OrganizationResponse,
    OrganizationList,
    PaginationParams,
    OrganizationFilters,
)
from app.core.firebase_client import (
    get_collection,
)
from app.core.logging import get_service_logger

logger = get_service_logger("organization")


class OrganizationNotFoundError(Exception):
    """Organization not found error."""

    pass


class OrganizationAlreadyExistsError(Exception):
    """Organization already exists error."""

    pass


class OrganizationService:
    """Service for managing organizations with multi-tenancy support."""

    COLLECTION_NAME = "organizations"

    def __init__(self):
        self.logger = logger

    async def create_organization(
        self, org_data: OrganizationCreate
    ) -> OrganizationResponse:
        """
        Create a new organization.

        Args:
            org_data: Organization creation data

        Returns:
            Created organization response

        Raises:
            OrganizationAlreadyExistsError: If organization name already exists
        """
        try:
            # Check if organization with same name already exists
            existing_org = await self._get_organization_by_name(org_data.name)
            if existing_org and existing_org.is_active:
                raise OrganizationAlreadyExistsError(
                    f"Organization with name '{org_data.name}' already exists"
                )

            # Create new organization
            org = Organization(
                name=org_data.name,
                domain=org_data.domain,
                settings=org_data.settings,
                plan_type=org_data.plan_type,
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )

            # Add to Firestore
            collection = get_collection(self.COLLECTION_NAME)
            timestamp, doc_ref = await collection.add(org.to_dict())
            org_id = doc_ref.id
            org.id = org_id

            self.logger.info("Organization created", org_id=org_id, name=org.name)

            return OrganizationResponse.model_validate(org)

        except OrganizationAlreadyExistsError:
            raise
        except Exception as e:
            self.logger.error("Error creating organization", error=str(e))
            raise

    async def get_organization(self, org_id: str) -> OrganizationResponse:
        """
        Get organization by ID.

        Args:
            org_id: Organization ID (Firestore document ID)

        Returns:
            Organization response

        Raises:
            OrganizationNotFoundError: If organization not found
        """
        try:
            doc_ref = get_collection(self.COLLECTION_NAME).document(org_id)
            doc = await doc_ref.get()

            if not doc.exists:
                raise OrganizationNotFoundError(
                    f"Organization with ID {org_id} not found"
                )

            org_data = doc.to_dict()
            org = Organization.from_dict(org_data, doc.id)

            if not org.is_active:
                raise OrganizationNotFoundError(
                    f"Organization with ID {org_id} not found"
                )

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
        self, org_id: str, update_data: OrganizationUpdate
    ) -> OrganizationResponse:
        """
        Update organization.

        Args:
            org_id: Organization ID (Firestore document ID)
            update_data: Update data

        Returns:
            Updated organization response

        Raises:
            OrganizationNotFoundError: If organization not found
            OrganizationAlreadyExistsError: If name conflict occurs
        """
        try:
            # Get existing organization
            doc_ref = get_collection(self.COLLECTION_NAME).document(org_id)
            doc = await doc_ref.get()

            if not doc.exists:
                raise OrganizationNotFoundError(
                    f"Organization with ID {org_id} not found"
                )

            org_data = doc.to_dict()
            org = Organization.from_dict(org_data, doc.id)

            if not org.is_active:
                raise OrganizationNotFoundError(
                    f"Organization with ID {org_id} not found"
                )

            # Check name uniqueness if name is being updated
            if update_data.name and update_data.name != org.name:
                existing_org = await self._get_organization_by_name(update_data.name)
                if (
                    existing_org
                    and existing_org.id != org_id
                    and existing_org.is_active
                ):
                    raise OrganizationAlreadyExistsError(
                        f"Organization with name '{update_data.name}' already exists"
                    )

            # Update fields
            update_fields = update_data.model_dump(exclude_unset=True)
            for field, value in update_fields.items():
                setattr(org, field, value)

            # Update timestamp
            org.update_timestamp()

            # Save to Firestore
            await doc_ref.update(org.to_dict())

            self.logger.info(
                "Organization updated",
                org_id=org_id,
                updates=list(update_fields.keys()),
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
            collection = get_collection(self.COLLECTION_NAME)

            # Build query with filters
            query = collection
            firestore_filters = []

            # Always filter for active organizations
            firestore_filters.append(FieldFilter("is_active", "==", True))

            if filters:
                if filters.plan_type:
                    firestore_filters.append(
                        FieldFilter("plan_type", "==", filters.plan_type.value)
                    )

                if filters.is_active is not None:
                    # Update the active filter
                    firestore_filters[-1] = FieldFilter(
                        "is_active", "==", filters.is_active
                    )

            # Apply filters
            for filter_obj in firestore_filters:
                query = query.where(filter=filter_obj)

            # Order by created_at descending
            from google.cloud.firestore import Query

            query = query.order_by("created_at", direction=Query.DESCENDING)

            # Get all documents for filtering and counting
            docs = query.stream()
            all_organizations = []

            async for doc in docs:
                org_data = doc.to_dict()
                org = Organization.from_dict(org_data, doc.id)

                # Apply client-side filters for text search (Firestore doesn't support ILIKE)
                if filters:
                    if filters.name and filters.name.lower() not in org.name.lower():
                        continue
                    if (
                        filters.domain
                        and org.domain
                        and filters.domain.lower() not in org.domain.lower()
                    ):
                        continue

                all_organizations.append(org)

            # Get total count
            total = len(all_organizations)

            # Apply pagination
            start_idx = pagination.offset
            end_idx = start_idx + pagination.per_page
            paginated_orgs = all_organizations[start_idx:end_idx]

            # Convert to response models
            org_responses = [
                OrganizationResponse.model_validate(org) for org in paginated_orgs
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

    async def delete_organization(self, org_id: str) -> bool:
        """
        Soft delete organization (set is_active=False).

        Args:
            org_id: Organization ID (Firestore document ID)

        Returns:
            True if deleted successfully

        Raises:
            OrganizationNotFoundError: If organization not found
        """
        try:
            # Get organization
            doc_ref = get_collection(self.COLLECTION_NAME).document(org_id)
            doc = await doc_ref.get()

            if not doc.exists:
                raise OrganizationNotFoundError(
                    f"Organization with ID {org_id} not found"
                )

            org_data = doc.to_dict()
            org = Organization.from_dict(org_data, doc.id)

            if not org.is_active:
                raise OrganizationNotFoundError(
                    f"Organization with ID {org_id} not found"
                )

            # Soft delete - update is_active to False
            await doc_ref.update(
                {"is_active": False, "updated_at": datetime.utcnow().isoformat()}
            )

            self.logger.info("Organization deleted", org_id=org_id, name=org.name)

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
            org = await self._get_organization_by_name(name)
            return OrganizationResponse.model_validate(org) if org else None
        except Exception as e:
            self.logger.error(
                "Error getting organization by name", name=name, error=str(e)
            )
            raise

    # Private helper methods
    async def _get_organization_by_name(self, name: str) -> Optional[Organization]:
        """Get organization by name (internal method)."""
        try:
            collection = get_collection(self.COLLECTION_NAME)
            query = collection.where(filter=FieldFilter("name", "==", name))

            docs = query.stream()
            async for doc in docs:
                org_data = doc.to_dict()
                org = Organization.from_dict(org_data, doc.id)
                return org

            return None
        except Exception as e:
            self.logger.error(
                "Error getting organization by name", name=name, error=str(e)
            )
            return None


# Global service instance
organization_service = OrganizationService()
