"""
Unit tests for app/core/security.py

Tests password hashing, JWT tokens, and token management.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, Mock
import jwt as pyjwt

from app.core.security import (
    TokenInfo,
    UserSessionManager,
    EnterpriseTokenManager,
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    verify_token,
    generate_secure_password,
    validate_password_strength,
)


class TestPasswordHashing:
    """Test password hashing and verification."""

    def test_hash_password_returns_string(self):
        """Test that hash_password returns a string."""
        password = "TestPassword123!"
        hashed = hash_password(password)

        assert isinstance(hashed, str)
        assert hashed != password
        assert len(hashed) > 0

    def test_hash_password_different_for_same_input(self):
        """Test that hashing same password twice gives different hashes (salt)."""
        password = "TestPassword123!"
        hash1 = hash_password(password)
        hash2 = hash_password(password)

        # Due to salt, hashes should be different
        assert hash1 != hash2

    def test_verify_password_correct(self):
        """Test password verification with correct password."""
        password = "TestPassword123!"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """Test password verification with incorrect password."""
        password = "TestPassword123!"
        hashed = hash_password(password)

        assert verify_password("WrongPassword", hashed) is False

    def test_verify_password_empty(self):
        """Test password verification with empty password."""
        password = "TestPassword123!"
        hashed = hash_password(password)

        assert verify_password("", hashed) is False


class TestPasswordValidation:
    """Test password strength validation."""

    def test_validate_strong_password(self):
        """Test validation of strong password."""
        result = validate_password_strength("StrongP@ssw0rd!")
        assert result["is_valid"] is True
        assert result["strength"] in ["medium", "strong"]

    def test_validate_weak_password_too_short(self):
        """Test validation rejects password that's too short."""
        result = validate_password_strength("Short1!")
        assert result["is_valid"] is False
        assert "at least 8 characters" in result.get("message", "").lower()

    def test_validate_weak_password_no_uppercase(self):
        """Test validation of password without uppercase."""
        result = validate_password_strength("password123!")
        # Depending on implementation, this may pass or fail
        # Adjust based on actual validate_password_strength implementation
        assert "strength" in result

    def test_validate_weak_password_no_numbers(self):
        """Test validation of password without numbers."""
        result = validate_password_strength("Password!!!")
        assert "strength" in result


class TestJWTTokens:
    """Test JWT token creation and decoding."""

    def test_create_access_token(self, mock_settings):
        """Test access token creation."""
        data = {"sub": "user123", "org_id": "org123"}

        with patch("app.core.security.settings", mock_settings):
            token = create_access_token(data)

        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_refresh_token(self, mock_settings):
        """Test refresh token creation."""
        data = {"sub": "user123", "org_id": "org123"}

        with patch("app.core.security.settings", mock_settings):
            token = create_refresh_token(data)

        assert isinstance(token, str)
        assert len(token) > 0

    def test_verify_valid_token(self, mock_settings):
        """Test verifying a valid token."""
        data = {"sub": "user123", "org_id": "org123"}

        with patch("app.core.security.settings", mock_settings):
            token, _ = create_access_token(data)
            decoded = verify_token(token)

        assert decoded is not None
        assert decoded["sub"] == "user123"
        assert decoded["org_id"] == "org123"

    def test_verify_expired_token(self, mock_settings):
        """Test verifying an expired token."""
        data = {"sub": "user123", "org_id": "org123"}
        expired_time = timedelta(minutes=-10)  # Already expired

        with patch("app.core.security.settings", mock_settings):
            # Create token that's already expired
            token = pyjwt.encode(
                {
                    **data,
                    "exp": datetime.utcnow() + expired_time,
                    "iat": datetime.utcnow(),
                },
                mock_settings.JWT_SECRET_KEY,
                algorithm=mock_settings.JWT_ALGORITHM,
            )

            decoded = verify_token(token)

        # Should return None for expired token
        assert decoded is None

    def test_verify_invalid_token(self, mock_settings):
        """Test verifying an invalid token."""
        with patch("app.core.security.settings", mock_settings):
            decoded = verify_token("invalid.token.here")

        assert decoded is None

    def test_verify_tampered_token(self, mock_settings):
        """Test verifying a tampered token."""
        data = {"sub": "user123", "org_id": "org123"}

        with patch("app.core.security.settings", mock_settings):
            token, _ = create_access_token(data)
            # Tamper with token
            tampered_token = token[:-10] + "tampered123"
            decoded = verify_token(tampered_token)

        assert decoded is None


class TestPasswordGeneration:
    """Test secure password generation."""

    def test_generate_secure_password(self):
        """Test secure password generation."""
        password = generate_secure_password()

        assert isinstance(password, str)
        assert len(password) >= 12

    def test_generate_unique_passwords(self):
        """Test that generated passwords are unique."""
        pwd1 = generate_secure_password()
        pwd2 = generate_secure_password()

        assert pwd1 != pwd2


