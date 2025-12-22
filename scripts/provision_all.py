#!/usr/bin/env python3
"""
GCP Resource Provisioning Script for Document Intelligence Backend.

Reads configuration from .env.production and provisions/verifies GCP resources:
1. Cloud SQL PostgreSQL instance, database, and user
2. GCS bucket with versioning
3. Service Account with IAM roles
4. Secret Manager secrets
5. Database tables (optional, with --init-tables)
6. Environment file generation (optional, with --generate-env)

Usage:
    # Full setup (provision + init tables + generate env) - RECOMMENDED
    uv run python scripts/provision_all.py --full-setup --env-file .env.production

    # Default: read from .env.production (provision GCP resources only)
    uv run python scripts/provision_all.py

    # Specify different env file
    uv run python scripts/provision_all.py --env-file .env

    # Provision + initialize database tables
    uv run python scripts/provision_all.py --init-tables

    # Provision + generate .env file from provisioned resources
    uv run python scripts/provision_all.py --generate-env --env-output .env.local

    # Dry run (preview actions)
    uv run python scripts/provision_all.py --dry-run

    # Skip specific steps
    uv run python scripts/provision_all.py --skip-cloudsql --skip-bucket

    # Delete all resources and recreate
    uv run python scripts/provision_all.py --delete

    # Delete only (don't recreate)
    uv run python scripts/provision_all.py --delete-only

    # Delete without confirmation (for CI/CD)
    uv run python scripts/provision_all.py --delete --force

Requirements:
    - Google Cloud SDK (gcloud) installed and authenticated
    - Required permissions: Project Owner or equivalent
"""

import sys
import json
import subprocess
import argparse
from pathlib import Path
from typing import Tuple, List
from dataclasses import dataclass, field
from enum import Enum

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class Status(Enum):
    """Resource status."""
    EXISTS = "EXISTS"
    CREATED = "CREATED"
    DELETED = "DELETED"
    MISSING = "MISSING"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


# ANSI color codes
class Colors:
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    END = "\033[0m"


def colored(text: str, color: str) -> str:
    """Return colored text."""
    return f"{color}{text}{Colors.END}"


def status_icon(status: Status) -> str:
    """Return colored status with icon."""
    if status == Status.EXISTS:
        return colored("EXISTS ✓", Colors.GREEN)
    elif status == Status.CREATED:
        return colored("CREATED ✓", Colors.GREEN)
    elif status == Status.DELETED:
        return colored("DELETED ✓", Colors.RED)
    elif status == Status.MISSING:
        return colored("MISSING ✗", Colors.RED)
    elif status == Status.FAILED:
        return colored("FAILED ✗", Colors.RED)
    elif status == Status.SKIPPED:
        return colored("SKIPPED", Colors.YELLOW)
    return str(status.value)


@dataclass
class ProvisioningConfig:
    """Configuration for provisioning."""
    project_id: str
    region: str = "us-central1"

    # Cloud SQL
    cloud_sql_instance: str = ""
    database_name: str = ""
    database_user: str = "postgres"
    database_password: str = ""
    cloud_sql_tier: str = "db-f1-micro"

    # GCS
    bucket_name: str = ""
    storage_class: str = "STANDARD"

    # Service Account
    service_account_name: str = "document-intelligence-api-sa"

    # Secrets
    jwt_secret_key: str = ""

    # Options
    skip_steps: List[str] = field(default_factory=list)
    dry_run: bool = False
    env_file: str = ".env.production"


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
        return False
    try:
        accounts = json.loads(output)
        return any(a.get("status") == "ACTIVE" for a in accounts)
    except json.JSONDecodeError:
        return False


