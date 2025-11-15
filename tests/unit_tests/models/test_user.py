"""
Unit tests for app/models/user.py

Tests User model functionality.
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

from app.models.user import User, UserRole


class TestUserModel:
    """Test User model creation and validation."""

    def test_user_creation_with_required_fields(self, mock_user_data):
        """Test creating user with all required fields."""
        user = User(**mock_user_data)

        assert user.id == "user123"
        assert user.org_id == "org123"
        assert user.email == "test@example.com"
        assert user.username == "testuser"
        assert user.full_name == "Test User"
        assert user.role == UserRole.USER
        assert user.is_active is True

    def test_user_creation_defaults(self):
        """Test user creation with default values."""
        user = User(
            org_id="org123",
            email="test@example.com",
            username="testuser",
            password_hash="hashed",
            full_name="Test User",
        )

        assert user.role == UserRole.USER
        assert user.is_active is True
        assert isinstance(user.created_at, datetime)
        assert isinstance(user.updated_at, datetime)
        assert user.last_login is None

    def test_user_role_enum(self):
        """Test UserRole enum values."""
        assert UserRole.ADMIN == "admin"
        assert UserRole.USER == "user"
        assert UserRole.VIEWER == "viewer"

    def test_user_to_dict(self, mock_user_data):
        """Test converting user to dictionary."""
        user = User(**mock_user_data)
        user_dict = user.to_dict()

        assert "id" not in user_dict  # ID excluded
        assert user_dict["org_id"] == "org123"
        assert user_dict["email"] == "test@example.com"
        assert user_dict["username"] == "testuser"
        assert isinstance(user_dict["created_at"], str)  # ISO format

    def test_user_from_dict(self, mock_user_data):
        """Test creating user from dictionary."""
        user = User.from_dict(mock_user_data, doc_id="user123")

        assert user.id == "user123"
        assert user.org_id == "org123"
        assert user.email == "test@example.com"

    def test_user_from_dict_with_datetime_strings(self):
        """Test creating user from dict with datetime strings."""
        data = {
            "org_id": "org123",
            "email": "test@example.com",
            "username": "testuser",
            "password_hash": "hashed",
            "full_name": "Test User",
            "role": "user",
            "is_active": True,
            "created_at": "2024-01-01T12:00:00",
            "updated_at": "2024-01-01T12:00:00",
            "last_login": "2024-01-01T13:00:00",
        }

        user = User.from_dict(data, doc_id="user123")

        assert isinstance(user.created_at, datetime)
        assert isinstance(user.updated_at, datetime)
        assert isinstance(user.last_login, datetime)


class TestUserProperties:
    """Test User model properties and methods."""

    def test_is_admin_property(self):
        """Test is_admin property."""
        admin_user = User(
            org_id="org123",
            email="admin@example.com",
            username="admin",
            password_hash="hashed",
            full_name="Admin User",
            role=UserRole.ADMIN,
        )

        assert admin_user.is_admin is True
        assert admin_user.is_user is False
        assert admin_user.is_viewer is False

    def test_is_user_property(self):
        """Test is_user property."""
        regular_user = User(
            org_id="org123",
            email="user@example.com",
            username="user",
            password_hash="hashed",
            full_name="Regular User",
            role=UserRole.USER,
        )

        assert regular_user.is_user is True
        assert regular_user.is_admin is False
        assert regular_user.is_viewer is False

    def test_is_viewer_property(self):
        """Test is_viewer property."""
        viewer_user = User(
            org_id="org123",
            email="viewer@example.com",
            username="viewer",
            password_hash="hashed",
            full_name="Viewer User",
            role=UserRole.VIEWER,
        )

        assert viewer_user.is_viewer is True
        assert viewer_user.is_admin is False
        assert viewer_user.is_user is False

    def test_can_modify_property(self):
        """Test can_modify property."""
        admin = User(
            org_id="org123",
            email="admin@example.com",
            username="admin",
            password_hash="hashed",
            full_name="Admin",
            role=UserRole.ADMIN,
        )
        user = User(
            org_id="org123",
            email="user@example.com",
            username="user",
            password_hash="hashed",
            full_name="User",
            role=UserRole.USER,
        )
        viewer = User(
            org_id="org123",
            email="viewer@example.com",
            username="viewer",
            password_hash="hashed",
            full_name="Viewer",
            role=UserRole.VIEWER,
        )

        assert admin.can_modify is True
        assert user.can_modify is True
        assert viewer.can_modify is False

    def test_can_admin_property(self):
        """Test can_admin property."""
        admin = User(
            org_id="org123",
            email="admin@example.com",
            username="admin",
            password_hash="hashed",
            full_name="Admin",
            role=UserRole.ADMIN,
        )
        user = User(
            org_id="org123",
            email="user@example.com",
            username="user",
            password_hash="hashed",
            full_name="User",
            role=UserRole.USER,
        )

        assert admin.can_admin is True
        assert user.can_admin is False

    def test_update_timestamp(self, mock_user_data):
        """Test updating timestamp."""
        user = User(**mock_user_data)
        original_updated_at = user.updated_at

        # Wait a moment and update
        import time
        time.sleep(0.01)
        user.update_timestamp()

        assert user.updated_at > original_updated_at

    def test_update_last_login(self, mock_user_data):
        """Test updating last login timestamp."""
        user = User(**mock_user_data)
        assert user.last_login is None

        user.update_last_login()

        assert user.last_login is not None
        assert isinstance(user.last_login, datetime)
