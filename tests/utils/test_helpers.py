"""
Test Helper Functions

Common utility functions for API testing including authentication,
resource creation, and validation helpers.
"""

import io
import json
from typing import Dict, Optional, Tuple, Any
import httpx
import sys
from pathlib import Path

# Add tests directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from test_config import config, data_factory, TestCredentials


# ============================================================================
# Authentication Helpers
# ============================================================================

async def create_organization(
    client: httpx.AsyncClient,
    org_data: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Create a test organization.

    Args:
        client: HTTP client
        org_data: Optional organization data (will be generated if None)

    Returns:
        Dict with organization data including 'id'

    Raises:
        AssertionError: If organization creation fails
    """
    if org_data is None:
        org_data = data_factory.generate_org_data()

    response = await client.post(
        f"{config.api_prefix}/organizations/",  # Fixed: Added trailing slash
        json=org_data
    )
    assert response.status_code == 201, (
        f"Failed to create organization: {response.status_code} - {response.text}"
    )
    return response.json()


async def register_user(
    client: httpx.AsyncClient,
    org_id: str,
    user_data: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Register a new user in an organization.

    Args:
        client: HTTP client
        org_id: Organization ID
        user_data: Optional user data (will be generated if None)

    Returns:
        Dict with registration response

    Raises:
        AssertionError: If registration fails
    """
    if user_data is None:
        user_data = data_factory.generate_user_data()

    register_data = {
        **user_data,
        "organization_id": org_id
    }

    response = await client.post(
        f"{config.api_prefix}/auth/register",
        json=register_data
    )
    assert response.status_code in [200, 201], (
        f"Failed to register user: {response.status_code} - {response.text}"
    )
    return response.json()


async def login_user(
    client: httpx.AsyncClient,
    email: str,
    password: str
) -> TestCredentials:
    """
    Login user and return credentials with token.

    Args:
        client: HTTP client
        email: User email
        password: User password

    Returns:
        TestCredentials object with access token and user info

    Raises:
        AssertionError: If login fails
    """
    response = await client.post(
        f"{config.api_prefix}/auth/login",
        json={
            "email": email,
            "password": password
        }
    )
    assert response.status_code == 200, (
        f"Failed to login: {response.status_code} - {response.text}"
    )

    credentials = TestCredentials(email=email, password=password)
    credentials.update_from_login_response(response.json())
    return credentials


async def create_test_user_session(
    client: httpx.AsyncClient,
    org_id: Optional[str] = None,
    user_data: Optional[Dict] = None
) -> Tuple[str, TestCredentials]:
    """
    Create complete test session: org (if needed), user, and login.

    Args:
        client: HTTP client
        org_id: Optional organization ID (will create new org if None)
        user_data: Optional user data

    Returns:
        Tuple of (org_id, TestCredentials)

    Example:
        org_id, creds = await create_test_user_session(client)
        headers = creds.auth_headers
    """
    # Create organization if not provided
    if org_id is None:
        org = await create_organization(client)
        org_id = org["id"]

    # Generate user data if not provided
    if user_data is None:
        user_data = data_factory.generate_user_data()

    # Register user
    await register_user(client, org_id, user_data)

    # Login and get credentials
    credentials = await login_user(client, user_data["email"], user_data["password"])

    return org_id, credentials


async def refresh_session(
    client: httpx.AsyncClient,
    refresh_token: str
) -> Dict[str, Any]:
    """
    Refresh session using refresh token.

    Args:
        client: HTTP client
        refresh_token: Refresh token

    Returns:
        Dict with new access token and user info

    Raises:
        AssertionError: If refresh fails
    """
    response = await client.post(
        f"{config.api_prefix}/auth/refresh-session",
        json={"refresh_token": refresh_token}
    )
    assert response.status_code == 200, (
        f"Failed to refresh session: {response.status_code} - {response.text}"
    )
    return response.json()


async def logout_user(
    client: httpx.AsyncClient,
    access_token: str
) -> None:
    """
    Logout user.

    Args:
        client: HTTP client
        access_token: Access token

    Raises:
        AssertionError: If logout fails
    """
    response = await client.post(
        f"{config.api_prefix}/auth/logout",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200, (
        f"Failed to logout: {response.status_code} - {response.text}"
    )


# ============================================================================
# Document Helpers
# ============================================================================

async def upload_document(
    client: httpx.AsyncClient,
    credentials: TestCredentials,
    file_content: bytes,
    filename: str,
    content_type: str = "application/pdf",
    target_path: Optional[str] = None,
    metadata: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Upload a document.

    Args:
        client: HTTP client
        credentials: User credentials
        file_content: File content bytes
        filename: File name
        content_type: MIME type
        target_path: Optional target path in GCS
        metadata: Optional metadata dict

    Returns:
        Dict with uploaded document data

    Raises:
        AssertionError: If upload fails
    """
    files = {"file": (filename, io.BytesIO(file_content), content_type)}

    data = {}
    if target_path:
        data["target_path"] = target_path
    if metadata:
        data["metadata"] = json.dumps(metadata)

    response = await client.post(
        f"{config.api_prefix}/documents/upload",
        headers=credentials.auth_headers,
        files=files,
        data=data,
        timeout=config.upload_timeout
    )
    assert response.status_code in [200, 201], (
        f"Failed to upload document: {response.status_code} - {response.text}"
    )
    return response.json()


async def get_document(
    client: httpx.AsyncClient,
    credentials: TestCredentials,
    document_id: str
) -> Dict[str, Any]:
    """
    Get document by ID.

    Args:
        client: HTTP client
        credentials: User credentials
        document_id: Document ID

    Returns:
        Dict with document data

    Raises:
        AssertionError: If retrieval fails
    """
    response = await client.get(
        f"{config.api_prefix}/documents/{document_id}",
        headers=credentials.auth_headers
    )
    assert response.status_code == 200, (
        f"Failed to get document: {response.status_code} - {response.text}"
    )
    return response.json()


async def list_documents(
    client: httpx.AsyncClient,
    credentials: TestCredentials,
    page: int = 1,
    per_page: int = 10,
    **filters
) -> Dict[str, Any]:
    """
    List documents with pagination and filters.

    Args:
        client: HTTP client
        credentials: User credentials
        page: Page number
        per_page: Items per page
        **filters: Additional filter parameters (folder_path, file_type, status, etc.)

    Returns:
        Dict with documents list and pagination info

    Raises:
        AssertionError: If listing fails
    """
    params = {
        "page": page,
        "per_page": per_page,
        **filters
    }

    response = await client.get(
        f"{config.api_prefix}/documents/",
        headers=credentials.auth_headers,
        params=params
    )
    assert response.status_code == 200, (
        f"Failed to list documents: {response.status_code} - {response.text}"
    )
    return response.json()


async def delete_document(
    client: httpx.AsyncClient,
    credentials: TestCredentials,
    document_id: str
) -> None:
    """
    Delete document (soft delete).

    Args:
        client: HTTP client
        credentials: User credentials
        document_id: Document ID

    Raises:
        AssertionError: If deletion fails
    """
    response = await client.delete(
        f"{config.api_prefix}/documents/{document_id}",
        headers=credentials.auth_headers
    )
    assert response.status_code == 200, (
        f"Failed to delete document: {response.status_code} - {response.text}"
    )


# ============================================================================
# Folder Helpers
# ============================================================================

async def create_folder(
    client: httpx.AsyncClient,
    credentials: TestCredentials,
    org_id: str,
    folder_data: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Create a folder.

    Args:
        client: HTTP client
        credentials: User credentials
        org_id: Organization ID
        folder_data: Optional folder data (will be generated if None)

    Returns:
        Dict with created folder data

    Raises:
        AssertionError: If creation fails
    """
    if folder_data is None:
        folder_data = data_factory.generate_folder_data()

    response = await client.post(
        f"{config.api_prefix}/organizations/{org_id}/folders",
        headers=credentials.auth_headers,
        json=folder_data
    )
    assert response.status_code == 201, (
        f"Failed to create folder: {response.status_code} - {response.text}"
    )
    return response.json()


async def get_folder(
    client: httpx.AsyncClient,
    credentials: TestCredentials,
    org_id: str,
    folder_id: str
) -> Dict[str, Any]:
    """
    Get folder by ID.

    Args:
        client: HTTP client
        credentials: User credentials
        org_id: Organization ID
        folder_id: Folder ID

    Returns:
        Dict with folder data

    Raises:
        AssertionError: If retrieval fails
    """
    response = await client.get(
        f"{config.api_prefix}/organizations/{org_id}/folders/{folder_id}",
        headers=credentials.auth_headers
    )
    assert response.status_code == 200, (
        f"Failed to get folder: {response.status_code} - {response.text}"
    )
    return response.json()


async def delete_folder(
    client: httpx.AsyncClient,
    credentials: TestCredentials,
    org_id: str,
    folder_id: str
) -> None:
    """
    Delete folder (soft delete).

    Args:
        client: HTTP client
        credentials: User credentials
        org_id: Organization ID
        folder_id: Folder ID

    Raises:
        AssertionError: If deletion fails
    """
    response = await client.delete(
        f"{config.api_prefix}/organizations/{org_id}/folders/{folder_id}",
        headers=credentials.auth_headers
    )
    assert response.status_code == 200, (
        f"Failed to delete folder: {response.status_code} - {response.text}"
    )


# ============================================================================
# AI Content Helpers
# ============================================================================

async def generate_summary(
    client: httpx.AsyncClient,
    credentials: TestCredentials,
    filename: str,
    custom_prompt: Optional[str] = None,
    timeout: float = None
) -> Dict[str, Any]:
    """
    Generate document summary.

    Args:
        client: HTTP client
        credentials: User credentials
        filename: Document filename
        custom_prompt: Optional custom prompt
        timeout: Optional custom timeout

    Returns:
        Dict with summary data

    Raises:
        AssertionError: If generation fails
    """
    params = {"file_name": filename}
    json_data = {}
    if custom_prompt:
        json_data["prompt"] = custom_prompt

    response = await client.post(
        f"{config.api_prefix}/documents/summarize",
        headers=credentials.auth_headers,
        params=params,
        json=json_data if json_data else None,
        timeout=timeout or config.ai_operation_timeout
    )
    assert response.status_code == 200, (
        f"Failed to generate summary: {response.status_code} - {response.text}"
    )
    return response.json()


async def generate_questions(
    client: httpx.AsyncClient,
    credentials: TestCredentials,
    filename: str,
    question_count: int = 5,
    custom_prompt: Optional[str] = None,
    timeout: float = None
) -> Dict[str, Any]:
    """
    Generate document questions.

    Args:
        client: HTTP client
        credentials: User credentials
        filename: Document filename
        question_count: Number of questions to generate
        custom_prompt: Optional custom prompt
        timeout: Optional custom timeout

    Returns:
        Dict with questions data

    Raises:
        AssertionError: If generation fails
    """
    params = {"file_name": filename}
    json_data = {"question_count": question_count}
    if custom_prompt:
        json_data["prompt"] = custom_prompt

    response = await client.post(
        f"{config.api_prefix}/documents/questions",
        headers=credentials.auth_headers,
        params=params,
        json=json_data,
        timeout=timeout or config.ai_operation_timeout
    )
    assert response.status_code == 200, (
        f"Failed to generate questions: {response.status_code} - {response.text}"
    )
    return response.json()


async def generate_faq(
    client: httpx.AsyncClient,
    credentials: TestCredentials,
    filename: str,
    faq_count: int = 5,
    custom_prompt: Optional[str] = None,
    timeout: float = None
) -> Dict[str, Any]:
    """
    Generate document FAQ.

    Args:
        client: HTTP client
        credentials: User credentials
        filename: Document filename
        faq_count: Number of FAQ items to generate
        custom_prompt: Optional custom prompt
        timeout: Optional custom timeout

    Returns:
        Dict with FAQ data

    Raises:
        AssertionError: If generation fails
    """
    params = {"file_name": filename}
    json_data = {"faq_count": faq_count}
    if custom_prompt:
        json_data["prompt"] = custom_prompt

    response = await client.post(
        f"{config.api_prefix}/documents/faq",
        headers=credentials.auth_headers,
        params=params,
        json=json_data,
        timeout=timeout or config.ai_operation_timeout
    )
    assert response.status_code == 200, (
        f"Failed to generate FAQ: {response.status_code} - {response.text}"
    )
    return response.json()


# ============================================================================
# Assertion Helpers
# ============================================================================

def assert_response_schema(response_data: Dict, expected_keys: list) -> None:
    """
    Assert response contains expected keys.

    Args:
        response_data: Response JSON data
        expected_keys: List of expected keys

    Raises:
        AssertionError: If any expected key is missing
    """
    for key in expected_keys:
        assert key in response_data, f"Missing expected key: {key}"


def assert_pagination_schema(response_data: Dict) -> None:
    """
    Assert response contains pagination fields.

    Args:
        response_data: Response JSON data

    Raises:
        AssertionError: If pagination fields are missing
    """
    pagination_keys = ["items", "total", "page", "per_page", "total_pages"]
    assert_response_schema(response_data, pagination_keys)


def assert_error_response(response_data: Dict) -> None:
    """
    Assert response is an error response with detail.

    Args:
        response_data: Response JSON data

    Raises:
        AssertionError: If not a valid error response
    """
    assert "detail" in response_data, "Error response missing 'detail' field"