def load_config_from_env(env_file_path: str) -> ProvisioningConfig:
    """Load configuration from .env file."""
    env_path = project_root / env_file_path

    if not env_path.exists():
        print(colored(f"Error: Environment file not found: {env_file_path}", Colors.RED))
        sys.exit(1)

    # Parse .env file
    env_vars = {}
    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, value = line.split('=', 1)
                # Remove quotes from value
                value = value.strip().strip('"').strip("'")
                env_vars[key.strip()] = value

    # Extract required values
    project_id = env_vars.get("GCP_PROJECT_ID", "")
    if not project_id:
        print(colored("Error: GCP_PROJECT_ID not found in env file", Colors.RED))
        sys.exit(1)

    # Parse CLOUD_SQL_INSTANCE (format: project:region:instance)
    cloud_sql_instance_full = env_vars.get("CLOUD_SQL_INSTANCE", "")
    region = "us-central1"
    cloud_sql_instance = ""

    if cloud_sql_instance_full:
        parts = cloud_sql_instance_full.split(":")
        if len(parts) == 3:
            region = parts[1]
            cloud_sql_instance = parts[2]
        else:
            cloud_sql_instance = cloud_sql_instance_full

    return ProvisioningConfig(
        project_id=project_id,
        region=region,
        cloud_sql_instance=cloud_sql_instance,
        database_name=env_vars.get("DATABASE_NAME", "doc_intelligence"),
        database_user=env_vars.get("DATABASE_USER", "postgres"),
        database_password=env_vars.get("DATABASE_PASSWORD", ""),
        bucket_name=env_vars.get("GCS_BUCKET_NAME", f"{project_id}-document-store"),
        jwt_secret_key=env_vars.get("JWT_SECRET_KEY", ""),
        env_file=env_file_path,
    )


def display_config(config: ProvisioningConfig) -> None:
    """Display configuration summary."""
    print(f"\n{colored('Configuration:', Colors.BOLD)}")
    print(f"  Project ID:     {config.project_id}")
    print(f"  Region:         {config.region}")
    print(f"  Cloud SQL:      {config.cloud_sql_instance}")
    print(f"  Database:       {config.database_name}")
    print(f"  Database User:  {config.database_user}")
    print(f"  GCS Bucket:     {config.bucket_name}")
    print()


# =============================================================================
# DELETE FUNCTIONS
# =============================================================================

def delete_cloud_sql_instance(config: ProvisioningConfig) -> Status:
    """Delete Cloud SQL instance."""
    if config.dry_run:
        print(f"      [DRY RUN] Would delete instance: {config.cloud_sql_instance}")
        return Status.SKIPPED

    # Check if exists
    success, _ = run_gcloud_command([
        "sql", "instances", "describe", config.cloud_sql_instance,
        "--project", config.project_id
    ])

    if not success:
        return Status.MISSING

    # Delete instance
    print(f"      Deleting Cloud SQL instance (this may take a few minutes)...")
    success, _ = run_gcloud_command([
        "sql", "instances", "delete", config.cloud_sql_instance,
        "--project", config.project_id,
        "--quiet"
    ], capture_output=False)

    return Status.DELETED if success else Status.FAILED


def delete_gcs_bucket(config: ProvisioningConfig) -> Status:
    """Delete GCS bucket and all contents."""
    if config.dry_run:
        print(f"      [DRY RUN] Would delete bucket: {config.bucket_name}")
        return Status.SKIPPED

    # Check if exists
    success, _ = run_gcloud_command([
        "storage", "buckets", "describe", f"gs://{config.bucket_name}",
        "--project", config.project_id
    ])

    if not success:
        return Status.MISSING

    # Delete all objects first
    print(f"      Deleting all objects in bucket...")
    run_gcloud_command([
        "storage", "rm", "-r", f"gs://{config.bucket_name}/**",
        "--quiet"
    ])

    # Delete bucket
    print(f"      Deleting bucket...")
    success, _ = run_gcloud_command([
        "storage", "buckets", "delete", f"gs://{config.bucket_name}",
        "--quiet"
    ])

    return Status.DELETED if success else Status.FAILED


