#!/usr/bin/env python3
"""
Environment File Generator for Document Intelligence Backend.

This script generates .env files from provisioned GCP resources.

Usage:
    # Generate .env for local development
    uv run python scripts/generate_env.py

    # Generate .env.production for Cloud Run
    uv run python scripts/generate_env.py --env production

    # Specify output file
    uv run python scripts/generate_env.py --output .env.local

    # Include secrets from Secret Manager
    uv run python scripts/generate_env.py --include-secrets

Environment Variables:
    GCP_PROJECT_ID - Your GCP project ID

Requirements:
    - Google Cloud SDK (gcloud) installed and authenticated
    - Resources provisioned (Cloud SQL, GCS bucket, etc.)
"""

import os
import sys
import json
import subprocess
import logging
import argparse
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime
import urllib.parse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add project root to path for .env loading
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
from dotenv import load_dotenv
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(env_path)


def run_gcloud_command(args: list, capture_output: bool = True) -> Tuple[bool, str]:
    """Run a gcloud command and return success status and output."""
    cmd = ["gcloud"] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture_output,
            text=True,
            check=False
        )
        if result.returncode == 0:
            return True, result.stdout.strip() if capture_output else ""
        else:
            return False, result.stderr.strip() if capture_output else ""
    except FileNotFoundError:
        return False, "gcloud CLI not found. Please install Google Cloud SDK."
    except Exception as e:
        return False, str(e)


def get_project_id() -> Optional[str]:
    """Get GCP project ID from environment or gcloud config."""
    project_id = os.environ.get("GCP_PROJECT_ID")
    if project_id:
        return project_id

    success, output = run_gcloud_command(["config", "get-value", "project"])
    if success and output:
        return output

    return None


def get_cloud_sql_instances(project_id: str) -> List[Dict[str, Any]]:
    """Get Cloud SQL instances in the project."""
    success, output = run_gcloud_command([
        "sql", "instances", "list",
        "--project", project_id,
        "--format=json"
    ])
    if success:
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return []
    return []


def get_cloud_sql_instance_info(project_id: str, instance_name: str) -> Optional[Dict[str, Any]]:
    """Get Cloud SQL instance information."""
    success, output = run_gcloud_command([
        "sql", "instances", "describe", instance_name,
        "--project", project_id,
        "--format=json"
    ])
    if success:
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return None
    return None


def get_gcs_buckets(project_id: str) -> List[str]:
    """Get GCS buckets in the project."""
    success, output = run_gcloud_command([
        "storage", "buckets", "list",
        "--project", project_id,
        "--format=json"
    ])
    if success:
        try:
            buckets = json.loads(output)
            return [b.get("name", "").replace("gs://", "") for b in buckets]
        except json.JSONDecodeError:
            return []
    return []


def get_secret_value(project_id: str, secret_id: str) -> Optional[str]:
    """Get a secret value from Secret Manager."""
    success, output = run_gcloud_command([
        "secrets", "versions", "access", "latest",
        "--secret", secret_id,
        "--project", project_id
    ])
    if success:
        return output
    return None


def check_secret_exists(project_id: str, secret_id: str) -> bool:
    """Check if a secret exists in Secret Manager."""
    success, _ = run_gcloud_command([
        "secrets", "describe", secret_id,
        "--project", project_id
    ])
    return success


def generate_jwt_secret() -> str:
    """Generate a secure JWT secret."""
    import secrets
    import string
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(64))


