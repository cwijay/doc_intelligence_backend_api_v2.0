"""
Unit tests for the object-storage status reported by /status.

These cover app.core.gcs_client.get_gcs_status(), which exists so that a GCS
client sitting in disabled mode is visible to monitoring. Before it existed,
the only signal was a single log line at boot, and a failed upload was the
first indication that storage was broken.
"""

from typing import Optional

import pytest


class StubGCSClient:
    """Stands in for GCSClient, which cannot be constructed without network."""

    def __init__(self, initialized: bool, error: Optional[str] = None):
        self.is_initialized = initialized
        self.initialization_error = error


@pytest.mark.unit
class TestGetGCSStatus:
    def test_reports_unavailable_and_surfaces_error_when_init_failed(self, monkeypatch):
        """A configured bucket that failed to initialise must not look fine.

        This is the case that silently broke document upload and download:
        credentials were present, so the client tried to initialise, but the
        bucket probe failed and the client fell back to disabled mode.
        """
        from app.core import gcs_client as gcs_module

        monkeypatch.setattr(gcs_module.settings, "GCP_PROJECT_ID", "proj-1")
        monkeypatch.setattr(gcs_module.settings, "GCS_BUCKET_NAME", "bucket-1")

        result = gcs_module.get_gcs_status(
            client=StubGCSClient(False, "Bucket 'bucket-1' not found")
        )

        assert result["status"] == "unavailable"
        assert result["configured"] is True
        assert result["bucket"] == "bucket-1"
        assert result["error"] == "Bucket 'bucket-1' not found"

    def test_reports_connected_when_client_initialised(self, monkeypatch):
        """A working client reports connected and carries no error key."""
        from app.core import gcs_client as gcs_module

        monkeypatch.setattr(gcs_module.settings, "GCP_PROJECT_ID", "proj-1")
        monkeypatch.setattr(gcs_module.settings, "GCS_BUCKET_NAME", "bucket-1")

        result = gcs_module.get_gcs_status(client=StubGCSClient(True))

        assert result["status"] == "connected"
        assert result["configured"] is True
        assert "error" not in result

    def test_reports_disabled_when_not_configured(self, monkeypatch):
        """No project id means storage was never meant to run.

        The self-hosted stack ran this way on purpose before a credential
        existed, so an unconfigured client is not a failure and must be
        distinguishable from one that tried and failed.
        """
        from app.core import gcs_client as gcs_module

        monkeypatch.setattr(gcs_module.settings, "GCP_PROJECT_ID", "")
        monkeypatch.setattr(gcs_module.settings, "GCS_BUCKET_NAME", "bucket-1")

        result = gcs_module.get_gcs_status(client=StubGCSClient(False))

        assert result["status"] == "disabled"
        assert result["configured"] is False