def delete_service_account(config: ProvisioningConfig) -> Status:
    """Delete service account."""
    if config.dry_run:
        print(f"      [DRY RUN] Would delete service account: {config.service_account_name}")
        return Status.SKIPPED

    sa_email = f"{config.service_account_name}@{config.project_id}.iam.gserviceaccount.com"

    # Check if exists
    success, _ = run_gcloud_command([
        "iam", "service-accounts", "describe", sa_email,
        "--project", config.project_id
    ])

    if not success:
        return Status.MISSING

    # Delete service account
    success, _ = run_gcloud_command([
        "iam", "service-accounts", "delete", sa_email,
        "--project", config.project_id,
        "--quiet"
    ])

    return Status.DELETED if success else Status.FAILED


def delete_secret(config: ProvisioningConfig, secret_name: str) -> Status:
    """Delete a secret from Secret Manager."""
    if config.dry_run:
        print(f"      [DRY RUN] Would delete secret: {secret_name}")
        return Status.SKIPPED

    # Check if exists
    success, _ = run_gcloud_command([
        "secrets", "describe", secret_name,
        "--project", config.project_id
    ])

    if not success:
        return Status.MISSING

    # Delete secret
    success, _ = run_gcloud_command([
        "secrets", "delete", secret_name,
        "--project", config.project_id,
        "--quiet"
    ])

    return Status.DELETED if success else Status.FAILED


def confirm_delete(config: ProvisioningConfig) -> bool:
    """Prompt user to confirm deletion."""
    print()
    print(colored("=" * 60, Colors.RED))
    print(colored("⚠️  WARNING: DESTRUCTIVE OPERATION", Colors.RED + Colors.BOLD))
    print(colored("=" * 60, Colors.RED))
    print()
    print("This will DELETE the following resources:")
    print(f"  - Cloud SQL Instance: {colored(config.cloud_sql_instance, Colors.RED)} (ALL DATA WILL BE LOST)")
    print(f"  - GCS Bucket: {colored(config.bucket_name, Colors.RED)} (ALL FILES WILL BE DELETED)")
    print(f"  - Service Account: {colored(config.service_account_name, Colors.RED)}")
    print(f"  - Secrets: {colored('DATABASE_PASSWORD, JWT_SECRET_KEY', Colors.RED)}")
    print()
    print(colored("This action CANNOT be undone!", Colors.RED + Colors.BOLD))
    print()

    try:
        confirmation = input("Type 'DELETE' to confirm: ")
        return confirmation.strip() == "DELETE"
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
        return False


def run_delete_flow(config: ProvisioningConfig, args) -> dict:
    """Run the deletion flow for all resources."""
    results = {}

    print()
    print(colored("DELETING RESOURCES", Colors.RED + Colors.BOLD))
    print("=" * 50)
    print()

    # 1. Delete Secrets (fastest, do first)
    if not args.skip_secrets:
        print("[1/4] Secret Manager Secrets")
        for secret_name in ["DATABASE_PASSWORD", "JWT_SECRET_KEY"]:
            status = delete_secret(config, secret_name)
            results[f"Delete:Secret:{secret_name}"] = status
            print(f"      - {secret_name}: {status_icon(status)}")
        print()
    else:
        print(f"[1/4] Secrets - {status_icon(Status.SKIPPED)}")
        print()

    # 2. Delete Service Account
    if not args.skip_service_account:
        print("[2/4] Service Account")
        status = delete_service_account(config)
        results["Delete:Service Account"] = status
        print(f"      Status: {status_icon(status)}")
        print()
    else:
        print(f"[2/4] Service Account - {status_icon(Status.SKIPPED)}")
        print()

    # 3. Delete GCS Bucket
    if not args.skip_bucket:
        print("[3/4] GCS Bucket")
        status = delete_gcs_bucket(config)
        results["Delete:GCS Bucket"] = status
        print(f"      Status: {status_icon(status)}")
        print()
    else:
        print(f"[3/4] GCS Bucket - {status_icon(Status.SKIPPED)}")
        print()

    # 4. Delete Cloud SQL (slowest, do last)
    if not args.skip_cloudsql:
        print("[4/4] Cloud SQL Instance")
        status = delete_cloud_sql_instance(config)
        results["Delete:Cloud SQL Instance"] = status
        print(f"      Status: {status_icon(status)}")
        print()
    else:
        print(f"[4/4] Cloud SQL - {status_icon(Status.SKIPPED)}")
        print()

    return results