def build_env_config(
    project_id: str,
    environment: str = "development",
    include_secrets: bool = False,
    cloud_sql_instance: Optional[str] = None,
    bucket_name: Optional[str] = None,
    database_name: str = "doc_intelligence",
    database_user: str = "postgres",
) -> Dict[str, str]:
    """Build environment configuration from GCP resources."""
    config = {}

    # Basic GCP config
    config["GCP_PROJECT_ID"] = project_id
    config["ENVIRONMENT"] = environment

    # Cloud SQL configuration
    instances = get_cloud_sql_instances(project_id)
    if instances:
        # Use provided instance or first found
        if cloud_sql_instance:
            instance = next((i for i in instances if i.get("name") == cloud_sql_instance), None)
        else:
            instance = instances[0]

        if instance:
            instance_name = instance.get("name", "")
            region = instance.get("region", "us-central1")
            connection_name = f"{project_id}:{region}:{instance_name}"

            # Get public IP
            ip_addresses = instance.get("ipAddresses", [])
            public_ip = next(
                (ip["ipAddress"] for ip in ip_addresses if ip.get("type") == "PRIMARY"),
                None
            )

            config["CLOUD_SQL_INSTANCE"] = connection_name
            config["DATABASE_NAME"] = database_name
            config["DATABASE_USER"] = database_user

            if environment == "production":
                config["USE_CLOUD_SQL_CONNECTOR"] = "true"
                config["CLOUD_SQL_IP_TYPE"] = "PRIVATE"
            else:
                config["USE_CLOUD_SQL_CONNECTOR"] = "false"
                config["CLOUD_SQL_IP_TYPE"] = "PUBLIC"
                if public_ip:
                    config["_CLOUD_SQL_PUBLIC_IP"] = public_ip

    # GCS bucket configuration
    buckets = get_gcs_buckets(project_id)
    if buckets:
        # Use provided bucket or find one with 'document' in name
        if bucket_name and bucket_name in buckets:
            config["GCS_BUCKET_NAME"] = bucket_name
        else:
            doc_bucket = next((b for b in buckets if "document" in b.lower()), None)
            if doc_bucket:
                config["GCS_BUCKET_NAME"] = doc_bucket
            elif buckets:
                config["GCS_BUCKET_NAME"] = buckets[0]

    # Secrets from Secret Manager
    if include_secrets:
        secrets_to_fetch = ["DATABASE_PASSWORD", "JWT_SECRET_KEY", "REFRESH_SECRET_KEY"]
        for secret_id in secrets_to_fetch:
            if check_secret_exists(project_id, secret_id):
                value = get_secret_value(project_id, secret_id)
                if value:
                    config[secret_id] = value
            else:
                # Generate placeholder or random value
                if "PASSWORD" in secret_id:
                    config[f"# {secret_id}"] = "# Not found in Secret Manager - set manually"
                else:
                    config[secret_id] = generate_jwt_secret()
    else:
        # Add placeholders for secrets
        config["# DATABASE_PASSWORD"] = "# Get from Secret Manager or set manually"
        config["# JWT_SECRET_KEY"] = "# Generate with: openssl rand -base64 64"
        config["# REFRESH_SECRET_KEY"] = "# Generate with: openssl rand -base64 64"

    # Connection pool settings
    config["DB_POOL_SIZE"] = "5" if environment == "development" else "10"
    config["DB_MAX_OVERFLOW"] = "10" if environment == "development" else "20"
    config["DB_POOL_TIMEOUT"] = "30"
    config["DB_POOL_RECYCLE"] = "1800"

    # Session settings
    config["SESSION_DURATION_HOURS"] = "24"
    config["REFRESH_SESSION_DURATION_DAYS"] = "7"
    config["MAX_CONCURRENT_SESSIONS"] = "5"

    # API settings
    config["API_V1_STR"] = "/api/v1"
    config["DEBUG"] = "true" if environment == "development" else "false"
    config["LOG_LEVEL"] = "DEBUG" if environment == "development" else "INFO"

    # CORS settings
    if environment == "development":
        config["CORS_ALLOWED_ORIGINS"] = "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000"
    else:
        config["CORS_ALLOWED_ORIGINS"] = "# Set your production frontend URL"

    # File upload settings
    config["MAX_FILE_SIZE"] = "52428800"  # 50MB
    config["ALLOWED_FILE_TYPES"] = '["pdf", "xlsx"]'
    config["SIGNED_URL_EXPIRATION_MINUTES"] = "60"

    return config


