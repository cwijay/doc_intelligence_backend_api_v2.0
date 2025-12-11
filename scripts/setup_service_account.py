#!/usr/bin/env python3
"""
Service Account Setup Script for Document Intelligence Backend.

This script creates and configures the required service account with IAM roles.

Usage:
    # Create service account with all required roles
    uv run python scripts/setup_service_account.py create

    # Show current service accounts
    uv run python scripts/setup_service_account.py status

    # Generate a key file for local development
    uv run python scripts/setup_service_account.py create-key --output credentials.json

    # Delete service account
    uv run python scripts/setup_service_account.py delete

    # Non-interactive mode
    uv run python scripts/setup_service_account.py create --non-interactive

Environment Variables:
    GCP_PROJECT_ID - Your GCP project ID
    SERVICE_ACCOUNT_NAME - Name for the service account (default: document-intelligence-api-sa)

Requirements:
    - Google Cloud SDK (gcloud) installed and authenticated
    - Required permissions: IAM Admin, Service Account Admin
"""

import os
import sys
import json
import subprocess
import logging
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

# Default configuration
DEFAULT_SERVICE_ACCOUNT_NAME = "document-intelligence-api-sa"
DEFAULT_DISPLAY_NAME = "Document Intelligence API Service Account"

# Required IAM roles for the service account
REQUIRED_ROLES = [
    "roles/cloudsql.client",      # Cloud SQL access
    "roles/storage.objectAdmin",   # GCS bucket access
    "roles/logging.logWriter",     # Cloud Logging
    "roles/run.invoker",           # Cloud Run invocation
    "roles/secretmanager.secretAccessor",  # Secret Manager access
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


def get_service_account_email(project_id: str, account_name: str) -> str:
    """Generate the service account email from project and account name."""
    return f"{account_name}@{project_id}.iam.gserviceaccount.com"


def check_service_account_exists(project_id: str, account_name: str) -> bool:
    """Check if a service account already exists."""
    email = get_service_account_email(project_id, account_name)
    success, _ = run_gcloud_command([
        "iam", "service-accounts", "describe", email,
        "--project", project_id,
        "--format=json"
    ])
    return success


def get_service_account_info(project_id: str, account_name: str) -> Optional[Dict[str, Any]]:
    """Get service account information."""
    email = get_service_account_email(project_id, account_name)
    success, output = run_gcloud_command([
        "iam", "service-accounts", "describe", email,
        "--project", project_id,
        "--format=json"
    ])
    if success:
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return None
    return None


def list_service_accounts(project_id: str) -> List[Dict[str, Any]]:
    """List all service accounts in the project."""
    success, output = run_gcloud_command([
        "iam", "service-accounts", "list",
        "--project", project_id,
        "--format=json"
    ])
    if success:
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return []
    return []


def create_service_account(
    project_id: str,
    account_name: str,
    display_name: str
) -> bool:
    """Create a new service account."""
    logger.info(f"Creating service account: {account_name}")

    success, output = run_gcloud_command([
        "iam", "service-accounts", "create", account_name,
        "--display-name", display_name,
        "--project", project_id
    ])

    if not success:
        if "already exists" in output.lower():
            logger.info(f"Service account {account_name} already exists")
            return True
        logger.error(f"Failed to create service account: {output}")
        return False

    logger.info(f"Service account {account_name} created successfully!")
    return True


def assign_iam_role(
    project_id: str,
    account_email: str,
    role: str
) -> bool:
    """Assign an IAM role to the service account."""
    logger.info(f"Assigning role: {role}")

    success, output = run_gcloud_command([
        "projects", "add-iam-policy-binding", project_id,
        "--member", f"serviceAccount:{account_email}",
        "--role", role,
        "--condition=None"
    ])

    if not success:
        logger.error(f"Failed to assign role {role}: {output}")
        return False

    return True


def assign_all_roles(project_id: str, account_email: str, roles: List[str]) -> bool:
    """Assign all required IAM roles to the service account."""
    logger.info(f"Assigning {len(roles)} IAM roles...")

    all_success = True
    for role in roles:
        if not assign_iam_role(project_id, account_email, role):
            all_success = False

    if all_success:
        logger.info("All IAM roles assigned successfully!")
    else:
        logger.warning("Some IAM roles failed to assign")

    return all_success


def get_assigned_roles(project_id: str, account_email: str) -> List[str]:
    """Get all roles currently assigned to the service account."""
    success, output = run_gcloud_command([
        "projects", "get-iam-policy", project_id,
        "--format=json"
    ])

    if not success:
        return []

    try:
        policy = json.loads(output)
        roles = []
        member = f"serviceAccount:{account_email}"
        for binding in policy.get("bindings", []):
            if member in binding.get("members", []):
                roles.append(binding.get("role", ""))
        return roles
    except json.JSONDecodeError:
        return []


def create_key_file(
    project_id: str,
    account_email: str,
    output_path: str
) -> bool:
    """Create and download a service account key file."""
    logger.info(f"Creating key file: {output_path}")

    success, output = run_gcloud_command([
        "iam", "service-accounts", "keys", "create", output_path,
        "--iam-account", account_email,
        "--project", project_id
    ])

    if not success:
        logger.error(f"Failed to create key file: {output}")
        return False

    logger.info(f"Key file created: {output_path}")
    logger.warning("Keep this file secure! Do not commit to version control.")
    return True


def delete_service_account(project_id: str, account_name: str) -> bool:
    """Delete a service account."""
    email = get_service_account_email(project_id, account_name)

    logger.warning(f"Deleting service account: {email}")
    confirm = input("Type the account name to confirm deletion: ")
    if confirm != account_name:
        logger.info("Deletion cancelled - name did not match")
        return False

    success, output = run_gcloud_command([
        "iam", "service-accounts", "delete", email,
        "--project", project_id,
        "--quiet"
    ])

    if not success:
        logger.error(f"Failed to delete service account: {output}")
        return False

    logger.info(f"Service account {account_name} deleted successfully")
    return True


def show_status(project_id: str, account_name: str) -> None:
    """Show status of the service account."""
    logger.info("=== Service Account Status ===")
    logger.info(f"Project: {project_id}")
    logger.info("")

    email = get_service_account_email(project_id, account_name)
    info = get_service_account_info(project_id, account_name)

    if info:
        logger.info(f"Service Account: {account_name}")
        logger.info(f"  Email: {email}")
        logger.info(f"  Display Name: {info.get('displayName', 'N/A')}")
        logger.info(f"  Unique ID: {info.get('uniqueId', 'N/A')}")
        logger.info(f"  Disabled: {info.get('disabled', False)}")

        # Show assigned roles
        roles = get_assigned_roles(project_id, email)
        if roles:
            logger.info("  Assigned Roles:")
            for role in roles:
                status = "OK" if role in REQUIRED_ROLES else ""
                logger.info(f"    - {role} {status}")

        # Check for missing roles
        missing = [r for r in REQUIRED_ROLES if r not in roles]
        if missing:
            logger.warning("  Missing Roles:")
            for role in missing:
                logger.warning(f"    - {role}")
    else:
        logger.info(f"Service account {account_name} does not exist")
        logger.info(f"Run 'create' to create it")

    # List all service accounts
    logger.info("")
    logger.info("All Service Accounts in Project:")
    accounts = list_service_accounts(project_id)
    for acc in accounts:
        email = acc.get("email", "Unknown")
        name = acc.get("displayName", "No display name")
        logger.info(f"  - {email}")
        logger.info(f"    Display Name: {name}")


def display_completion_info(
    project_id: str,
    account_name: str,
    key_file: Optional[str] = None
) -> None:
    """Display setup completion information."""
    email = get_service_account_email(project_id, account_name)

    logger.info("")
    logger.info("=" * 70)
    logger.info("SERVICE ACCOUNT SETUP COMPLETE")
    logger.info("=" * 70)
    logger.info("")
    logger.info("Service Account Information:")
    logger.info(f"  Name: {account_name}")
    logger.info(f"  Email: {email}")
    logger.info(f"  Project: {project_id}")
    logger.info("")
    logger.info("Assigned Roles:")
    for role in REQUIRED_ROLES:
        logger.info(f"  - {role}")
    logger.info("")

    if key_file:
        logger.info("-" * 70)
        logger.info("Key File Generated:")
        logger.info(f"  {key_file}")
        logger.info("")
        logger.info("Add to your .env file:")
        logger.info(f"  GOOGLE_APPLICATION_CREDENTIALS={key_file}")
        logger.info("")
        logger.warning("SECURITY WARNING:")
        logger.warning("  - Keep the key file secure")
        logger.warning("  - Do NOT commit to version control")
        logger.warning("  - Add to .gitignore")

    logger.info("")
    logger.info("-" * 70)
    logger.info("For Cloud Run deployment, use Workload Identity instead of key files")
    logger.info("=" * 70)


def prompt_for_config(non_interactive: bool = False) -> Dict[str, str]:
    """Prompt user for configuration if not provided via environment."""
    config = {}

    # Project ID
    config["project_id"] = os.environ.get("GCP_PROJECT_ID") or get_project_id()
    if not config["project_id"]:
        if non_interactive:
            logger.error("GCP_PROJECT_ID not set and non-interactive mode enabled")
            sys.exit(1)
        config["project_id"] = input("Enter GCP Project ID: ").strip()

    # Service account name
    default_name = os.environ.get("SERVICE_ACCOUNT_NAME", DEFAULT_SERVICE_ACCOUNT_NAME)
    if non_interactive:
        config["account_name"] = default_name
    else:
        config["account_name"] = input(f"Service account name [{default_name}]: ").strip() or default_name

    # Display name
    if non_interactive:
        config["display_name"] = DEFAULT_DISPLAY_NAME
    else:
        config["display_name"] = input(f"Display name [{DEFAULT_DISPLAY_NAME}]: ").strip() or DEFAULT_DISPLAY_NAME

    return config


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Setup service account for Document Intelligence API"
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="create",
        choices=["create", "status", "delete", "create-key"],
        help="Command to run (default: create)"
    )
    parser.add_argument(
        "--project",
        help="GCP Project ID (overrides environment)"
    )
    parser.add_argument(
        "--name",
        help="Service account name"
    )
    parser.add_argument(
        "--output",
        default="credentials.json",
        help="Output path for key file (for create-key command)"
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Run without prompts (for CI/CD)"
    )
    parser.add_argument(
        "--skip-roles",
        action="store_true",
        help="Skip IAM role assignment"
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

    # Get account name
    account_name = args.name or os.environ.get("SERVICE_ACCOUNT_NAME", DEFAULT_SERVICE_ACCOUNT_NAME)

    if args.command == "status":
        show_status(project_id, account_name)

    elif args.command == "delete":
        delete_service_account(project_id, account_name)

    elif args.command == "create-key":
        email = get_service_account_email(project_id, account_name)
        if not check_service_account_exists(project_id, account_name):
            logger.error(f"Service account {account_name} does not exist")
            logger.error("Run 'create' first to create the service account")
            sys.exit(1)
        create_key_file(project_id, email, args.output)

    elif args.command == "create":
        logger.info("")
        logger.info("=" * 70)
        logger.info("Service Account Setup")
        logger.info("=" * 70)
        logger.info("")

        # Get configuration
        if args.non_interactive:
            config = {
                "project_id": project_id,
                "account_name": account_name,
                "display_name": DEFAULT_DISPLAY_NAME
            }
        else:
            config = prompt_for_config(args.non_interactive)
            project_id = config["project_id"]
            account_name = config["account_name"]

        email = get_service_account_email(project_id, account_name)

        logger.info("")
        logger.info("Configuration Summary:")
        logger.info(f"  Project: {project_id}")
        logger.info(f"  Account Name: {account_name}")
        logger.info(f"  Email: {email}")
        logger.info(f"  Display Name: {config['display_name']}")
        logger.info("")

        if not args.non_interactive:
            confirm = input("Proceed with setup? [Y/n]: ").strip().lower()
            if confirm == "n":
                logger.info("Setup cancelled")
                sys.exit(0)

        # Create service account
        if check_service_account_exists(project_id, account_name):
            logger.info(f"Service account {account_name} already exists")
        else:
            if not create_service_account(project_id, account_name, config["display_name"]):
                logger.error("Failed to create service account")
                sys.exit(1)

        # Assign IAM roles
        if not args.skip_roles:
            if not assign_all_roles(project_id, email, REQUIRED_ROLES):
                logger.warning("Some roles failed to assign, but continuing...")

        # Display completion info
        display_completion_info(project_id, account_name)


if __name__ == "__main__":
    main()
