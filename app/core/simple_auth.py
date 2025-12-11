"""
Simple MVP Authentication System

This provides basic session-based authentication for the MVP version.
Designed to be easily replaceable with enterprise JWT authentication later.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Any
from dataclasses import dataclass
from threading import Lock

from app.core.logging import get_logger
from app.core.config import settings

logger = get_logger(__name__)


@dataclass
class SimpleSession:
    """Simple session data structure for MVP authentication."""

    session_id: str
    user_id: str
    org_id: str
    email: str
    full_name: str
    username: str
    role: str
    created_at: datetime
    last_used: datetime
    expires_at: datetime
    refresh_token: Optional[str] = None
    refresh_expires_at: Optional[datetime] = None

    def is_expired(self) -> bool:
        """Check if session is expired."""
        return datetime.now(timezone.utc) > self.expires_at

    def is_refresh_expired(self) -> bool:
        """Check if refresh token is expired."""
        if not self.refresh_expires_at:
            return True
        return datetime.now(timezone.utc) > self.refresh_expires_at

    def is_in_grace_period(self, grace_minutes: int = 10) -> bool:
        """Check if session is in grace period before expiration."""
        if self.is_expired():
            return False
        grace_time = self.expires_at - timedelta(minutes=grace_minutes)
        return datetime.now(timezone.utc) >= grace_time

    def time_until_expiry(self) -> int:
        """Get seconds until session expiry."""
        if self.is_expired():
            return 0
        return int((self.expires_at - datetime.now(timezone.utc)).total_seconds())

    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary for API responses."""
        result = {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "org_id": self.org_id,
            "email": self.email,
            "full_name": self.full_name,
            "username": self.username,
            "role": self.role,
            "created_at": self.created_at.isoformat(),
            "last_used": self.last_used.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "time_until_expiry": self.time_until_expiry(),
        }
        if self.refresh_token:
            result["refresh_token"] = self.refresh_token
        if self.refresh_expires_at:
            result["refresh_expires_at"] = self.refresh_expires_at.isoformat()
        return result


