#!/usr/bin/env python3
"""
Cloud SQL Instance Setup Script for Document Intelligence Backend.

This script creates and configures the required Cloud SQL PostgreSQL instance.

Usage:
    # Create instance, database, and user
    uv run python scripts/setup_cloud_sql.py

    # Show current Cloud SQL instances
    uv run python scripts/setup_cloud_sql.py status

    # Delete instance (with confirmation)
    uv run python scripts/setup_cloud_sql.py delete

Environment Variables (optional - will prompt if not set):
    GCP_PROJECT_ID - Your GCP project ID
    CLOUD_SQL_INSTANCE_NAME - Name for the Cloud SQL instance
    CLOUD_SQL_REGION - Region (default: us-central1)
    DATABASE_NAME - Database name to create
    DATABASE_USER - Database user to create
    DATABASE_PASSWORD - Password for the database user

Requirements:
    - Google Cloud SDK (gcloud) installed and authenticated
    - Required permissions: Cloud SQL Admin, IAM
"""

import os
import sys
import json
import subprocess
import logging
import secrets
import string
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

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
    logger.info(f"Loaded environment from: {env_path}")


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


def check_gcloud_auth() -> bool:
    """Check if gcloud is authenticated."""
    success, output = run_gcloud_command(["auth", "list", "--format=json"])
    if not success:
        logger.error(f"gcloud auth check failed: {output}")
        return False

    try:
        accounts = json.loads(output)
        active_accounts = [a for a in accounts if a.get("status") == "ACTIVE"]
        if active_accounts:
            logger.info(f"Authenticated as: {active_accounts[0].get('account')}")
            return True
        else:
            logger.error("No active gcloud account. Run: gcloud auth login")
            return False
    except json.JSONDecodeError:
        logger.error("Failed to parse gcloud auth output")
        return False


def get_project_id() -> Optional[str]:
    """Get GCP project ID from environment or gcloud config."""
    # Try environment variable first
    project_id = os.environ.get("GCP_PROJECT_ID")
    if project_id:
        return project_id

    # Try gcloud config
    success, output = run_gcloud_command(["config", "get-value", "project"])
    if success and output:
        return output

    return None


