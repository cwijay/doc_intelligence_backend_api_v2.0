"""
Usage enforcement service for Document API.

Integrates with biz2bricks_core.UsageService for storage limit checking.
Provides helper functions for checking limits before upload and tracking storage changes.
"""

import logging
from typing import Optional

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

# Try to import biz2bricks_core, gracefully degrade if not available
try:
    from biz2bricks_core import usage_service, StorageLimitResult

    USAGE_TRACKING_ENABLED = True
except ImportError:
    logger.warning(
        "biz2bricks_core not available, usage tracking disabled. "
        "Install with: pip install biz2bricks-core"
    )
    usage_service = None
    StorageLimitResult = None
    USAGE_TRACKING_ENABLED = False


class StorageLimitExceededError(Exception):
    """Raised when storage limit would be exceeded."""

    def __init__(self, current_bytes: int, limit_bytes: int, tier: str):
        self.current_bytes = current_bytes
        self.limit_bytes = limit_bytes
        self.tier = tier
        super().__init__(
            f"Storage limit exceeded: {current_bytes}/{limit_bytes} bytes (tier: {tier})"
        )


async def check_storage_before_upload(org_id: str, file_size: int) -> Optional[dict]:
    """
    Check storage limit before allowing upload.

    Raises HTTPException with 402 Payment Required if limit exceeded.

    Args:
        org_id: Organization ID
        file_size: Size of file being uploaded in bytes

    Returns:
        Storage limit result dict if tracking enabled, None otherwise

    Raises:
        HTTPException: 402 if storage limit would be exceeded
    """
    if not USAGE_TRACKING_ENABLED or not usage_service:
        logger.debug("Usage tracking disabled, skipping storage check")
        return None

    try:
        result = await usage_service.check_storage_limit(org_id, file_size)

        if not result.allowed:
            current_mb = result.current_bytes / (1024 * 1024)
            limit_mb = result.limit_bytes / (1024 * 1024) if result.limit_bytes else 0
            file_mb = file_size / (1024 * 1024)

            logger.warning(
                f"Storage limit exceeded for org {org_id}: "
                f"current={current_mb:.1f}MB, limit={limit_mb:.1f}MB, "
                f"requested={file_mb:.1f}MB, tier={result.tier}"
            )

            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "error": "storage_limit_exceeded",
                    "message": (
                        f"Storage limit exceeded. "
                        f"Current: {current_mb:.1f}MB, Limit: {limit_mb:.1f}MB. "
                        f"Cannot upload {file_mb:.1f}MB file."
                    ),
                    "current_bytes": result.current_bytes,
                    "limit_bytes": result.limit_bytes,
                    "file_size_bytes": file_size,
                    "tier": result.tier,
                    "percentage_used": result.percentage_used,
                    "upgrade_hint": f"Upgrade from {result.tier} plan for more storage",
                },
            )

        # Log warning if approaching limit (>80%)
        if result.percentage_used >= 80:
            logger.info(
                f"Organization {org_id} approaching storage limit: "
                f"{result.percentage_used:.1f}% used"
            )

        return {
            "current_bytes": result.current_bytes,
            "limit_bytes": result.limit_bytes,
            "remaining_bytes": result.remaining_bytes,
            "percentage_used": result.percentage_used,
            "tier": result.tier,
        }

    except HTTPException:
        raise
    except Exception as e:
        # Log error but don't block upload on tracking failure
        logger.error(f"Error checking storage limit: {e}")
        return None


async def update_storage_after_upload(org_id: str, file_size: int) -> Optional[int]:
    """
    Update storage used after successful upload.

    This should be called after the document is successfully saved to the database.
    Uses fire-and-forget pattern - failures are logged but don't block the response.

    Args:
        org_id: Organization ID
        file_size: Size of uploaded file in bytes

    Returns:
        New storage usage in bytes if successful, None otherwise
    """
    if not USAGE_TRACKING_ENABLED or not usage_service:
        return None

    try:
        new_usage = await usage_service.update_storage_used(org_id, file_size)
        logger.debug(
            f"Updated storage for org {org_id}: +{file_size} bytes, "
            f"new total: {new_usage} bytes"
        )
        return new_usage
    except Exception as e:
        logger.error(f"Error updating storage after upload: {e}")
        return None


async def update_storage_after_delete(org_id: str, file_size: int) -> Optional[int]:
    """
    Update storage used after document deletion.

    This should be called when a document is deleted (hard delete) or
    permanently removed. Uses fire-and-forget pattern.

    Args:
        org_id: Organization ID
        file_size: Size of deleted file in bytes

    Returns:
        New storage usage in bytes if successful, None otherwise
    """
    if not USAGE_TRACKING_ENABLED or not usage_service:
        return None

    try:
        new_usage = await usage_service.update_storage_used(org_id, -file_size)
        logger.debug(
            f"Updated storage for org {org_id}: -{file_size} bytes, "
            f"new total: {new_usage} bytes"
        )
        return new_usage
    except Exception as e:
        logger.error(f"Error updating storage after delete: {e}")
        return None


async def get_storage_usage(org_id: str) -> Optional[dict]:
    """
    Get current storage usage for an organization.

    Args:
        org_id: Organization ID

    Returns:
        Storage usage summary dict, or None if tracking disabled
    """
    if not USAGE_TRACKING_ENABLED or not usage_service:
        return None

    try:
        return await usage_service.get_storage_usage_summary(org_id)
    except Exception as e:
        logger.error(f"Error getting storage usage: {e}")
        return None


async def recalculate_storage(org_id: str) -> Optional[int]:
    """
    Recalculate storage from documents table.

    This can be used for periodic reconciliation or manual repair.

    Args:
        org_id: Organization ID

    Returns:
        Recalculated storage usage in bytes, or None if failed
    """
    if not USAGE_TRACKING_ENABLED or not usage_service:
        return None

    try:
        return await usage_service.recalculate_storage(org_id)
    except Exception as e:
        logger.error(f"Error recalculating storage: {e}")
        return None