class SimpleAuthManager:
    """
    Simple session-based authentication manager for MVP.

    This is designed to be easily replaceable with JWT or other
    enterprise authentication systems in the future.
    """

    def __init__(self):
        self._sessions: Dict[str, SimpleSession] = {}
        self._refresh_tokens: Dict[str, str] = {}  # refresh_token -> session_id mapping
        self._lock = Lock()
        # Import settings here to avoid circular imports

        self.session_duration_hours = settings.SESSION_DURATION_HOURS
        self.refresh_duration_days = settings.REFRESH_SESSION_DURATION_DAYS
        self.grace_period_minutes = settings.TOKEN_GRACE_PERIOD_MINUTES

    def create_session(
        self,
        user_id: str,
        org_id: str,
        email: str,
        full_name: str,
        username: str,
        role: str,
    ) -> SimpleSession:
        """
        Create a new user session with refresh token.

        Args:
            user_id: User identifier
            org_id: Organization identifier
            email: User email
            full_name: User's full name
            username: Username
            role: User role

        Returns:
            Created session object
        """
        with self._lock:
            session_id = str(uuid.uuid4())
            refresh_token = str(uuid.uuid4())
            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(hours=self.session_duration_hours)
            refresh_expires_at = now + timedelta(days=self.refresh_duration_days)

            session = SimpleSession(
                session_id=session_id,
                user_id=user_id,
                org_id=org_id,
                email=email,
                full_name=full_name,
                username=username,
                role=role,
                created_at=now,
                last_used=now,
                expires_at=expires_at,
                refresh_token=refresh_token,
                refresh_expires_at=refresh_expires_at,
            )

            self._sessions[session_id] = session
            self._refresh_tokens[refresh_token] = session_id

            logger.info(
                "Session created with refresh token",
                session_id=session_id[:8] + "...",
                user_id=user_id,
                org_id=org_id,
                email=email,
                expires_at=expires_at.isoformat(),
                refresh_expires_at=refresh_expires_at.isoformat(),
            )

            return session

    def get_session(self, session_id: str) -> Optional[SimpleSession]:
        """
        Get session by ID and update last used time.

        Args:
            session_id: Session identifier

        Returns:
            Session object if valid, None if not found or expired
        """
        with self._lock:
            if session_id not in self._sessions:
                return None

            session = self._sessions[session_id]

            # Check if expired
            if session.is_expired():
                del self._sessions[session_id]
                logger.info(
                    "Session expired and removed",
                    session_id=session_id[:8] + "...",
                    user_id=session.user_id,
                )
                return None

            # Update last used time
            session.last_used = datetime.now(timezone.utc)

            logger.debug(
                "Session accessed",
                session_id=session_id[:8] + "...",
                user_id=session.user_id,
                last_used=session.last_used.isoformat(),
            )

            return session

    def invalidate_session(self, session_id: str) -> bool:
        """
        Invalidate a session (logout).

        Args:
            session_id: Session identifier

        Returns:
            True if session was found and removed, False otherwise
        """
        with self._lock:
            if session_id in self._sessions:
                session = self._sessions[session_id]
                del self._sessions[session_id]

                # Also remove refresh token mapping
                if (
                    session.refresh_token
                    and session.refresh_token in self._refresh_tokens
                ):
                    del self._refresh_tokens[session.refresh_token]

                logger.info(
                    "Session invalidated",
                    session_id=session_id[:8] + "...",
                    user_id=session.user_id,
                    email=session.email,
                )

                return True
            return False

    def invalidate_user_sessions(self, user_id: str, org_id: str) -> int:
        """
        Invalidate all sessions for a specific user.

        Args:
            user_id: User identifier
            org_id: Organization identifier

        Returns:
            Number of sessions invalidated
        """
        with self._lock:
            sessions_to_remove = []

            for session_id, session in self._sessions.items():
                if session.user_id == user_id and session.org_id == org_id:
                    sessions_to_remove.append(session_id)

            for session_id in sessions_to_remove:
                del self._sessions[session_id]

            if sessions_to_remove:
                logger.info(
                    "User sessions invalidated",
                    user_id=user_id,
                    org_id=org_id,
                    count=len(sessions_to_remove),
                )

            return len(sessions_to_remove)

    def cleanup_expired_sessions(self) -> int:
        """
        Clean up expired sessions.

        Returns:
            Number of sessions cleaned up
        """
        with self._lock:
            now = datetime.now(timezone.utc)
            expired_sessions = []

            for session_id, session in self._sessions.items():
                if session.expires_at <= now:
                    expired_sessions.append(session_id)

            for session_id in expired_sessions:
                del self._sessions[session_id]

            if expired_sessions:
                logger.info("Expired sessions cleaned up", count=len(expired_sessions))

            return len(expired_sessions)

    def get_active_session_count(self) -> int:
        """Get count of active sessions."""
        with self._lock:
            return len(self._sessions)

    def get_user_session_count(self, user_id: str, org_id: str) -> int:
        """Get count of active sessions for a specific user."""
        with self._lock:
            count = 0
            for session in self._sessions.values():
                if session.user_id == user_id and session.org_id == org_id:
                    count += 1
            return count

    def refresh_session(self, refresh_token: str) -> Optional[SimpleSession]:
        """
        Refresh a session using refresh token.

        Args:
            refresh_token: Refresh token identifier

        Returns:
            New session object if refresh is successful, None otherwise
        """
        with self._lock:
            if refresh_token not in self._refresh_tokens:
                logger.warning(
                    "Refresh token not found", refresh_token=refresh_token[:8] + "..."
                )
                return None

            session_id = self._refresh_tokens[refresh_token]
            if session_id not in self._sessions:
                # Clean up orphaned refresh token
                del self._refresh_tokens[refresh_token]
                logger.warning(
                    "Session not found for refresh token",
                    refresh_token=refresh_token[:8] + "...",
                    session_id=session_id[:8] + "...",
                )
                return None

            old_session = self._sessions[session_id]

            # Check if refresh token is expired
            if old_session.is_refresh_expired():
                # Clean up expired refresh token and session
                del self._refresh_tokens[refresh_token]
                del self._sessions[session_id]
                logger.info(
                    "Refresh token expired and cleaned up",
                    refresh_token=refresh_token[:8] + "...",
                    user_id=old_session.user_id,
                )
                return None

            # Create new session with new tokens (token rotation)
            new_session_id = str(uuid.uuid4())
            new_refresh_token = str(uuid.uuid4())
            now = datetime.now(timezone.utc)
            new_expires_at = now + timedelta(hours=self.session_duration_hours)
            new_refresh_expires_at = now + timedelta(days=self.refresh_duration_days)

            new_session = SimpleSession(
                session_id=new_session_id,
                user_id=old_session.user_id,
                org_id=old_session.org_id,
                email=old_session.email,
                full_name=old_session.full_name,
                username=old_session.username,
                role=old_session.role,
                created_at=old_session.created_at,  # Keep original creation time
                last_used=now,
                expires_at=new_expires_at,
                refresh_token=new_refresh_token,
                refresh_expires_at=new_refresh_expires_at,
            )

            # Update mappings
            del self._sessions[session_id]
            del self._refresh_tokens[refresh_token]
            self._sessions[new_session_id] = new_session
            self._refresh_tokens[new_refresh_token] = new_session_id

            logger.info(
                "Session refreshed with token rotation",
                old_session_id=session_id[:8] + "...",
                new_session_id=new_session_id[:8] + "...",
                user_id=old_session.user_id,
                expires_at=new_expires_at.isoformat(),
            )

            return new_session

    def validate_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Validate session and return validation info.

        Args:
            session_id: Session identifier

        Returns:
            Validation info dict if valid, None if invalid
        """
        session = self.get_session(session_id)
        if not session:
            return None

        return {
            "valid": True,
            "expires_at": session.expires_at.isoformat(),
            "time_remaining": session.time_until_expiry(),
            "in_grace_period": session.is_in_grace_period(self.grace_period_minutes),
            "can_refresh": session.refresh_token is not None
            and not session.is_refresh_expired(),
        }


# Global simple auth manager instance
simple_auth_manager = SimpleAuthManager()


def create_user_session(
    user_id: str, org_id: str, email: str, full_name: str, username: str, role: str
) -> SimpleSession:
    """
    Create a new user session using the global auth manager.

    Args:
        user_id: User identifier
        org_id: Organization identifier
        email: User email
        full_name: User's full name
        username: Username
        role: User role

    Returns:
        Created session object
    """
    return simple_auth_manager.create_session(
        user_id=user_id,
        org_id=org_id,
        email=email,
        full_name=full_name,
        username=username,
        role=role,
    )


def get_user_session(session_id: str) -> Optional[SimpleSession]:
    """
    Get and validate a user session.

    Args:
        session_id: Session identifier

    Returns:
        Session object if valid, None otherwise
    """
    return simple_auth_manager.get_session(session_id)


def invalidate_user_session(session_id: str) -> bool:
    """
    Invalidate a user session.

    Args:
        session_id: Session identifier

    Returns:
        True if session was invalidated, False if not found
    """
    return simple_auth_manager.invalidate_session(session_id)


def invalidate_all_user_sessions(user_id: str, org_id: str) -> int:
    """
    Invalidate all sessions for a user.

    Args:
        user_id: User identifier
        org_id: Organization identifier

    Returns:
        Number of sessions invalidated
    """
    return simple_auth_manager.invalidate_user_sessions(user_id, org_id)


def refresh_user_session(refresh_token: str) -> Optional[SimpleSession]:
    """
    Refresh a user session using refresh token.

    Args:
        refresh_token: Refresh token identifier

    Returns:
        New session object if refresh is successful, None otherwise
    """
    return simple_auth_manager.refresh_session(refresh_token)


def validate_user_session(session_id: str) -> Optional[Dict[str, Any]]:
    """
    Validate a user session and return validation info.

    Args:
        session_id: Session identifier

    Returns:
        Validation info dict if valid, None if invalid
    """
    return simple_auth_manager.validate_session(session_id)


# FastAPI Dependencies for simple authentication
from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Security scheme for session tokens
session_security = HTTPBearer()


def get_current_user_simple(
    credentials: HTTPAuthorizationCredentials = Depends(session_security),
) -> SimpleSession:
    """
    FastAPI dependency to get current user from session token.

    This replaces the complex JWT-based authentication with simple session validation.

    Args:
        credentials: HTTPAuthorizationCredentials from HTTPBearer security scheme

    Returns:
        SimpleSession object containing user information

    Raises:
        TokenExpiredError: If session is expired
        TokenInvalidError: If session is invalid
    """
    from app.core.exceptions import TokenExpiredError, TokenInvalidError

    session_token = credentials.credentials

    # Check if session exists
    with simple_auth_manager._lock:
        if session_token not in simple_auth_manager._sessions:
            logger.warning("Session not found", token_prefix=session_token[:8] + "...")
            raise TokenInvalidError("Session token not found")

        session = simple_auth_manager._sessions[session_token]

        # Check if expired
        if session.is_expired():
            del simple_auth_manager._sessions[session_token]
            # Also remove refresh token mapping
            if (
                session.refresh_token
                and session.refresh_token in simple_auth_manager._refresh_tokens
            ):
                del simple_auth_manager._refresh_tokens[session.refresh_token]

            logger.info(
                "Session expired and removed",
                session_id=session_token[:8] + "...",
                user_id=session.user_id,
                expired_at=session.expires_at.isoformat(),
            )
            raise TokenExpiredError(
                "Session token has expired", expires_at=session.expires_at.isoformat()
            )

        # Update last used time
        session.last_used = datetime.now(timezone.utc)

    logger.debug(
        "User authenticated via session",
        user_id=session.user_id,
        org_id=session.org_id,
        session_id=session.session_id[:8] + "...",
    )

    return session


# For backwards compatibility with existing code that expects dict
def get_current_user_dict(
    credentials: HTTPAuthorizationCredentials = Depends(session_security),
) -> Dict[str, Any]:
    """
    FastAPI dependency that returns user info as dict for backwards compatibility.

    Returns user information in the same format as the old JWT system.
    """
    session = get_current_user_simple(credentials)

    return {
        "user_id": session.user_id,
        "org_id": session.org_id,
        "email": session.email,
        "full_name": session.full_name,
        "username": session.username,
        "role": session.role,
        "session_id": session.session_id,
        "created_at": session.created_at.isoformat(),
        "last_used": session.last_used.isoformat(),
        "expires_at": session.expires_at.isoformat(),
    }


def get_mock_user_dict() -> Dict[str, Any]:
    """
    TEMPORARY: Mock user for testing without authentication.

    ⚠️  WARNING: FOR TESTING ONLY - REMOVE BEFORE PRODUCTION!

    Returns fake user data to bypass authentication during development/testing.
    Uses existing organization ID from the system for compatibility.
    """
    return {
        "user_id": "test-user-123",
        "org_id": "GUbmPT49OSDO3eFDU2r5",  # Existing org from logs
        "email": "test@example.com",
        "full_name": "Test User",
        "username": "testuser",
        "role": "admin",
        "session_id": "mock-session",
        "created_at": "2025-09-17T19:00:00",
        "last_used": "2025-09-17T19:00:00",
        "expires_at": "2025-09-18T19:00:00",
    }
