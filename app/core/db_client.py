"""
PostgreSQL async connection management using SQLAlchemy 2.0.

Supports both:
- Google Cloud SQL Python Connector (for production)
- Direct connection URL (for local development)

Note: Uses per-event-loop connector management to handle multi-threaded
async operations (e.g., background tasks from ThreadPoolExecutor).
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, Optional, Tuple

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.pool import AsyncAdaptedQueuePool

from app.core.config import settings

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Manages async PostgreSQL connections with Cloud SQL connector support.

    Implements singleton pattern with per-event-loop resource management.
    This allows the same DatabaseManager instance to work across multiple
    event loops (e.g., main loop + background thread pools).
    """

    _instance: Optional["DatabaseManager"] = None
    _initialized: bool = False
    _shutdown: bool = False

    # Per-loop resources: maps loop_id -> resource
    _connectors: Dict[int, Any] = {}
    _engines: Dict[int, AsyncEngine] = {}
    _session_factories: Dict[int, async_sessionmaker] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

    def _get_loop_id(self) -> int:
        """Get current event loop ID for per-loop resource tracking."""
        try:
            loop = asyncio.get_running_loop()
            return id(loop)
        except RuntimeError:
            return 0

    async def _async_setup_engine_for_loop(self, loop_id: int):
        """Initialize engine and session factory for the current event loop."""
        if self._shutdown:
            logger.debug(
                f"Skipping engine setup for loop {loop_id} - shutdown in progress"
            )
            return

        if loop_id in self._engines:
            return

        using_cloud_sql = False
        if settings.USE_CLOUD_SQL_CONNECTOR and settings.CLOUD_SQL_INSTANCE:
            engine, connector = await self._create_cloud_sql_engine_async()
            self._connectors[loop_id] = connector
            using_cloud_sql = connector is not None
        else:
            engine = self._create_direct_engine()

        self._engines[loop_id] = engine
        self._session_factories[loop_id] = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

        connection_type = "cloud_sql" if using_cloud_sql else "direct"
        logger.info(
            f"Database engine initialized for loop {loop_id}: "
            f"pool_size={settings.DB_POOL_SIZE}, connection={connection_type}"
        )

    async def _create_cloud_sql_engine_async(self) -> Tuple[AsyncEngine, Any]:
        """Create engine and connector for Cloud SQL."""
        CLOUD_SQL_CONNECT_TIMEOUT = 30.0

        try:
            from google.cloud.sql.connector import Connector, IPTypes

            ip_type = (
                IPTypes.PUBLIC
                if settings.CLOUD_SQL_IP_TYPE == "PUBLIC"
                else IPTypes.PRIVATE
            )

            logger.info(
                f"Attempting Cloud SQL connection: "
                f"instance={settings.CLOUD_SQL_INSTANCE}, "
                f"ip_type={settings.CLOUD_SQL_IP_TYPE}, "
                f"user={settings.DATABASE_USER}, "
                f"database={settings.DATABASE_NAME}"
            )

            loop = asyncio.get_running_loop()
            connector = Connector(loop=loop)

            try:
                logger.debug(
                    f"Testing Cloud SQL connection (timeout={CLOUD_SQL_CONNECT_TIMEOUT}s)..."
                )
                test_conn = await asyncio.wait_for(
                    connector.connect_async(
                        settings.CLOUD_SQL_INSTANCE,
                        "asyncpg",
                        user=settings.DATABASE_USER,
                        password=settings.DATABASE_PASSWORD,
                        db=settings.DATABASE_NAME,
                        ip_type=ip_type,
                    ),
                    timeout=CLOUD_SQL_CONNECT_TIMEOUT,
                )
                await test_conn.close()
                logger.info("Cloud SQL Connector test connection successful")
            except asyncio.TimeoutError:
                logger.warning(
                    f"Cloud SQL Connector timed out after {CLOUD_SQL_CONNECT_TIMEOUT}s. "
                    f"Falling back to direct connection."
                )
                try:
                    connector.close()
                except Exception:
                    pass
                return self._create_direct_engine(), None
            except Exception as e:
                logger.warning(
                    f"Cloud SQL Connector failed ({type(e).__name__}: {e}). "
                    f"Falling back to direct connection."
                )
                try:
                    connector.close()
                except Exception:
                    pass
                return self._create_direct_engine(), None

            async def getconn():
                conn = await asyncio.wait_for(
                    connector.connect_async(
                        settings.CLOUD_SQL_INSTANCE,
                        "asyncpg",
                        user=settings.DATABASE_USER,
                        password=settings.DATABASE_PASSWORD,
                        db=settings.DATABASE_NAME,
                        ip_type=ip_type,
                    ),
                    timeout=CLOUD_SQL_CONNECT_TIMEOUT,
                )
                return conn

            engine = create_async_engine(
                "postgresql+asyncpg://",
                async_creator=getconn,
                poolclass=AsyncAdaptedQueuePool,
                pool_size=settings.DB_POOL_SIZE,
                max_overflow=settings.DB_MAX_OVERFLOW,
                pool_timeout=settings.DB_POOL_TIMEOUT,
                pool_recycle=settings.DB_POOL_RECYCLE,
                echo=settings.DB_ECHO,
            )

            return engine, connector

        except ImportError as e:
            logger.warning(
                f"Cloud SQL connector not available ({e}), falling back to direct connection"
            )
            return self._create_direct_engine(), None

    def _create_direct_engine(self) -> AsyncEngine:
        """Create engine with direct connection URL."""
        database_url = settings.DATABASE_URL
        if not database_url:
            database_url = (
                f"postgresql+asyncpg://{settings.DATABASE_USER}:{settings.DATABASE_PASSWORD}"
                f"@{settings.DATABASE_HOST}:{settings.DATABASE_PORT}/{settings.DATABASE_NAME}"
            )

        # Log connection info without password - NEVER log credentials
        logger.info(
            "Creating direct database connection",
            extra={
                "host": settings.DATABASE_HOST,
                "port": settings.DATABASE_PORT,
                "database": settings.DATABASE_NAME,
                "user": settings.DATABASE_USER,
            },
        )
        return create_async_engine(
            database_url,
            poolclass=AsyncAdaptedQueuePool,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            pool_timeout=settings.DB_POOL_TIMEOUT,
            pool_recycle=settings.DB_POOL_RECYCLE,
            echo=settings.DB_ECHO,
        )

    @property
    def engine(self) -> AsyncEngine:
        """Get the async engine for the current event loop."""
        loop_id = self._get_loop_id()
        if loop_id not in self._engines:
            raise RuntimeError(
                "Engine not initialized for this event loop. "
                "Use 'async with db.session()' or 'await db.get_engine_async()' first."
            )
        return self._engines[loop_id]

    async def get_engine_async(self) -> Optional[AsyncEngine]:
        """Get the async engine, initializing for the current event loop if necessary."""
        loop_id = self._get_loop_id()
        if loop_id not in self._engines:
            await self._async_setup_engine_for_loop(loop_id)
        return self._engines.get(loop_id)

    async def test_connection(self, timeout: float = 15.0) -> bool:
        """Test database connectivity with timeout."""
        from sqlalchemy import text

        engine = await self.get_engine_async()
        if not engine:
            logger.warning("No database engine available")
            return False

        try:
            async with asyncio.timeout(timeout):
                async with engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
            logger.info("Database connection test successful")
            return True
        except asyncio.TimeoutError:
            logger.error(f"Database connection test timed out after {timeout}s")
            return False
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get an async session with automatic commit/rollback.

        Usage:
            async with db.session() as session:
                result = await session.execute(...)
        """
        loop_id = self._get_loop_id()
        if loop_id not in self._session_factories:
            await self._async_setup_engine_for_loop(loop_id)

        if loop_id not in self._session_factories:
            raise RuntimeError("Failed to initialize database session factory")

        session = self._session_factories[loop_id]()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def create_tables(self):
        """Create all tables (for development/testing)."""
        from biz2bricks_core import Base

        engine = await self.get_engine_async()
        if engine:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables created")

    async def drop_tables(self):
        """Drop all tables (for testing only)."""
        from biz2bricks_core import Base

        engine = await self.get_engine_async()
        if engine:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            logger.info("Database tables dropped")

    async def close(self):
        """Close engines and connectors for the CURRENT event loop only."""
        loop_id = self._get_loop_id()

        if loop_id in self._connectors and self._connectors[loop_id]:
            try:
                connector = self._connectors[loop_id]
                if hasattr(connector, "close_async"):
                    await connector.close_async()
                else:
                    connector.close()
            except Exception as e:
                logger.debug(f"Error closing connector for loop {loop_id}: {e}")
            finally:
                del self._connectors[loop_id]

        if loop_id in self._engines:
            try:
                await self._engines[loop_id].dispose()
            except Exception as e:
                logger.debug(f"Error disposing engine for loop {loop_id}: {e}")
            finally:
                del self._engines[loop_id]

        if loop_id in self._session_factories:
            del self._session_factories[loop_id]

        logger.info("Database connections closed for current loop")

    async def close_all(self):
        """Close ALL engines and connectors across ALL event loops."""
        self._shutdown = True

        for loop_id, connector in list(self._connectors.items()):
            if connector:
                try:
                    connector.close()
                except Exception as e:
                    logger.debug(f"Error closing connector for loop {loop_id}: {e}")
        self._connectors.clear()

        current_loop_id = self._get_loop_id()
        if current_loop_id in self._engines:
            try:
                await self._engines[current_loop_id].dispose()
            except Exception as e:
                logger.debug(f"Error disposing engine: {e}")

        self._engines.clear()
        self._session_factories.clear()

        logger.info("All database connections closed")


# Global database manager instance
db = DatabaseManager()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency injection helper for FastAPI."""
    async with db.session() as session:
        yield session