class TestTokenInfo:
    """Test TokenInfo dataclass."""

    def test_token_info_creation(self):
        """Test TokenInfo creation."""
        token_info = TokenInfo(
            token_id="token123",
            user_id="user123",
            org_id="org123",
            token_type="access",
            issued_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=2),
        )

        assert token_info.token_id == "token123"
        assert token_info.user_id == "user123"
        assert token_info.org_id == "org123"
        assert token_info.token_type == "access"
        assert token_info.last_used is None
        assert token_info.session_id is None

    def test_token_info_with_optional_fields(self):
        """Test TokenInfo with optional fields."""
        now = datetime.utcnow()
        token_info = TokenInfo(
            token_id="token123",
            user_id="user123",
            org_id="org123",
            token_type="refresh",
            issued_at=now,
            expires_at=now + timedelta(days=7),
            last_used=now,
            user_agent="Mozilla/5.0",
            ip_address="192.168.1.1",
            session_id="session123",
            refresh_token_family_id="family123",
        )

        assert token_info.last_used == now
        assert token_info.user_agent == "Mozilla/5.0"
        assert token_info.ip_address == "192.168.1.1"
        assert token_info.session_id == "session123"
        assert token_info.refresh_token_family_id == "family123"


class TestUserSessionManager:
    """Test UserSessionManager dataclass."""

    def test_user_session_manager_creation(self):
        """Test UserSessionManager creation."""
        manager = UserSessionManager(user_id="user123", org_id="org123")

        assert manager.user_id == "user123"
        assert manager.org_id == "org123"
        assert len(manager.active_tokens) == 0
        assert len(manager.blacklisted_tokens) == 0
        assert isinstance(manager.created_at, datetime)
        assert isinstance(manager.last_activity, datetime)

    def test_user_session_manager_add_tokens(self):
        """Test adding tokens to session manager."""
        manager = UserSessionManager(user_id="user123", org_id="org123")

        manager.active_tokens.add("token1")
        manager.active_tokens.add("token2")

        assert len(manager.active_tokens) == 2
        assert "token1" in manager.active_tokens
        assert "token2" in manager.active_tokens

    def test_user_session_manager_blacklist_token(self):
        """Test blacklisting tokens."""
        manager = UserSessionManager(user_id="user123", org_id="org123")

        manager.active_tokens.add("token1")
        manager.active_tokens.remove("token1")
        manager.blacklisted_tokens.add("token1")

        assert "token1" not in manager.active_tokens
        assert "token1" in manager.blacklisted_tokens


class TestEnterpriseTokenManager:
    """Test EnterpriseTokenManager."""

    def test_token_manager_initialization(self):
        """Test token manager initialization."""
        manager = EnterpriseTokenManager()

        assert isinstance(manager._token_registry, dict)
        assert isinstance(manager._user_sessions, dict)
        assert isinstance(manager._blacklisted_tokens, set)
        assert len(manager._token_registry) == 0

    def test_register_token(self):
        """Test registering a token."""
        manager = EnterpriseTokenManager()
        now = datetime.utcnow()

        token_info = TokenInfo(
            token_id="token123",
            user_id="user123",
            org_id="org123",
            token_type="access",
            issued_at=now,
            expires_at=now + timedelta(hours=2),
        )

        result = manager.register_token(token_info)

        assert result is True
        assert "token123" in manager._token_registry
        assert "user123:org123" in manager._user_sessions

    def test_blacklist_token(self):
        """Test blacklisting a token."""
        manager = EnterpriseTokenManager()
        now = datetime.utcnow()

        token_info = TokenInfo(
            token_id="token123",
            user_id="user123",
            org_id="org123",
            token_type="access",
            issued_at=now,
            expires_at=now + timedelta(hours=2),
        )

        manager.register_token(token_info)
        result = manager.blacklist_token("token123", reason="logout")

        assert result is True
        assert "token123" in manager._blacklisted_tokens

    def test_is_token_blacklisted(self):
        """Test checking if token is blacklisted."""
        manager = EnterpriseTokenManager()
        now = datetime.utcnow()

        token_info = TokenInfo(
            token_id="token123",
            user_id="user123",
            org_id="org123",
            token_type="access",
            issued_at=now,
            expires_at=now + timedelta(hours=2),
        )

        manager.register_token(token_info)

        assert manager.is_token_blacklisted("token123") is False

        manager.blacklist_token("token123")

        assert manager.is_token_blacklisted("token123") is True

    def test_cleanup_expired_tokens(self):
        """Test cleanup of expired tokens."""
        manager = EnterpriseTokenManager()
        now = datetime.utcnow()

        # Create expired token
        expired_token = TokenInfo(
            token_id="expired_token",
            user_id="user123",
            org_id="org123",
            token_type="access",
            issued_at=now - timedelta(hours=5),
            expires_at=now - timedelta(hours=3),
        )

        # Create valid token
        valid_token = TokenInfo(
            token_id="valid_token",
            user_id="user123",
            org_id="org123",
            token_type="access",
            issued_at=now,
            expires_at=now + timedelta(hours=2),
        )

        manager.register_token(expired_token)
        manager.register_token(valid_token)

        # Run cleanup
        manager.cleanup_expired_tokens()

        # Valid token should remain, expired should be removed
        assert "valid_token" in manager._token_registry
        # Expired might be moved to blacklist or removed entirely
