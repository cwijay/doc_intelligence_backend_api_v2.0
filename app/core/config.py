from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    # FastAPI Configuration
    PROJECT_NAME: str = "Document Intelligence API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"

    # Server Configuration
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # JWT Configuration - Enterprise Security Settings
    JWT_SECRET_KEY: str = Field(
        ...,
        description="Secret key for JWT tokens - must be cryptographically secure (min 32 chars)",
    )
    JWT_ALGORITHM: str = "HS256"

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def validate_jwt_secret_key(cls, v: str) -> str:
        """Validate JWT secret key has minimum length for security."""
        if len(v) < 32:
            raise ValueError(
                "JWT_SECRET_KEY must be at least 32 characters long for security. "
                'Generate a secure key with: python -c "import secrets; print(secrets.token_hex(32))"'
            )
        return v

    # Access Token Configuration
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=30,
        description="Access token expiration in minutes (recommended: 15-30 for production)",
    )

    # Refresh Token Configuration
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(
        default=30,
        description="Refresh token expiration in days (recommended: 7-30 for production)",
    )

    # Session Management Configuration
    MAX_CONCURRENT_SESSIONS: int = Field(
        default=5, description="Maximum concurrent sessions per user (0 = unlimited)"
    )

    # Token Security Settings
    INVALIDATE_TOKENS_ON_LOGIN: bool = Field(
        default=True, description="Invalidate all previous tokens when user logs in"
    )

    ENABLE_TOKEN_ROTATION: bool = Field(
        default=True, description="Enable refresh token rotation for enhanced security"
    )

    # Token Blacklist Cleanup
    TOKEN_BLACKLIST_CLEANUP_HOURS: int = Field(
        default=24, description="Hours between automatic blacklist cleanup runs"
    )

    # Session Configuration (Simple Auth)
    SESSION_DURATION_HOURS: int = Field(
        default=2,
        description="Session token duration in hours (recommended: 1-4 hours)",
    )

    REFRESH_SESSION_DURATION_DAYS: int = Field(
        default=7, description="Refresh token duration in days (recommended: 7-30 days)"
    )

    TOKEN_GRACE_PERIOD_MINUTES: int = Field(
        default=10, description="Grace period for token expiration in minutes"
    )

    # Security Monitoring
    ENABLE_AUTH_AUDIT_LOGGING: bool = Field(
        default=True, description="Enable detailed authentication audit logging"
    )

    AUTH_RATE_LIMIT_PER_MINUTE: int = Field(
        default=60, description="Maximum authentication attempts per minute per IP"
    )

    # PostgreSQL/Cloud SQL Configuration
    DATABASE_URL: Optional[str] = None  # Full connection URL (for local dev)
    DATABASE_NAME: str = "doc_intelligence"
    DATABASE_USER: str = "postgres"
    DATABASE_PASSWORD: str = ""
    DATABASE_HOST: str = "localhost"
    DATABASE_PORT: int = 5432
    CLOUD_SQL_INSTANCE: Optional[str] = None  # e.g., project:region:instance
    USE_CLOUD_SQL_CONNECTOR: bool = False
    CLOUD_SQL_IP_TYPE: str = "PRIVATE"  # PRIVATE or PUBLIC

    # Connection Pool Settings - increased for production workloads
    DB_POOL_SIZE: int = 10  # Base connections per event loop
    DB_MAX_OVERFLOW: int = 20  # Additional connections under load
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800  # 30 minutes
    DB_ECHO: bool = False  # SQL query logging

    # Google Cloud Platform Configuration
    GCP_PROJECT_ID: Optional[str] = None
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None  # Path to service account file
    GCS_BUCKET_NAME: str = "biz-to-bricks-document-store"
    DOCUMENT_STORE_BASE_PATH: str = ""  # Base path within bucket (empty for root)

    # Document Configuration
    MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50MB in bytes
    ALLOWED_FILE_TYPES: List[str] = ["pdf", "xlsx"]

    DOCUMENT_UPLOAD_TIMEOUT: int = 300  # 5 minutes in seconds
    SIGNED_URL_EXPIRATION_MINUTES: int = 60  # Default signed URL expiration

    @field_validator("ALLOWED_FILE_TYPES", mode="before")
    @classmethod
    def parse_allowed_file_types(cls, v):
        """Parse ALLOWED_FILE_TYPES from comma-separated string or JSON array."""
        if isinstance(v, str) and not v.startswith("["):
            return [x.strip() for x in v.split(",")]
        return v

    # CORS Settings - Environment-specific configuration
    # Next.js frontend runs on port 3000. Use ADDITIONAL_CORS_ORIGINS env var for other ports.
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    # Additional CORS Origins (JSON string from env var)
    ADDITIONAL_CORS_ORIGINS: Optional[str] = None

    # Production CORS Origins (comma-separated string or JSON array)
    PRODUCTION_CORS_ORIGINS: Optional[str] = None

    # Frontend domain (for automatic CORS origin detection)
    FRONTEND_DOMAIN: Optional[str] = None

    CORS_CREDENTIALS: bool = True
    CORS_METHODS: List[str] = ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"]
    CORS_HEADERS: List[str] = [
        "Authorization",
        "Content-Type",
        "X-Requested-With",
        "Accept",
        "Origin",
        "Cache-Control",
        "X-File-Name",
        "X-CSRF-Token",
        "Access-Control-Allow-Headers",
        "Access-Control-Allow-Origin",
        "User-Agent",
        "DNT",
        "Keep-Alive",
        "If-Modified-Since",
        "X-Mx-ReqToken",
    ]

    # Cloud Run specific settings
    CLOUD_RUN_SERVICE_URL: Optional[str] = None
    ENABLE_CORS_DEBUG: bool = False

    # Frontend-specific Cloud Run configuration
    FRONTEND_CLOUD_RUN_URL: Optional[str] = None
    FRONTEND_SERVICE_NAME: Optional[str] = None

    # Logging Configuration
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "text"  # json or text

    # Cache Configuration
    CACHE_ENABLED: bool = True
    CACHE_BACKEND: str = "memory"  # "memory" (default) or "redis"
    CACHE_DEFAULT_TTL: int = 300  # 5 minutes default

    # Redis Configuration (only used when CACHE_BACKEND=redis)
    REDIS_HOST: Optional[str] = None  # GCP Memorystore IP
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: Optional[str] = None
    REDIS_DB: int = 0

    # Cache TTL Settings (in seconds)
    CACHE_DOCUMENT_TTL: int = 120  # 2 minutes - documents change frequently
    CACHE_FOLDER_TTL: int = 300  # 5 minutes
    CACHE_ORG_TTL: int = 1800  # 30 minutes - orgs rarely change
    CACHE_USER_TTL: int = 300  # 5 minutes

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )

    @property
    def resolved_cors_origins(self) -> List[str]:
        """Get CORS origins based on environment and configuration."""
        import json
        import os

        # In production, do NOT start with localhost defaults for security
        if self.is_production:
            origins = []
        else:
            # In development, start with default origins
            origins = list(self.CORS_ORIGINS)

        # Add additional CORS origins from environment
        if self.ADDITIONAL_CORS_ORIGINS:
            try:
                # Try parsing as JSON array first
                if self.ADDITIONAL_CORS_ORIGINS.startswith("["):
                    additional_origins = json.loads(self.ADDITIONAL_CORS_ORIGINS)
                    origins.extend(additional_origins)
                else:
                    # Parse as comma-separated string
                    additional_origins = [
                        origin.strip()
                        for origin in self.ADDITIONAL_CORS_ORIGINS.split(",")
                    ]
                    origins.extend(additional_origins)
            except (json.JSONDecodeError, ValueError):
                # Fallback to single origin
                origins.append(self.ADDITIONAL_CORS_ORIGINS)

        # In production, use production-specific origins
        if self.is_production:
            # Parse production CORS origins from environment
            if self.PRODUCTION_CORS_ORIGINS:
                try:
                    # Try parsing as JSON array first
                    if self.PRODUCTION_CORS_ORIGINS.startswith("["):
                        prod_origins = json.loads(self.PRODUCTION_CORS_ORIGINS)
                    else:
                        # Parse as comma-separated or semicolon-separated string
                        if ";" in self.PRODUCTION_CORS_ORIGINS:
                            prod_origins = [
                                origin.strip()
                                for origin in self.PRODUCTION_CORS_ORIGINS.split(";")
                            ]
                        else:
                            prod_origins = [
                                origin.strip()
                                for origin in self.PRODUCTION_CORS_ORIGINS.split(",")
                            ]

                    origins.extend(prod_origins)
                except (json.JSONDecodeError, ValueError):
                    # Fallback to single origin
                    origins = [self.PRODUCTION_CORS_ORIGINS]

            # Add frontend domain variations if specified
            if self.FRONTEND_DOMAIN:
                domain = self.FRONTEND_DOMAIN.rstrip("/")
                origins.extend(
                    [
                        f"https://{domain}",
                        f"https://www.{domain}",
                        f"https://app.{domain}",
                    ]
                )

            # Add Cloud Run service URL if available
            if self.CLOUD_RUN_SERVICE_URL:
                origins.append(self.CLOUD_RUN_SERVICE_URL.rstrip("/"))

            # Add explicit frontend Cloud Run URL
            if self.FRONTEND_CLOUD_RUN_URL:
                origins.append(self.FRONTEND_CLOUD_RUN_URL.rstrip("/"))

            # Auto-detect backend Cloud Run URL from environment
            service_name = os.getenv("K_SERVICE")
            revision = os.getenv("K_REVISION")
            if service_name and revision:
                # Cloud Run URL pattern for backend
                region = os.getenv("GCP_REGION", "us-central1")
                if self.GCP_PROJECT_ID:
                    cloud_run_url = (
                        f"https://{service_name}-{revision[:8]}-{region}.a.run.app"
                    )
                    origins.append(cloud_run_url)

        # In development, include production frontend URL for testing if configured
        if self.is_development and self.FRONTEND_CLOUD_RUN_URL:
            origins.append(self.FRONTEND_CLOUD_RUN_URL.rstrip("/"))

        # Remove duplicates while preserving order
        seen = set()
        unique_origins = []
        for origin in origins:
            if origin and origin not in seen:
                seen.add(origin)
                unique_origins.append(origin)

        return unique_origins

    @property
    def is_development(self) -> bool:
        """Check if the application is running in development mode."""
        return self.ENVIRONMENT.lower() in ["development", "dev", "local"]

    @property
    def is_production(self) -> bool:
        """Check if the application is running in production mode."""
        return self.ENVIRONMENT.lower() in ["production", "prod"]

    @property
    def access_token_expire_minutes(self) -> int:
        """Get access token expiration in minutes with environment-specific defaults."""
        if self.is_production:
            # Production: shorter tokens for security
            return min(self.ACCESS_TOKEN_EXPIRE_MINUTES, 15)
        return self.ACCESS_TOKEN_EXPIRE_MINUTES

    @property
    def refresh_token_expire_days(self) -> int:
        """Get refresh token expiration in days with environment-specific defaults."""
        if self.is_production:
            # Production: shorter refresh tokens
            return min(self.REFRESH_TOKEN_EXPIRE_DAYS, 7)
        return self.REFRESH_TOKEN_EXPIRE_DAYS


# Global settings instance
settings = Settings()
