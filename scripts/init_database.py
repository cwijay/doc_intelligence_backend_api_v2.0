#!/usr/bin/env python3
"""
Initialize PostgreSQL database tables.

This script creates all required tables for the Document Intelligence API.
It can be run standalone or as part of the deployment process.

Usage:
    # Using uv
    uv run python scripts/init_database.py

    # Direct execution
    python scripts/init_database.py

    # With environment file
    ENV_FILE=.env.production python scripts/init_database.py

Environment Variables:
    DATABASE_URL - Direct PostgreSQL connection string (for local dev)
    USE_CLOUD_SQL_CONNECTOR - Set to 'true' for Cloud SQL connector
    CLOUD_SQL_INSTANCE - Cloud SQL instance connection name
    DATABASE_NAME, DATABASE_USER, DATABASE_PASSWORD - Cloud SQL credentials
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Configure logging for CLI output
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
from dotenv import load_dotenv

env_file = os.environ.get("ENV_FILE", ".env")
env_path = project_root / env_file
if env_path.exists():
    load_dotenv(env_path)
    logger.info(f"Loaded environment from: {env_path}")
else:
    logger.warning(f"No environment file found at: {env_path}")
    logger.info("Using system environment variables")


async def init_tables():
    """Create all database tables."""
    from biz2bricks_core import db, Base

    logger.info("=== PostgreSQL Database Initialization ===")

    # Test connection first
    logger.info("Testing database connection...")
    if not await db.test_connection():
        logger.error("Could not connect to database")
        logger.error("Please check your database configuration:")
        logger.error("  - DATABASE_URL for direct connections")
        logger.error("  - CLOUD_SQL_INSTANCE, DATABASE_NAME, DATABASE_USER, DATABASE_PASSWORD for Cloud SQL")
        sys.exit(1)

    logger.info("Database connection successful!")

    # Create tables
    logger.info("Creating tables...")
    try:
        await db.create_tables()
        logger.info("Tables created successfully!")
    except Exception as e:
        logger.error(f"Failed to create tables: {e}")
        sys.exit(1)

    # List created tables
    logger.info("Verifying tables...")
    engine = await db.get_engine_async()
    async with engine.connect() as conn:
        from sqlalchemy import text
        result = await conn.execute(text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """))
        tables = result.fetchall()

        if tables:
            logger.info("Created tables:")
            for (table_name,) in tables:
                logger.info(f"  - {table_name}")
        else:
            logger.warning("No tables found in public schema")

    # Close connections
    await db.close_all()
    logger.info("=== Initialization Complete ===")


async def drop_tables():
    """Drop all tables (use with caution!)."""
    from biz2bricks_core import db, Base

    logger.warning("=== WARNING: Dropping All Tables ===")

    confirm = input("Are you sure you want to drop all tables? (type 'yes' to confirm): ")
    if confirm.lower() != "yes":
        logger.info("Aborted.")
        return

    engine = await db.get_engine_async()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    logger.info("All tables dropped.")
    await db.close_all()


async def show_status():
    """Show database status and table information."""
    from biz2bricks_core import db

    logger.info("=== Database Status ===")

    if not await db.test_connection():
        logger.error("Could not connect to database")
        sys.exit(1)

    engine = await db.get_engine_async()
    async with engine.connect() as conn:
        from sqlalchemy import text

        # Get database version
        result = await conn.execute(text("SELECT version()"))
        version = result.scalar()
        logger.info(f"PostgreSQL Version: {version}")

        # Get tables with row counts
        result = await conn.execute(text("""
            SELECT
                t.table_name,
                (SELECT COUNT(*) FROM information_schema.columns c
                 WHERE c.table_name = t.table_name AND c.table_schema = 'public') as column_count
            FROM information_schema.tables t
            WHERE t.table_schema = 'public'
            ORDER BY t.table_name
        """))
        tables = result.fetchall()

        if tables:
            logger.info("Tables in database:")
            for table_name, col_count in tables:
                # Get row count for each table
                try:
                    count_result = await conn.execute(
                        text(f'SELECT COUNT(*) FROM "{table_name}"')
                    )
                    row_count = count_result.scalar()
                    logger.info(f"  - {table_name}: {col_count} columns, {row_count} rows")
                except Exception:
                    logger.info(f"  - {table_name}: {col_count} columns")
        else:
            logger.info("No tables found. Run 'init' to create tables.")

    await db.close_all()


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Initialize PostgreSQL database for Document Intelligence API"
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="init",
        choices=["init", "drop", "status"],
        help="Command to run (default: init)"
    )

    args = parser.parse_args()

    if args.command == "init":
        asyncio.run(init_tables())
    elif args.command == "drop":
        asyncio.run(drop_tables())
    elif args.command == "status":
        asyncio.run(show_status())


if __name__ == "__main__":
    main()