# =============================================================================
# PROVISION FUNCTIONS
# =============================================================================

def provision_cloud_sql_instance(config: ProvisioningConfig) -> Status:
    """Check/create Cloud SQL instance."""
    if config.dry_run:
        print(f"      [DRY RUN] Would check/create instance: {config.cloud_sql_instance}")
        return Status.SKIPPED

    # Check if instance exists
    success, _ = run_gcloud_command([
        "sql", "instances", "describe", config.cloud_sql_instance,
        "--project", config.project_id
    ])

    if success:
        return Status.EXISTS

    # Create instance (no authorized networks - use Cloud SQL Connector for secure access)
    print(f"      Creating Cloud SQL instance (this may take 5-10 minutes)...")
    success, output = run_gcloud_command([
        "sql", "instances", "create", config.cloud_sql_instance,
        "--database-version", "POSTGRES_15",
        "--tier", config.cloud_sql_tier,
        "--region", config.region,
        "--project", config.project_id,
        "--availability-type", "ZONAL",
        "--storage-type", "SSD",
        "--storage-size", "10GB",
        "--storage-auto-increase",
        "--assign-ip",
        "--quiet"
    ], capture_output=False)

    if success:
        return Status.CREATED
    return Status.FAILED


def provision_database(config: ProvisioningConfig) -> Status:
    """Check/create database."""
    if config.dry_run:
        print(f"      [DRY RUN] Would check/create database: {config.database_name}")
        return Status.SKIPPED

    # Check if database exists
    success, output = run_gcloud_command([
        "sql", "databases", "list",
        "--instance", config.cloud_sql_instance,
        "--project", config.project_id,
        "--format=value(name)"
    ])

    if success and config.database_name in output.split('\n'):
        return Status.EXISTS

    # Create database
    success, output = run_gcloud_command([
        "sql", "databases", "create", config.database_name,
        "--instance", config.cloud_sql_instance,
        "--project", config.project_id
    ])

    if success:
        return Status.CREATED
    if "already exists" in output.lower():
        return Status.EXISTS
    return Status.FAILED


def provision_database_user(config: ProvisioningConfig) -> Status:
    """Check/create database user."""
    if config.dry_run:
        print(f"      [DRY RUN] Would check/create user: {config.database_user}")
        return Status.SKIPPED

    # Check if user exists
    success, output = run_gcloud_command([
        "sql", "users", "list",
        "--instance", config.cloud_sql_instance,
        "--project", config.project_id,
        "--format=value(name)"
    ])

    if success and config.database_user in output.split('\n'):
        return Status.EXISTS

    # Create user
    if not config.database_password:
        print(colored("      Warning: No DATABASE_PASSWORD in env file", Colors.YELLOW))
        return Status.FAILED

    success, output = run_gcloud_command([
        "sql", "users", "create", config.database_user,
        "--instance", config.cloud_sql_instance,
        "--project", config.project_id,
        "--password", config.database_password
    ])

    if success:
        return Status.CREATED
    if "already exists" in output.lower():
        return Status.EXISTS
    return Status.FAILED


def provision_gcs_bucket(config: ProvisioningConfig) -> Status:
    """Check/create GCS bucket."""
    if config.dry_run:
        print(f"      [DRY RUN] Would check/create bucket: {config.bucket_name}")
        return Status.SKIPPED

    # Check if bucket exists
    success, _ = run_gcloud_command([
        "storage", "buckets", "describe", f"gs://{config.bucket_name}",
        "--project", config.project_id
    ])

    if success:
        return Status.EXISTS

    # Create bucket
    success, output = run_gcloud_command([
        "storage", "buckets", "create", f"gs://{config.bucket_name}",
        "--project", config.project_id,
        "--location", config.region,
        "--default-storage-class", config.storage_class,
        "--uniform-bucket-level-access"
    ])

    if not success:
        if "already exists" in output.lower() or "409" in output:
            return Status.EXISTS
        return Status.FAILED

    # Enable versioning
    run_gcloud_command([
        "storage", "buckets", "update", f"gs://{config.bucket_name}",
        "--versioning"
    ])

    return Status.CREATED


