#!/usr/bin/env python3
"""
Secret Manager Setup Script for Document Intelligence Backend.

This script creates and manages secrets in Google Cloud Secret Manager.

Usage:
    # Create all required secrets with generated values
    uv run python scripts/setup_secrets.py create

    # Show current secrets status
    uv run python scripts/setup_secrets.py status

    # Get a secret value
    uv run python scripts/setup_secrets.py get DATABASE_PASSWORD

    # Delete a secret
    uv run python scripts/setup_secrets.py delete DATABASE_PASSWORD

    # Non-interactive mode
    uv run python scripts/setup_secrets.py create --non-interactive

Environment Variables:
    GCP_PROJECT_ID - Your GCP project ID

Requirements:
    - Google Cloud SDK (gcloud) installed and authenticated
    - Required permissions: Secret Manager Admin
    - Secret Manager API enabled
"""

import os
import sys
import json
import subprocess
import logging
import secrets
import string
import argparse
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List

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

# Secrets to manage
REQUIRED_SECRETS = [
    {
        "name": "DATABASE_PASSWORD",
        "description": "PostgreSQL database password",
        "length": 32,
    },
    {
        "name": "JWT_SECRET_KEY",
        "description": "JWT signing secret key",
        "length": 64,
    },
    {
        "name": "REFRESH_SECRET_KEY",
        "description": "Refresh token signing secret key",
        "length": 64,
    },
]


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
    project_id = os.environ.get("GCP_PROJECT_ID")
    if project_id:
        return project_id

    success, output = run_gcloud_command(["config", "get-value", "project"])
    if success and output:
        return output

    return None


def generate_secure_key(length: int = 64) -> str:
    """Generate a cryptographically secure random key."""
    # Use URL-safe characters for easier handling
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def generate_secure_password(length: int = 32) -> str:
    """Generate a secure random password with special characters."""
    # Include special characters for passwords
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_=+"
    # Ensure at least one of each character type
    password = [
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%^&*-_=+"),
    ]
    # Fill the rest randomly
    password.extend(secrets.choice(alphabet) for _ in range(length - 4))
    # Shuffle to randomize position
    secrets.SystemRandom().shuffle(password)
    return ''.join(password)


def enable_secret_manager_api(project_id: str) -> bool:
    """Enable the Secret Manager API for the project."""
    logger.info("Enabling Secret Manager API...")

    success, output = run_gcloud_command([
        "services", "enable", "secretmanager.googleapis.com",
        "--project", project_id
    ])

    if not success:
        if "already enabled" in output.lower():
            logger.info("Secret Manager API is already enabled")
            return True
        logger.error(f"Failed to enable Secret Manager API: {output}")
        return False

    logger.info("Secret Manager API enabled successfully")
    return True


def check_secret_exists(project_id: str, secret_id: str) -> bool:
    """Check if a secret exists."""
    success, _ = run_gcloud_command([
        "secrets", "describe", secret_id,
        "--project", project_id,
        "--format=json"
    ])
    return success


def get_secret_info(project_id: str, secret_id: str) -> Optional[Dict[str, Any]]:
    """Get secret metadata (not the value)."""
    success, output = run_gcloud_command([
        "secrets", "describe", secret_id,
        "--project", project_id,
        "--format=json"
    ])
    if success:
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return None
    return None


def list_secrets(project_id: str) -> List[Dict[str, Any]]:
    """List all secrets in the project."""
    success, output = run_gcloud_command([
        "secrets", "list",
        "--project", project_id,
        "--format=json"
    ])
    if success:
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return []
    return []


