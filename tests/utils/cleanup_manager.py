"""
Resource Cleanup Manager

Advanced cleanup utilities for managing test resources and ensuring
proper cleanup even in case of test failures.
"""

import asyncio
from typing import Dict, List, Optional
import httpx
import sys
from pathlib import Path

# Add tests directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from test_config import config


class CleanupManager:
    """
    Manages cleanup of test resources with retry and error handling.

    This is an enhanced version of the ResourceTracker from conftest.py
    with additional features like retry logic and dependency ordering.
    """

    def __init__(self):
        """Initialize cleanup manager with empty resource lists."""
        self.organizations: List[str] = []
        self.users: List[Dict[str, str]] = []
        self.documents: List[Dict[str, str]] = []
        self.folders: List[Dict[str, str]] = []
        self.sessions: List[str] = []  # Track session tokens for logout
        self._cleanup_errors: List[Dict] = []

    def track_organization(self, org_id: str) -> None:
        """Track organization for cleanup."""
        if org_id and org_id not in self.organizations:
            self.organizations.append(org_id)

    def track_user(self, org_id: str, user_id: str) -> None:
        """Track user for cleanup."""
        if org_id and user_id:
            self.users.append({"org_id": org_id, "user_id": user_id})

    def track_document(self, org_id: str, doc_id: str) -> None:
        """Track document for cleanup."""
        if org_id and doc_id:
            self.documents.append({"org_id": org_id, "doc_id": doc_id})

    def track_folder(self, org_id: str, folder_id: str) -> None:
        """Track folder for cleanup."""
        if org_id and folder_id:
            self.folders.append({"org_id": org_id, "folder_id": folder_id})

    def track_session(self, access_token: str) -> None:
        """Track session for logout."""
        if access_token and access_token not in self.sessions:
            self.sessions.append(access_token)

    @property
    def has_cleanup_errors(self) -> bool:
        """Check if there were any cleanup errors."""
        return len(self._cleanup_errors) > 0

    @property
    def cleanup_errors(self) -> List[Dict]:
        """Get list of cleanup errors."""
        return self._cleanup_errors

    async def _cleanup_resource(
        self,
        client: httpx.AsyncClient,
        method: str,
        endpoint: str,
        headers: Optional[Dict] = None,
        retries: int = 3
    ) -> bool:
        """
        Cleanup a single resource with retry logic.

        Args:
            client: HTTP client
            method: HTTP method (DELETE, POST, etc.)
            endpoint: API endpoint
            headers: Optional headers
            retries: Number of retry attempts

        Returns:
            True if successful, False otherwise
        """
        for attempt in range(retries):
            try:
                response = await client.request(
                    method,
                    endpoint,
                    headers=headers,
                    timeout=10.0
                )
                if response.status_code in [200, 204, 404]:
                    return True
                elif response.status_code >= 500 and attempt < retries - 1:
                    # Retry on server errors
                    await asyncio.sleep(1 * (attempt + 1))
                    continue
                else:
                    self._cleanup_errors.append({
                        "endpoint": endpoint,
                        "status_code": response.status_code,
                        "error": response.text
                    })
                    return False
            except Exception as e:
                if attempt < retries - 1:
                    await asyncio.sleep(1 * (attempt + 1))
                    continue
                else:
                    self._cleanup_errors.append({
                        "endpoint": endpoint,
                        "error": str(e)
                    })
                    return False
        return False

    async def cleanup_sessions(
        self,
        client: httpx.AsyncClient
    ) -> None:
        """
        Cleanup all tracked sessions (logout).

        Args:
            client: HTTP client
        """
        for access_token in self.sessions:
            headers = {"Authorization": f"Bearer {access_token}"}
            await self._cleanup_resource(
                client,
                "POST",
                f"{config.api_prefix}/auth/logout",
                headers=headers
            )

    async def cleanup_documents(
        self,
        client: httpx.AsyncClient,
        headers: Optional[Dict] = None
    ) -> None:
        """
        Cleanup all tracked documents.

        Args:
            client: HTTP client
            headers: Optional auth headers
        """
        for doc in reversed(self.documents):
            await self._cleanup_resource(
                client,
                "DELETE",
                f"{config.api_prefix}/documents/{doc['doc_id']}",
                headers=headers
            )

    async def cleanup_folders(
        self,
        client: httpx.AsyncClient,
        headers: Optional[Dict] = None
    ) -> None:
        """
        Cleanup all tracked folders.

        Args:
            client: HTTP client
            headers: Optional auth headers
        """
        for folder in reversed(self.folders):
            await self._cleanup_resource(
                client,
                "DELETE",
                f"{config.api_prefix}/organizations/{folder['org_id']}/folders/{folder['folder_id']}",
                headers=headers
            )

    async def cleanup_users(
        self,
        client: httpx.AsyncClient,
        headers: Optional[Dict] = None
    ) -> None:
        """
        Cleanup all tracked users.

        Args:
            client: HTTP client
            headers: Optional auth headers
        """
        for user in reversed(self.users):
            await self._cleanup_resource(
                client,
                "DELETE",
                f"{config.api_prefix}/organizations/{user['org_id']}/users/{user['user_id']}",
                headers=headers
            )

    async def cleanup_organizations(
        self,
        client: httpx.AsyncClient,
        headers: Optional[Dict] = None
    ) -> None:
        """
        Cleanup all tracked organizations.

        Args:
            client: HTTP client
            headers: Optional auth headers
        """
        for org_id in reversed(self.organizations):
            await self._cleanup_resource(
                client,
                "DELETE",
                f"{config.api_prefix}/organizations/{org_id}",
                headers=headers
            )

    async def cleanup_all(
        self,
        client: httpx.AsyncClient,
        headers: Optional[Dict] = None
    ) -> None:
        """
        Cleanup all tracked resources in proper order.

        Order:
        1. Sessions (logout)
        2. Documents
        3. Folders
        4. Users
        5. Organizations

        Args:
            client: HTTP client
            headers: Optional auth headers
        """
        # Clear previous errors
        self._cleanup_errors = []

        # Cleanup in dependency order
        await self.cleanup_sessions(client)
        await self.cleanup_documents(client, headers)
        await self.cleanup_folders(client, headers)
        await self.cleanup_users(client, headers)
        await self.cleanup_organizations(client, headers)

    def print_cleanup_summary(self) -> None:
        """Print summary of cleanup operations."""
        print("\n" + "=" * 60)
        print("CLEANUP SUMMARY")
        print("=" * 60)
        print(f"Organizations cleaned: {len(self.organizations)}")
        print(f"Users cleaned: {len(self.users)}")
        print(f"Folders cleaned: {len(self.folders)}")
        print(f"Documents cleaned: {len(self.documents)}")
        print(f"Sessions cleaned: {len(self.sessions)}")
        print(f"Errors: {len(self._cleanup_errors)}")

        if self._cleanup_errors:
            print("\nCleanup Errors:")
            for error in self._cleanup_errors:
                print(f"  - {error}")
        print("=" * 60 + "\n")

    def reset(self) -> None:
        """Reset all tracked resources."""
        self.organizations = []
        self.users = []
        self.documents = []
        self.folders = []
        self.sessions = []
        self._cleanup_errors = []