def provision_service_account(config: ProvisioningConfig) -> Status:
    """Check/create service account."""
    if config.dry_run:
        print(f"      [DRY RUN] Would check/create service account: {config.service_account_name}")
        return Status.SKIPPED

    sa_email = f"{config.service_account_name}@{config.project_id}.iam.gserviceaccount.com"

    # Check if exists
    success, _ = run_gcloud_command([
        "iam", "service-accounts", "describe", sa_email,
        "--project", config.project_id
    ])

    if success:
        return Status.EXISTS

    # Create service account
    success, output = run_gcloud_command([
        "iam", "service-accounts", "create", config.service_account_name,
        "--display-name", "Document Intelligence API Service Account",
        "--project", config.project_id
    ])

    if not success:
        if "already exists" in output.lower():
            return Status.EXISTS
        return Status.FAILED

    # Add IAM roles
    roles = [
        "roles/cloudsql.client",
        "roles/storage.objectAdmin",
        "roles/secretmanager.secretAccessor",
    ]

    for role in roles:
        run_gcloud_command([
            "projects", "add-iam-policy-binding", config.project_id,
            "--member", f"serviceAccount:{sa_email}",
            "--role", role,
            "--quiet"
        ])

    return Status.CREATED


def provision_secret(config: ProvisioningConfig, secret_name: str, secret_value: str) -> Status:
    """Check/create a secret in Secret Manager."""
    if config.dry_run:
        print(f"      [DRY RUN] Would check/create secret: {secret_name}")
        return Status.SKIPPED

    # Check if secret exists
    success, _ = run_gcloud_command([
        "secrets", "describe", secret_name,
        "--project", config.project_id
    ])

    if success:
        return Status.EXISTS

    # Create secret
    success, output = run_gcloud_command([
        "secrets", "create", secret_name,
        "--project", config.project_id,
        "--replication-policy", "automatic"
    ])

    if not success and "already exists" not in output.lower():
        return Status.FAILED

    # Add secret version
    if secret_value:
        cmd = f'echo -n "{secret_value}" | gcloud secrets versions add {secret_name} --data-file=- --project={config.project_id}'
        result = subprocess.run(cmd, shell=True, check=False, capture_output=True)
        if result.returncode != 0:
            return Status.FAILED

    return Status.CREATED