def create_secret(
    project_id: str,
    secret_id: str,
    secret_value: str,
    description: str = ""
) -> bool:
    """Create a new secret with an initial version."""
    logger.info(f"Creating secret: {secret_id}")

    # First, create the secret (without a value)
    labels = f"app=document-intelligence,managed-by=setup-script"
    success, output = run_gcloud_command([
        "secrets", "create", secret_id,
        "--project", project_id,
        "--replication-policy", "automatic",
        "--labels", labels
    ])

    if not success:
        if "already exists" in output.lower():
            logger.info(f"Secret {secret_id} already exists, adding new version...")
        else:
            logger.error(f"Failed to create secret: {output}")
            return False

    # Add a version with the actual value
    # Use echo and pipe to avoid exposing the value in process list
    try:
        cmd = f'echo -n "{secret_value}" | gcloud secrets versions add {secret_id} --data-file=- --project={project_id}'
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode != 0:
            logger.error(f"Failed to add secret version: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"Failed to add secret version: {e}")
        return False

    logger.info(f"Secret {secret_id} created/updated successfully!")
    return True


def get_secret_value(project_id: str, secret_id: str, version: str = "latest") -> Optional[str]:
    """Get the value of a secret."""
    success, output = run_gcloud_command([
        "secrets", "versions", "access", version,
        "--secret", secret_id,
        "--project", project_id
    ])

    if not success:
        logger.error(f"Failed to get secret value: {output}")
        return None

    return output


def delete_secret(project_id: str, secret_id: str, force: bool = False) -> bool:
    """Delete a secret."""
    logger.warning(f"Deleting secret: {secret_id}")

    if not force:
        confirm = input(f"Type '{secret_id}' to confirm deletion: ")
        if confirm != secret_id:
            logger.info("Deletion cancelled - name did not match")
            return False

    success, output = run_gcloud_command([
        "secrets", "delete", secret_id,
        "--project", project_id,
        "--quiet"
    ])

    if not success:
        logger.error(f"Failed to delete secret: {output}")
        return False

    logger.info(f"Secret {secret_id} deleted successfully")
    return True


def show_status(project_id: str) -> None:
    """Show status of secrets."""
    logger.info("=== Secret Manager Status ===")
    logger.info(f"Project: {project_id}")
    logger.info("")

    # Check if API is enabled
    success, _ = run_gcloud_command([
        "services", "list",
        "--project", project_id,
        "--filter", "name:secretmanager.googleapis.com",
        "--format=json"
    ])

    if success:
        logger.info("Secret Manager API: Enabled")
    else:
        logger.warning("Secret Manager API: Not enabled or inaccessible")
        logger.info("Run 'create' to enable and create secrets")
        return

    logger.info("")

    # List required secrets
    logger.info("Required Secrets:")
    for secret_config in REQUIRED_SECRETS:
        secret_id = secret_config["name"]
        exists = check_secret_exists(project_id, secret_id)
        status = "EXISTS" if exists else "MISSING"
        logger.info(f"  - {secret_id}: {status}")
        if exists:
            info = get_secret_info(project_id, secret_id)
            if info:
                created = info.get("createTime", "Unknown")
                logger.info(f"      Created: {created}")

    # List all secrets
    logger.info("")
    logger.info("All Secrets in Project:")
    all_secrets = list_secrets(project_id)
    if all_secrets:
        for secret in all_secrets:
            name = secret.get("name", "").split("/")[-1]
            logger.info(f"  - {name}")
    else:
        logger.info("  (none)")


def create_all_secrets(project_id: str, non_interactive: bool = False) -> Dict[str, str]:
    """Create all required secrets and return their values."""
    logger.info("")
    logger.info("=" * 70)
    logger.info("Secret Manager Setup")
    logger.info("=" * 70)
    logger.info("")

    # Enable API first
    if not enable_secret_manager_api(project_id):
        logger.error("Cannot proceed without Secret Manager API")
        sys.exit(1)

    secrets_created = {}

    for secret_config in REQUIRED_SECRETS:
        secret_id = secret_config["name"]
        description = secret_config["description"]
        length = secret_config["length"]

        logger.info("")
        logger.info(f"Processing: {secret_id}")
        logger.info(f"  Description: {description}")

        # Check if exists
        if check_secret_exists(project_id, secret_id):
            if non_interactive:
                logger.info(f"  Secret exists, skipping...")
                # Try to get existing value
                value = get_secret_value(project_id, secret_id)
                if value:
                    secrets_created[secret_id] = value
                continue
            else:
                action = input(f"  Secret exists. [S]kip, [R]egenerate, or [E]nter value? [S/r/e]: ").strip().lower()
                if action == "r":
                    logger.info("  Regenerating secret...")
                elif action == "e":
                    value = input(f"  Enter value for {secret_id}: ").strip()
                    if not value:
                        logger.warning("  Empty value, skipping...")
                        continue
                    if create_secret(project_id, secret_id, value, description):
                        secrets_created[secret_id] = value
                    continue
                else:
                    logger.info("  Skipping...")
                    value = get_secret_value(project_id, secret_id)
                    if value:
                        secrets_created[secret_id] = value
                    continue

        # Generate new value
        if "PASSWORD" in secret_id:
            value = generate_secure_password(length)
        else:
            value = generate_secure_key(length)

        # Create the secret
        if create_secret(project_id, secret_id, value, description):
            secrets_created[secret_id] = value
            logger.info(f"  Value (first 8 chars): {value[:8]}...")

    return secrets_created


def display_completion_info(project_id: str, secrets_created: Dict[str, str]) -> None:
    """Display setup completion information."""
    logger.info("")
    logger.info("=" * 70)
    logger.info("SECRET MANAGER SETUP COMPLETE")
    logger.info("=" * 70)
    logger.info("")
    logger.info(f"Project: {project_id}")
    logger.info("")
    logger.info("Secrets Created/Updated:")
    for secret_id in secrets_created:
        logger.info(f"  - {secret_id}")

    logger.info("")
    logger.info("-" * 70)
    logger.info("Accessing Secrets in Code:")
    logger.info("-" * 70)
    logger.info("")
    logger.info("Option 1: Direct access via Secret Manager API")
    logger.info("  from google.cloud import secretmanager")
    logger.info("  client = secretmanager.SecretManagerServiceClient()")
    logger.info(f'  name = f"projects/{project_id}/secrets/DATABASE_PASSWORD/versions/latest"')
    logger.info("  response = client.access_secret_version(request={\"name\": name})")
    logger.info("  password = response.payload.data.decode('UTF-8')")
    logger.info("")
    logger.info("Option 2: Environment variables in Cloud Run")
    logger.info("  Configure secrets as environment variables in Cloud Run service")
    logger.info("")
    logger.info("-" * 70)
    logger.info("Cloud Run Configuration:")
    logger.info("-" * 70)
    for secret_id in secrets_created:
        logger.info(f"  --set-secrets={secret_id}={secret_id}:latest")
    logger.info("")
    logger.info("=" * 70)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Setup secrets in Secret Manager for Document Intelligence API"
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="create",
        choices=["create", "status", "get", "delete"],
        help="Command to run (default: create)"
    )
    parser.add_argument(
        "secret_name",
        nargs="?",
        help="Secret name (for get/delete commands)"
    )
    parser.add_argument(
        "--project",
        help="GCP Project ID (overrides environment)"
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Run without prompts (for CI/CD)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force operation without confirmation"
    )

    args = parser.parse_args()

    # Check gcloud is available and authenticated
    logger.info("Checking gcloud authentication...")
    if not check_gcloud_auth():
        logger.error("Please authenticate with: gcloud auth login")
        sys.exit(1)

    # Get project ID
    project_id = args.project or os.environ.get("GCP_PROJECT_ID") or get_project_id()
    if not project_id:
        if args.non_interactive:
            logger.error("GCP_PROJECT_ID not set")
            sys.exit(1)
        project_id = input("Enter GCP Project ID: ").strip()

    if not project_id:
        logger.error("No project ID provided")
        sys.exit(1)

    logger.info(f"Using project: {project_id}")

    if args.command == "status":
        show_status(project_id)

    elif args.command == "get":
        if not args.secret_name:
            logger.error("Secret name required for 'get' command")
            sys.exit(1)
        value = get_secret_value(project_id, args.secret_name)
        if value:
            print(value)
        else:
            sys.exit(1)

    elif args.command == "delete":
        if not args.secret_name:
            logger.error("Secret name required for 'delete' command")
            sys.exit(1)
        delete_secret(project_id, args.secret_name, args.force)

    elif args.command == "create":
        secrets_created = create_all_secrets(project_id, args.non_interactive)
        display_completion_info(project_id, secrets_created)


if __name__ == "__main__":
    main()