# Convenience functions for common cleanup patterns

async def cleanup_test_org(
    client: httpx.AsyncClient,
    org_id: str,
    headers: Optional[Dict] = None
) -> bool:
    """
    Cleanup entire organization and all its resources.

    This is a convenience function that attempts to delete an organization.
    Note: The API should handle cascading deletes for child resources.

    Args:
        client: HTTP client
        org_id: Organization ID to cleanup
        headers: Optional auth headers

    Returns:
        True if successful
    """
    try:
        response = await client.delete(
            f"{config.api_prefix}/organizations/{org_id}",
            headers=headers,
            timeout=10.0
        )
        return response.status_code in [200, 204, 404]
    except Exception:
        return False


async def cleanup_test_document(
    client: httpx.AsyncClient,
    doc_id: str,
    headers: Dict
) -> bool:
    """
    Cleanup a single document.

    Args:
        client: HTTP client
        doc_id: Document ID
        headers: Auth headers

    Returns:
        True if successful
    """
    try:
        response = await client.delete(
            f"{config.api_prefix}/documents/{doc_id}",
            headers=headers,
            timeout=10.0
        )
        return response.status_code in [200, 204, 404]
    except Exception:
        return False


async def cleanup_test_folder(
    client: httpx.AsyncClient,
    org_id: str,
    folder_id: str,
    headers: Dict
) -> bool:
    """
    Cleanup a single folder.

    Args:
        client: HTTP client
        org_id: Organization ID
        folder_id: Folder ID
        headers: Auth headers

    Returns:
        True if successful
    """
    try:
        response = await client.delete(
            f"{config.api_prefix}/organizations/{org_id}/folders/{folder_id}",
            headers=headers,
            timeout=10.0
        )
        return response.status_code in [200, 204, 404]
    except Exception:
        return False