def run_provision_flow(config: ProvisioningConfig, args) -> dict:
    """Run the provisioning flow for all resources."""
    results = {}
    step = 0
    total_steps = 6
    if getattr(args, 'init_tables', False) or getattr(args, 'full_setup', False):
        total_steps += 1
    if getattr(args, 'generate_env', False) or getattr(args, 'full_setup', False):
        total_steps += 1

    print()
    print(colored("PROVISIONING RESOURCES", Colors.GREEN + Colors.BOLD))
    print("=" * 50)
    print()

    # 1. Cloud SQL Instance
    if not args.skip_cloudsql:
        step += 1
        print(f"[{step}/{total_steps}] Cloud SQL Instance")
        status = provision_cloud_sql_instance(config)
        results["Cloud SQL Instance"] = status
        print(f"      Status: {status_icon(status)}")
        print()

        # 2. Database
        step += 1
        print(f"[{step}/{total_steps}] Database")
        if status in [Status.EXISTS, Status.CREATED]:
            status = provision_database(config)
        else:
            status = Status.SKIPPED
        results["Database"] = status
        print(f"      Status: {status_icon(status)}")
        print()

        # 3. Database User
        step += 1
        print(f"[{step}/{total_steps}] Database User")
        if results.get("Database") in [Status.EXISTS, Status.CREATED]:
            status = provision_database_user(config)
        else:
            status = Status.SKIPPED
        results["Database User"] = status
        print(f"      Status: {status_icon(status)}")
        print()
    else:
        step += 3
        results["Cloud SQL Instance"] = Status.SKIPPED
        results["Database"] = Status.SKIPPED
        results["Database User"] = Status.SKIPPED
        print(f"[1-3/{total_steps}] Cloud SQL - {status_icon(Status.SKIPPED)}")
        print()

    # 4. GCS Bucket
    step += 1
    print(f"[{step}/{total_steps}] GCS Bucket")
    if not args.skip_bucket:
        status = provision_gcs_bucket(config)
    else:
        status = Status.SKIPPED
    results["GCS Bucket"] = status
    print(f"      Status: {status_icon(status)}")
    print()

    # 5. Service Account
    step += 1
    print(f"[{step}/{total_steps}] Service Account")
    if not args.skip_service_account:
        status = provision_service_account(config)
    else:
        status = Status.SKIPPED
    results["Service Account"] = status
    print(f"      Status: {status_icon(status)}")
    print()

    # 6. Secret Manager
    step += 1
    print(f"[{step}/{total_steps}] Secret Manager Secrets")
    if not args.skip_secrets:
        secrets_to_create = [
            ("DATABASE_PASSWORD", config.database_password),
            ("JWT_SECRET_KEY", config.jwt_secret_key),
        ]

        for secret_name, secret_value in secrets_to_create:
            status = provision_secret(config, secret_name, secret_value)
            results[f"Secret:{secret_name}"] = status
            print(f"      - {secret_name}: {status_icon(status)}")
    else:
        print(f"      Status: {status_icon(Status.SKIPPED)}")
    print()

    # 7. Database Tables (conditional)
    if getattr(args, 'init_tables', False) or getattr(args, 'full_setup', False):
        step += 1
        print(f"[{step}/{total_steps}] Database Tables")
        # Only init tables if Cloud SQL was successful
        if results.get("Database") in [Status.EXISTS, Status.CREATED]:
            status = init_database_tables(config)
        else:
            print("      Skipped: Cloud SQL database not available")
            status = Status.SKIPPED
        results["Database Tables"] = status
        print(f"      Status: {status_icon(status)}")
        print()

    # 8. Generate Environment File (conditional)
    if getattr(args, 'generate_env', False) or getattr(args, 'full_setup', False):
        step += 1
        print(f"[{step}/{total_steps}] Environment File")
        status = generate_environment_file(config, getattr(args, 'env_output', '.env'))
        results["Environment File"] = status
        print(f"      Status: {status_icon(status)}")
        print()

    return results


def init_database_tables(config: ProvisioningConfig) -> Status:
    """Initialize database tables by calling init_database.py."""
    import os

    if config.dry_run:
        print("      [DRY RUN] Would initialize database tables")
        return Status.SKIPPED

    print("      Running database table initialization...")
    try:
        env = os.environ.copy()
        env["ENV_FILE"] = config.env_file

        result = subprocess.run(
            [sys.executable, str(project_root / "scripts" / "init_database.py")],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(project_root)
        )
        if result.returncode == 0:
            print("      Tables created successfully")
            return Status.CREATED
        else:
            error_msg = result.stderr[:200] if result.stderr else "Unknown error"
            print(f"      Error: {error_msg}")
            return Status.FAILED
    except Exception as e:
        print(f"      Exception: {e}")
        return Status.FAILED