def generate_password(length: int = 16) -> str:
    """Generate a secure random password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def check_instance_exists(project_id: str, instance_name: str) -> bool:
    """Check if a Cloud SQL instance already exists."""
    success, output = run_gcloud_command([
        "sql", "instances", "describe", instance_name,
        "--project", project_id,
        "--format=json"
    ])
    return success


def get_instance_info(project_id: str, instance_name: str) -> Optional[Dict[str, Any]]:
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


def list_instances(project_id: str) -> list:
    """List all Cloud SQL instances in the project."""
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


def create_instance(
    project_id: str,
    instance_name: str,
    region: str = "us-central1",
    tier: str = "db-f1-micro",
    database_version: str = "POSTGRES_15"
) -> bool:
    """Create a Cloud SQL PostgreSQL instance."""
    logger.info(f"Creating Cloud SQL instance: {instance_name}")
    logger.info(f"  Region: {region}")
    logger.info(f"  Tier: {tier}")
    logger.info(f"  PostgreSQL Version: {database_version}")
    logger.info("This may take 5-10 minutes...")

    success, output = run_gcloud_command([
        "sql", "instances", "create", instance_name,
        "--database-version", database_version,
        "--tier", tier,
        "--region", region,
        "--project", project_id,
        "--availability-type", "ZONAL",
        "--storage-type", "SSD",
        "--storage-size", "10GB",
        "--storage-auto-increase",
        "--assign-ip",  # Assign public IP for local development
        "--authorized-networks", "0.0.0.0/0",  # Allow all IPs (for dev only!)
        "--quiet"
    ], capture_output=False)

    if not success:
        logger.error(f"Failed to create instance: {output}")
        return False

    logger.info(f"Instance {instance_name} created successfully!")
    return True


def create_database(project_id: str, instance_name: str, database_name: str) -> bool:
    """Create a database in the Cloud SQL instance."""
    logger.info(f"Creating database: {database_name}")

    success, output = run_gcloud_command([
        "sql", "databases", "create", database_name,
        "--instance", instance_name,
        "--project", project_id
    ])

    if not success:
        if "already exists" in output.lower():
            logger.info(f"Database {database_name} already exists")
            return True
        logger.error(f"Failed to create database: {output}")
        return False

    logger.info(f"Database {database_name} created successfully!")
    return True


def create_user(
    project_id: str,
    instance_name: str,
    username: str,
    password: str
) -> bool:
    """Create a user in the Cloud SQL instance."""
    logger.info(f"Creating user: {username}")

    success, output = run_gcloud_command([
        "sql", "users", "create", username,
        "--instance", instance_name,
        "--project", project_id,
        "--password", password
    ])

    if not success:
        if "already exists" in output.lower():
            logger.info(f"User {username} already exists, updating password...")
            return set_user_password(project_id, instance_name, username, password)
        logger.error(f"Failed to create user: {output}")
        return False

    logger.info(f"User {username} created successfully!")
    return True


def set_user_password(
    project_id: str,
    instance_name: str,
    username: str,
    password: str
) -> bool:
    """Set password for an existing user."""
    success, output = run_gcloud_command([
        "sql", "users", "set-password", username,
        "--instance", instance_name,
        "--project", project_id,
        "--password", password
    ])

    if not success:
        logger.error(f"Failed to set password: {output}")
        return False

    logger.info(f"Password updated for user {username}")
    return True


def get_instance_ip(project_id: str, instance_name: str) -> Optional[str]:
    """Get the public IP address of the Cloud SQL instance."""
    info = get_instance_info(project_id, instance_name)
    if info:
        ip_addresses = info.get("ipAddresses", [])
        for ip in ip_addresses:
            if ip.get("type") == "PRIMARY":
                return ip.get("ipAddress")
    return None


def display_connection_info(
    project_id: str,
    instance_name: str,
    region: str,
    database_name: str,
    username: str,
    password: str
) -> None:
    """Display connection information and .env configuration."""
    instance_connection_name = f"{project_id}:{region}:{instance_name}"
    public_ip = get_instance_ip(project_id, instance_name)

    # URL encode special characters in password
    import urllib.parse
    encoded_password = urllib.parse.quote(password, safe='')

    logger.info("")
    logger.info("=" * 70)
    logger.info("CLOUD SQL SETUP COMPLETE")
    logger.info("=" * 70)
    logger.info("")
    logger.info("Instance Information:")
    logger.info(f"  Instance Name: {instance_name}")
    logger.info(f"  Connection Name: {instance_connection_name}")
    logger.info(f"  Public IP: {public_ip}")
    logger.info(f"  Database: {database_name}")
    logger.info(f"  User: {username}")
    logger.info("")
    logger.info("-" * 70)
    logger.info("Add these to your .env file:")
    logger.info("-" * 70)
    logger.info("")
    print(f"""# =============================================================================
# PostgreSQL Cloud SQL Configuration
# =============================================================================
CLOUD_SQL_INSTANCE={instance_connection_name}
DATABASE_NAME={database_name}
DATABASE_USER={username}
DATABASE_PASSWORD={password}

# Use Cloud SQL connector (recommended for Cloud Run)
USE_CLOUD_SQL_CONNECTOR=true

# Cloud SQL IP type: PUBLIC for local dev, PRIVATE for production (in VPC)
CLOUD_SQL_IP_TYPE=PUBLIC