def format_env_file(config: Dict[str, str], environment: str) -> str:
    """Format configuration as .env file content."""
    lines = []

    # Header
    lines.append("# =============================================================================")
    lines.append(f"# Document Intelligence API - {environment.upper()} Environment")
    lines.append(f"# Generated by scripts/generate_env.py on {datetime.now().isoformat()}")
    lines.append("# =============================================================================")
    lines.append("")

    # Group configurations
    sections = {
        "GCP Configuration": ["GCP_PROJECT_ID", "ENVIRONMENT", "GOOGLE_APPLICATION_CREDENTIALS"],
        "Cloud SQL Configuration": [
            "CLOUD_SQL_INSTANCE", "DATABASE_NAME", "DATABASE_USER", "DATABASE_PASSWORD",
            "USE_CLOUD_SQL_CONNECTOR", "CLOUD_SQL_IP_TYPE", "DATABASE_URL",
            "_CLOUD_SQL_PUBLIC_IP"
        ],
        "Connection Pool": ["DB_POOL_SIZE", "DB_MAX_OVERFLOW", "DB_POOL_TIMEOUT", "DB_POOL_RECYCLE"],
        "Cloud Storage": ["GCS_BUCKET_NAME"],
        "Authentication": [
            "JWT_SECRET_KEY", "REFRESH_SECRET_KEY",
            "SESSION_DURATION_HOURS", "REFRESH_SESSION_DURATION_DAYS", "MAX_CONCURRENT_SESSIONS"
        ],
        "API Configuration": ["API_V1_STR", "DEBUG", "LOG_LEVEL", "CORS_ALLOWED_ORIGINS"],
        "File Upload": ["MAX_FILE_SIZE", "ALLOWED_FILE_TYPES", "SIGNED_URL_EXPIRATION_MINUTES"],
    }

    for section, keys in sections.items():
        section_items = []
        for key in keys:
            if key in config:
                section_items.append((key, config[key]))
            # Check for comment keys
            comment_key = f"# {key}"
            if comment_key in config:
                section_items.append((comment_key, config[comment_key]))

        if section_items:
            lines.append(f"# {section}")
            lines.append("# " + "-" * (len(section) + 2))
            for key, value in section_items:
                if key.startswith("#"):
                    lines.append(f"{key}={value}")
                elif key.startswith("_"):
                    # Internal/helper values as comments
                    lines.append(f"# {key[1:]}={value}")
                else:
                    lines.append(f"{key}={value}")
            lines.append("")

    # Add DATABASE_URL for local development if we have the info
    if "_CLOUD_SQL_PUBLIC_IP" in config and "DATABASE_USER" in config and "DATABASE_NAME" in config:
        ip = config["_CLOUD_SQL_PUBLIC_IP"]
        user = config["DATABASE_USER"]
        db = config["DATABASE_NAME"]
        lines.append("# Direct PostgreSQL connection URL (for local development)")
        lines.append("# Uncomment and set DATABASE_PASSWORD to use")
        lines.append(f"# DATABASE_URL=postgresql+asyncpg://{user}:YOUR_PASSWORD@{ip}:5432/{db}")
        lines.append("")

    return "\n".join(lines)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate environment file from provisioned GCP resources"
    )
    parser.add_argument(
        "--env", "-e",
        default="development",
        choices=["development", "staging", "production"],
        help="Target environment (default: development)"
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file path (default: .env or .env.<env>)"
    )
    parser.add_argument(
        "--project",
        help="GCP Project ID (overrides environment)"
    )
    parser.add_argument(
        "--instance",
        help="Cloud SQL instance name"
    )
    parser.add_argument(
        "--bucket",
        help="GCS bucket name"
    )
    parser.add_argument(
        "--database",
        default="doc_intelligence",
        help="Database name (default: doc_intelligence)"
    )
    parser.add_argument(
        "--user",
        default="postgres",
        help="Database user (default: postgres)"
    )
    parser.add_argument(
        "--include-secrets",
        action="store_true",
        help="Include secrets from Secret Manager"
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print to stdout instead of file"
    )

    args = parser.parse_args()

    # Get project ID
    project_id = args.project or get_project_id()
    if not project_id:
        logger.error("GCP_PROJECT_ID not set and couldn't detect from gcloud")
        sys.exit(1)

    logger.info(f"Using project: {project_id}")
    logger.info(f"Environment: {args.env}")

    # Build configuration
    logger.info("Querying GCP resources...")
    config = build_env_config(
        project_id=project_id,
        environment=args.env,
        include_secrets=args.include_secrets,
        cloud_sql_instance=args.instance,
        bucket_name=args.bucket,
        database_name=args.database,
        database_user=args.user,
    )

    # Format output
    content = format_env_file(config, args.env)

    if args.stdout:
        print(content)
    else:
        # Determine output path
        if args.output:
            output_path = Path(args.output)
        elif args.env == "development":
            output_path = project_root / ".env"
        else:
            output_path = project_root / f".env.{args.env}"

        # Check if file exists
        if output_path.exists():
            backup_path = output_path.with_suffix(f".backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}")
            logger.info(f"Backing up existing file to: {backup_path}")
            output_path.rename(backup_path)

        # Write file
        output_path.write_text(content)
        logger.info(f"Environment file written to: {output_path}")

        # Display summary
        logger.info("")
        logger.info("=" * 60)
        logger.info("Environment File Generated")
        logger.info("=" * 60)
        logger.info(f"File: {output_path}")
        logger.info(f"Environment: {args.env}")
        logger.info("")
        logger.info("Next Steps:")
        logger.info("1. Review and update the generated file")
        if not args.include_secrets:
            logger.info("2. Set DATABASE_PASSWORD (from Secret Manager or manually)")
            logger.info("3. Set JWT_SECRET_KEY and REFRESH_SECRET_KEY")
        logger.info("4. For local development, set GOOGLE_APPLICATION_CREDENTIALS")
        logger.info("")


if __name__ == "__main__":
    main()
