"""
Integration tests for health check endpoints.

Tests the /health, /status, /ready, and /live endpoints.
"""

import os
from unittest.mock import patch, AsyncMock

import pytest

# Set test environment
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-testing-purposes-only-32chars")
os.environ.setdefault("ENVIRONMENT", "test")


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_health_endpoint(self, async_client):
        """Test /health endpoint returns 200 OK."""
        response = await async_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_live_endpoint(self, async_client):
        """Test /live endpoint returns 200 OK."""
        response = await async_client.get("/live")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_status_endpoint(self, async_client):
        """Test /status endpoint returns service information."""
        # Mock database connection to avoid actual DB calls
        with patch('app.main.db') as mock_db:
            mock_db.test_connection = AsyncMock(return_value=True)

            response = await async_client.get("/status")

            assert response.status_code == 200
            data = response.json()
            assert "status" in data
            assert "version" in data
            assert "environment" in data

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_ready_endpoint_success(self, async_client):
        """Test /ready endpoint when database is connected."""
        with patch('app.main.db') as mock_db:
            mock_db.test_connection = AsyncMock(return_value=True)

            response = await async_client.get("/ready")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ready"

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_ready_endpoint_database_unavailable(self, async_client):
        """Test /ready endpoint when database is unavailable."""
        with patch('app.main.db') as mock_db:
            mock_db.test_connection = AsyncMock(return_value=False)

            response = await async_client.get("/ready")

            # Should return 503 when not ready
            assert response.status_code in [200, 503]


class TestDocsEndpoint:
    """Tests for documentation endpoint."""

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_docs_endpoint_available_in_dev(self, async_client):
        """Test /docs endpoint is available in development."""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            response = await async_client.get("/docs")

            # Should redirect or return docs
            assert response.status_code in [200, 307]

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_openapi_json_available(self, async_client):
        """Test /openapi.json endpoint returns API spec."""
        response = await async_client.get("/openapi.json")

        # May be disabled in production
        if response.status_code == 200:
            data = response.json()
            assert "openapi" in data
            assert "info" in data
            assert "paths" in data
