"""
Unit tests for the /status handler's object-storage reporting.

Exercises app.api.health.detailed_status() directly rather than over HTTP:
the integration fixtures need a database driver that is not installed, and
the behaviour under test here is the handler's own assembly logic.
"""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.unit
class TestDetailedStatusGCS:
    @pytest.mark.asyncio
    async def test_status_includes_gcs_service(self):
        """/status must report object storage alongside postgres and cache."""
        from app.api import health

        with (
            patch.object(health.db, "test_connection", AsyncMock(return_value=True)),
            patch.object(
                health,
                "get_gcs_status",
                return_value={
                    "status": "connected",
                    "configured": True,
                    "bucket": "bucket-1",
                    "project_id": "proj-1",
                },
            ),
        ):
            result = await health.detailed_status()

        assert result["services"]["gcs"]["status"] == "connected"
        assert result["services"]["gcs"]["bucket"] == "bucket-1"

    @pytest.mark.asyncio
    async def test_unavailable_storage_degrades_overall_status(self):
        """A configured bucket that failed must not report the app healthy.

        Document upload and download are dead in this state, so reporting
        "healthy" is the exact blind spot this reporting exists to close.
        """
        from app.api import health

        with (
            patch.object(health.db, "test_connection", AsyncMock(return_value=True)),
            patch.object(
                health,
                "get_gcs_status",
                return_value={
                    "status": "unavailable",
                    "configured": True,
                    "bucket": "bucket-1",
                    "project_id": "proj-1",
                    "error": "Bucket 'bucket-1' not found",
                },
            ),
        ):
            result = await health.detailed_status()

        assert result["application"]["status"] == "degraded"

    @pytest.mark.asyncio
    async def test_disabled_storage_does_not_degrade_overall_status(self):
        """Storage switched off on purpose is a valid deployment, not a fault."""
        from app.api import health

        with (
            patch.object(health.db, "test_connection", AsyncMock(return_value=True)),
            patch.object(
                health,
                "get_gcs_status",
                return_value={
                    "status": "disabled",
                    "configured": False,
                    "bucket": None,
                    "project_id": None,
                },
            ),
        ):
            result = await health.detailed_status()

        assert result["application"]["status"] == "healthy"
