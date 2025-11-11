from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Query, status
from app.core.logging import get_service_logger
from app.services.org_service import (
    organization_service,
    OrganizationNotFoundError,
    OrganizationAlreadyExistsError,
)
from app.models.schemas import (
    OrganizationCreateRequest,
    OrganizationUpdateRequest,
    OrganizationResponse,
    OrganizationList,
    OrganizationDeleteResponse,
    PaginationParams,
    OrganizationFilters,
    PlanType,
)

logger = get_service_logger("organization_api")

router = APIRouter(prefix="/organizations")


@router.post(
    "/",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new organization",
    description="Create a new organization with the provided details. Organization name must be unique.",
)
async def create_organization(
    organization: OrganizationCreateRequest,
) -> OrganizationResponse:
    """
    Create a new organization.

    - **name**: Unique organization name (required)
    - **domain**: Organization domain (optional)
    - **settings**: Organization settings as JSON object
    - **plan_type**: Plan type (FREE, STARTER, PRO)
    """
    try:
        logger.info("Creating organization", name=organization.name)

        result = await organization_service.create_organization(organization)

        logger.info(
            "Organization created successfully", org_id=str(result.id), name=result.name
        )

        return result

    except OrganizationAlreadyExistsError as e:
        logger.warning(
            "Organization creation failed - name exists",
            name=organization.name,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Organization with name '{organization.name}' already exists",
        )
    except Exception as e:
        logger.error(
            "Failed to create organization", name=organization.name, error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while creating organization",
        )


@router.get(
    "/{org_id}",
    response_model=OrganizationResponse,
    summary="Get organization by ID",
    description="Retrieve a specific organization by its unique identifier.",
)
async def get_organization(org_id: str) -> OrganizationResponse:
    """
    Get organization by ID.

    - **org_id**: ID of the organization to retrieve
    """
    try:
        logger.debug("Retrieving organization", org_id=org_id)

        result = await organization_service.get_organization(org_id)

        return result

    except OrganizationNotFoundError:
        logger.warning("Organization not found", org_id=org_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization with ID {org_id} not found",
        )
    except Exception as e:
        logger.error("Failed to retrieve organization", org_id=org_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while retrieving organization",
        )


@router.put(
    "/{org_id}",
    response_model=OrganizationResponse,
    summary="Update organization",
    description="Update an existing organization's details. Only provided fields will be updated.",
)
async def update_organization(
    org_id: str, organization: OrganizationUpdateRequest
) -> OrganizationResponse:
    """
    Update organization by ID.

    - **org_id**: ID of the organization to update
    - **name**: New organization name (optional)
    - **domain**: New organization domain (optional)
    - **settings**: Updated settings (optional)
    - **plan_type**: New plan type (optional)
    """
    try:
        logger.info("Updating organization", org_id=org_id)

        result = await organization_service.update_organization(org_id, organization)

        logger.info(
            "Organization updated successfully", org_id=org_id, name=result.name
        )

        return result

    except OrganizationNotFoundError:
        logger.warning("Organization update failed - not found", org_id=org_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization with ID {org_id} not found",
        )
    except OrganizationAlreadyExistsError as e:
        logger.warning(
            "Organization update failed - name conflict", org_id=org_id, error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization name already exists",
        )
    except Exception as e:
        logger.error("Failed to update organization", org_id=org_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while updating organization",
        )


@router.get(
    "/",
    response_model=OrganizationList,
    summary="List organizations",
    description="Retrieve a paginated list of organizations with optional filtering.",
)
async def list_organizations(
    page: int = Query(default=1, ge=1, description="Page number (starts from 1)"),
    per_page: int = Query(
        default=20, ge=1, le=100, description="Items per page (max 100)"
    ),
    name: str = Query(
        default=None, description="Filter by organization name (partial match)"
    ),
    domain: str = Query(default=None, description="Filter by domain (partial match)"),
    plan_type: PlanType = Query(default=None, description="Filter by plan type"),
    is_active: bool = Query(default=None, description="Filter by active status"),
) -> OrganizationList:
    """
    List organizations with pagination and filtering.

    Query Parameters:
    - **page**: Page number (default: 1)
    - **per_page**: Items per page (default: 20, max: 100)
    - **name**: Filter by organization name (partial match)
    - **domain**: Filter by domain (partial match)
    - **plan_type**: Filter by plan type (FREE, STARTER, PRO)
    - **is_active**: Filter by active status (true/false)
    """
    try:
        # Create pagination parameters
        pagination = PaginationParams(page=page, per_page=per_page)

        # Create filters (only include non-None values)
        filters = OrganizationFilters(
            name=name, domain=domain, plan_type=plan_type, is_active=is_active
        )

        logger.debug(
            "Listing organizations",
            page=page,
            per_page=per_page,
            filters=filters.model_dump(exclude_none=True),
        )

        result = await organization_service.list_organizations(pagination, filters)

        logger.debug(
            "Organizations listed successfully",
            count=len(result.organizations),
            total=result.total,
        )

        return result

    except Exception as e:
        logger.error("Failed to list organizations", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while listing organizations",
        )