# Direct PostgreSQL connection URL (for local development)
# NOTE: Password is URL-encoded
DATABASE_URL=postgresql+asyncpg://{username}:{encoded_password}@{public_ip}:5432/{database_name}
""")
    logger.info("")
    logger.info("-" * 70)
    logger.info("Next Steps:")
    logger.info("-" * 70)
    logger.info("1. Copy the configuration above to your .env file")
    logger.info("2. Initialize database tables:")
    logger.info("   uv run python scripts/init_database.py")
    logger.info("3. Start the development server:")
    logger.info("   ./deploy.sh --dev")
    logger.info("")
    logger.info("Security Warning:")
    logger.info("  The instance is configured with public IP and open access (0.0.0.0/0)")
    logger.info("  This is suitable for development only. For production:")
    logger.info("  - Use Private IP with VPC")
    logger.info("  - Configure authorized networks")
    logger.info("  - Use Cloud SQL Proxy or Cloud SQL Connector")
    logger.info("=" * 70)


def show_status(project_id: str) -> None:
    """Show status of Cloud SQL instances."""
    logger.info("=== Cloud SQL Status ===")
    logger.info(f"Project: {project_id}")
    logger.info("")

    instances = list_instances(project_id)
    if not instances:
        logger.info("No Cloud SQL instances found in this project.")
        return

    for instance in instances:
        name = instance.get("name", "Unknown")
        state = instance.get("state", "Unknown")
        region = instance.get("region", "Unknown")
        version = instance.get("databaseVersion", "Unknown")
        tier = instance.get("settings", {}).get("tier", "Unknown")

        # Get IP addresses
        ips = instance.get("ipAddresses", [])
        primary_ip = next((ip["ipAddress"] for ip in ips if ip.get("type") == "PRIMARY"), "None")

        logger.info(f"Instance: {name}")
        logger.info(f"  State: {state}")
        logger.info(f"  Region: {region}")
        logger.info(f"  Version: {version}")
        logger.info(f"  Tier: {tier}")
        logger.info(f"  Public IP: {primary_ip}")
        logger.info(f"  Connection: {project_id}:{region}:{name}")
        logger.info("")


def delete_instance(project_id: str, instance_name: str) -> bool:
    """Delete a Cloud SQL instance."""
    logger.warning(f"=== DELETING Cloud SQL Instance: {instance_name} ===")
    logger.warning("This will permanently delete the instance and ALL data!")

    confirm = input("Type the instance name to confirm deletion: ")
    if confirm != instance_name:
        logger.info("Deletion cancelled - name did not match")
        return False

    success, output = run_gcloud_command([
        "sql", "instances", "delete", instance_name,
        "--project", project_id,
        "--quiet"
    ], capture_output=False)

    if not success:
        logger.error(f"Failed to delete instance: {output}")
        return False

    logger.info(f"Instance {instance_name} deleted successfully")
    return True


def prompt_for_config() -> Dict[str, str]:
    """Prompt user for configuration if not provided via environment."""
    config = {}

    # Project ID
    config["project_id"] = os.environ.get("GCP_PROJECT_ID") or get_project_id()
    if not config["project_id"]:
        config["project_id"] = input("Enter GCP Project ID: ").strip()

    # Instance name
    default_instance = os.environ.get("CLOUD_SQL_INSTANCE_NAME", "doc-intelligence-db")
    config["instance_name"] = input(f"Instance name [{default_instance}]: ").strip() or default_instance

    # Region
    default_region = os.environ.get("CLOUD_SQL_REGION", "us-central1")
    config["region"] = input(f"Region [{default_region}]: ").strip() or default_region

    # Database name
    default_db = os.environ.get("DATABASE_NAME", "doc_intelligence")
    config["database_name"] = input(f"Database name [{default_db}]: ").strip() or default_db

    # Username
    default_user = os.environ.get("DATABASE_USER", "postgres")
    config["username"] = input(f"Database user [{default_user}]: ").strip() or default_user

    # Password
    env_password = os.environ.get("DATABASE_PASSWORD")
    if env_password:
        use_env = input("Use password from environment? [Y/n]: ").strip().lower()
        if use_env != "n":
            config["password"] = env_password
        else:
            config["password"] = input("Enter password (or press Enter to generate): ").strip()
    else:
        config["password"] = input("Enter password (or press Enter to generate): ").strip()

    if not config["password"]:
        config["password"] = generate_password()
        logger.info(f"Generated password: {config['password']}")

    # Tier
    default_tier = "db-f1-micro"
    print("\nAvailable tiers:")
    print("  db-f1-micro    - Shared core, 0.6 GB RAM (cheapest, dev only)")
    print("  db-g1-small    - Shared core, 1.7 GB RAM")
    print("  db-custom-1-3840 - 1 vCPU, 3.75 GB RAM (recommended for production)")
    config["tier"] = input(f"Instance tier [{default_tier}]: ").strip() or default_tier

    return config


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Setup Cloud SQL PostgreSQL instance for Document Intelligence API"
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="create",
        choices=["create", "status", "delete"],
        help="Command to run (default: create)"
    )
    parser.add_argument(
        "--project",
        help="GCP Project ID (overrides environment)"
    )
    parser.add_argument(
        "--instance",
        help="Instance name for delete command"
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Run without prompts (for CI/CD)"
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
        "--tier",
        default="db-f1-micro",
        help="Instance tier (default: db-f1-micro)"
    )
    parser.add_argument(
        "--region",
        default="us-central1",
        help="Region (default: us-central1)"
    )

    args = parser.parse_args()

    # Check gcloud is available and authenticated
    logger.info("Checking gcloud authentication...")
    if not check_gcloud_auth():
        logger.error("Please authenticate with: gcloud auth login")
        sys.exit(1)

    project_id = args.project or get_project_id()
    if not project_id:
        project_id = input("Enter GCP Project ID: ").strip()

    if not project_id:
        logger.error("No project ID provided")
        sys.exit(1)

    logger.info(f"Using project: {project_id}")

    if args.command == "status":
        show_status(project_id)

    elif args.command == "delete":
        instance_name = args.instance
        if not instance_name:
            instance_name = input("Enter instance name to delete: ").strip()
        if instance_name:
            delete_instance(project_id, instance_name)
        else:
            logger.error("No instance name provided")

    elif args.command == "create":
        logger.info("")
        logger.info("=" * 70)
        logger.info("Cloud SQL PostgreSQL Instance Setup")
        logger.info("=" * 70)
        logger.info("")

        # Get configuration - use args in non-interactive mode
        if args.non_interactive:
            # Build config from command line arguments
            config = {
                "project_id": project_id,
                "instance_name": args.instance or os.environ.get("CLOUD_SQL_INSTANCE_NAME", "doc-intelligence-db"),
                "region": args.region,
                "database_name": args.database,
                "username": args.user,
                "password": os.environ.get("DATABASE_PASSWORD") or generate_password(),
                "tier": args.tier,
            }
        else:
            config = prompt_for_config()

        logger.info("")
        logger.info("Configuration Summary:")
        logger.info(f"  Project: {config['project_id']}")
        logger.info(f"  Instance: {config['instance_name']}")
        logger.info(f"  Region: {config['region']}")
        logger.info(f"  Database: {config['database_name']}")
        logger.info(f"  User: {config['username']}")
        logger.info(f"  Tier: {config['tier']}")
        logger.info("")

        if not args.non_interactive:
            confirm = input("Proceed with setup? [Y/n]: ").strip().lower()
            if confirm == "n":
                logger.info("Setup cancelled")
                sys.exit(0)

        # Check if instance exists
        if check_instance_exists(config["project_id"], config["instance_name"]):
            logger.info(f"Instance {config['instance_name']} already exists")
            if not args.non_interactive:
                use_existing = input("Use existing instance? [Y/n]: ").strip().lower()
                if use_existing == "n":
                    logger.info("Setup cancelled")
                    sys.exit(0)
            # In non-interactive mode, always use existing instance
        else:
            # Create instance
            if not create_instance(
                config["project_id"],
                config["instance_name"],
                config["region"],
                config["tier"]
            ):
                logger.error("Failed to create instance")
                sys.exit(1)

        # Create database
        if not create_database(
            config["project_id"],
            config["instance_name"],
            config["database_name"]
        ):
            logger.error("Failed to create database")
            sys.exit(1)

        # Create user
        if not create_user(
            config["project_id"],
            config["instance_name"],
            config["username"],
            config["password"]
        ):
            logger.error("Failed to create user")
            sys.exit(1)

        # Display connection info
        display_connection_info(
            config["project_id"],
            config["instance_name"],
            config["region"],
            config["database_name"],
            config["username"],
            config["password"]
        )


if __name__ == "__main__":
    main()