def generate_environment_file(config: ProvisioningConfig, output_path: str) -> Status:
    """Generate .env file by calling generate_env.py."""
    if config.dry_run:
        print(f"      [DRY RUN] Would generate {output_path}")
        return Status.SKIPPED

    print(f"      Generating environment file: {output_path}")
    try:
        cmd = [
            sys.executable,
            str(project_root / "scripts" / "generate_env.py"),
            "--output", output_path,
            "--project", config.project_id,
            "--include-secrets",
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(project_root)
        )
        if result.returncode == 0:
            print(f"      Environment file generated: {output_path}")
            return Status.CREATED
        else:
            error_msg = result.stderr[:200] if result.stderr else "Unknown error"
            print(f"      Error: {error_msg}")
            return Status.FAILED
    except Exception as e:
        print(f"      Exception: {e}")
        return Status.FAILED


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Provision GCP resources from .env configuration"
    )
    parser.add_argument(
        "--env-file",
        default=".env.production",
        help="Path to environment file (default: .env.production)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview actions without executing"
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Delete existing resources before creating (DESTRUCTIVE)"
    )
    parser.add_argument(
        "--delete-only",
        action="store_true",
        help="Only delete resources, don't recreate"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompts (use with --delete)"
    )
    parser.add_argument(
        "--skip-cloudsql",
        action="store_true",
        help="Skip Cloud SQL setup"
    )
    parser.add_argument(
        "--skip-bucket",
        action="store_true",
        help="Skip GCS bucket setup"
    )
    parser.add_argument(
        "--skip-service-account",
        action="store_true",
        help="Skip service account setup"
    )
    parser.add_argument(
        "--skip-secrets",
        action="store_true",
        help="Skip Secret Manager setup"
    )
    parser.add_argument(
        "--init-tables",
        action="store_true",
        help="Initialize database tables after provisioning"
    )
    parser.add_argument(
        "--generate-env",
        action="store_true",
        help="Generate .env file from provisioned resources"
    )
    parser.add_argument(
        "--env-output",
        default=".env",
        help="Output path for generated .env file (default: .env)"
    )
    parser.add_argument(
        "--full-setup",
        action="store_true",
        help="Run complete setup: provision + init-tables + generate-env"
    )

    args = parser.parse_args()

    # Handle --full-setup convenience flag
    if args.full_setup:
        args.init_tables = True
        args.generate_env = True

    # Header
    print()
    print("=" * 50)
    print(colored("GCP Resource Provisioning", Colors.BOLD))
    print("=" * 50)
    print(f"Reading configuration from: {colored(args.env_file, Colors.BLUE)}")

    # Check gcloud authentication
    print("\nChecking gcloud authentication...", end=" ")
    if not check_gcloud_auth():
        print(colored("FAILED", Colors.RED))
        print("\nPlease authenticate with:")
        print("  gcloud auth login")
        print("  gcloud auth application-default login")
        sys.exit(1)
    print(colored("OK", Colors.GREEN))

    # Load configuration
    config = load_config_from_env(args.env_file)
    config.dry_run = args.dry_run

    display_config(config)

    if config.dry_run:
        print(colored("[DRY RUN MODE - No changes will be made]\n", Colors.YELLOW))

    all_results = {}

    # Handle delete flow
    if args.delete or args.delete_only:
        # Confirm deletion unless --force is used
        if not args.force and not config.dry_run:
            if not confirm_delete(config):
                print("\nDeletion cancelled.")
                sys.exit(0)

        delete_results = run_delete_flow(config, args)
        all_results.update(delete_results)

        # If delete-only, show summary and exit
        if args.delete_only:
            print("=" * 50)
            print(colored("DELETION SUMMARY", Colors.BOLD))
            print("=" * 50)

            failed = [k for k, v in all_results.items() if v == Status.FAILED]
            if not failed:
                print(colored("\nAll resources deleted successfully! ✓\n", Colors.GREEN))
                sys.exit(0)
            else:
                print(colored(f"\nSome deletions failed:", Colors.RED))
                for item in failed:
                    print(f"  - {item}")
                print()
                sys.exit(1)

    # Run provisioning flow
    provision_results = run_provision_flow(config, args)
    all_results.update(provision_results)

    # Verification Summary
    print("=" * 50)
    print(colored("VERIFICATION SUMMARY", Colors.BOLD))
    print("=" * 50)

    # Filter out delete results for final summary
    provision_only = {k: v for k, v in all_results.items() if not k.startswith("Delete:")}
    failed = [k for k, v in provision_only.items() if v in [Status.FAILED, Status.MISSING]]

    if not failed:
        print(colored("\nAll resources verified successfully! ✓\n", Colors.GREEN))
        sys.exit(0)
    else:
        print(colored(f"\nSome resources failed:", Colors.RED))
        for item in failed:
            print(f"  - {item}")
        print()
        sys.exit(1)


if __name__ == "__main__":
    main()