@router.delete(
    "/{org_id}",
    response_model=OrganizationDeleteResponse,
    summary="Delete organization",
    description="Soft delete an organization by setting it as inactive. This operation cannot be undone via API.",
)
async def delete_organization(org_id: str) -> OrganizationDeleteResponse:
    """
    Soft delete organization by ID.

    - **org_id**: ID of the organization to delete

    Note: This performs a soft delete by marking the organization as inactive.
    The organization data is preserved but will not appear in normal queries.
    """
    try:
        logger.info("Deleting organization", org_id=org_id)

        success = await organization_service.delete_organization(org_id)

        if success:
            logger.info("Organization deleted successfully", org_id=org_id)
            return OrganizationDeleteResponse(
                success=True,
                message=f"Organization {org_id} has been deleted successfully",
            )
        else:
            logger.error("Organization deletion failed unexpectedly", org_id=org_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete organization",
            )

    except OrganizationNotFoundError:
        logger.warning("Organization deletion failed - not found", org_id=org_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization with ID {org_id} not found",
        )
    except Exception as e:
        logger.error("Failed to delete organization", org_id=org_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while deleting organization",
        )


@router.get(
    "/search/by-name/{name}",
    response_model=OrganizationResponse,
    summary="Get organization by name",
    description="Retrieve an organization by its exact name. This endpoint is useful for lookups by name.",
)
async def get_organization_by_name(name: str) -> OrganizationResponse:
    """
    Get organization by exact name match.

    - **name**: Exact organization name to search for
    """
    try:
        logger.debug("Retrieving organization by name", name=name)

        result = await organization_service.get_organization_by_name(name)

        if result is None:
            logger.warning("Organization not found by name", name=name)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Organization with name '{name}' not found",
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to retrieve organization by name", name=name, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while retrieving organization",
        )


@router.get(
    "/stats/summary",
    response_model=Dict[str, Any],
    summary="Get organization statistics",
    description="Get summary statistics about organizations in the system.",
)
async def get_organization_stats() -> Dict[str, Any]:
    """
    Get organization statistics and summary information.

    Returns counts by plan type, active/inactive status, and other metrics.
    """
    try:
        logger.debug("Retrieving organization statistics")

        # Get all organizations to calculate stats
        all_orgs = await organization_service.list_organizations(
            PaginationParams(page=1, per_page=1000),
            OrganizationFilters(is_active=None),  # Include inactive
        )

        # Calculate statistics
        total_count = all_orgs.total
        active_count = sum(1 for org in all_orgs.organizations if org.is_active)
        inactive_count = total_count - active_count

        # Count by plan type
        plan_counts = {
            "free": sum(
                1
                for org in all_orgs.organizations
                if org.plan_type == PlanType.FREE and org.is_active
            ),
            "starter": sum(
                1
                for org in all_orgs.organizations
                if org.plan_type == PlanType.STARTER and org.is_active
            ),
            "pro": sum(
                1
                for org in all_orgs.organizations
                if org.plan_type == PlanType.PRO and org.is_active
            ),
        }

        # Count organizations with domains
        with_domain_count = sum(
            1 for org in all_orgs.organizations if org.domain and org.is_active
        )

        stats = {
            "total_organizations": total_count,
            "active_organizations": active_count,
            "inactive_organizations": inactive_count,
            "organizations_with_domain": with_domain_count,
            "plan_distribution": plan_counts,
            "premium_organizations": plan_counts["starter"] + plan_counts["pro"],
        }

        logger.debug("Organization statistics retrieved", stats=stats)

        return stats

    except Exception as e:
        logger.error("Failed to retrieve organization statistics", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while retrieving statistics",
        )
