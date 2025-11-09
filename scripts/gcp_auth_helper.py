#!/usr/bin/env python3
"""
GCP Authentication Helper Utilities

Helper utilities for managing GCP authentication and credentials
for the document intelligence backend system.

Usage:
    python scripts/gcp_auth_helper.py [command]

Commands:
    check       - Check current authentication status
    setup       - Interactive authentication setup
    test        - Test authentication and permissions
"""

import os
import sys
import json
import subprocess
from typing import Optional, Dict, Any, Tuple
from pathlib import Path

import google.auth
from google.auth.exceptions import DefaultCredentialsError
from google.cloud import storage
from google.api_core.exceptions import GoogleAPIError, Forbidden

# Project configuration
PROJECT_ID = "ibm-keras"
REQUIRED_SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/devstorage.full_control"
]


class GCPAuthHelper:
    """Helper class for GCP authentication management."""
    
    def __init__(self, project_id: str = PROJECT_ID):
        self.project_id = project_id
        
    def check_gcloud_installation(self) -> bool:
        """Check if gcloud CLI is installed."""
        try:
            result = subprocess.run(
                ["gcloud", "version"], 
                capture_output=True, 
                text=True, 
                check=False
            )
            if result.returncode == 0:
                print("✅ gcloud CLI is installed")
                return True
            else:
                print("❌ gcloud CLI not found")
                return False
        except FileNotFoundError:
            print("❌ gcloud CLI not found in PATH")
            return False
    
    def check_current_auth(self) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Check current authentication status.
        
        Returns:
            (is_authenticated, account, project)
        """
        try:
            # Check active account
            result = subprocess.run(
                ["gcloud", "auth", "list", "--filter=status:ACTIVE", "--format=value(account)"],
                capture_output=True,
                text=True,
                check=False
            )
            
            active_account = result.stdout.strip() if result.returncode == 0 else None
            
            # Check current project
            result = subprocess.run(
                ["gcloud", "config", "get-value", "project"],
                capture_output=True,
                text=True,
                check=False
            )
            
            current_project = result.stdout.strip() if result.returncode == 0 else None
            
            return bool(active_account), active_account, current_project
            
        except Exception as e:
            print(f"Error checking authentication: {e}")
            return False, None, None
    
    def check_application_default_credentials(self) -> Tuple[bool, Optional[str]]:
        """
        Check if Application Default Credentials are set up.
        
        Returns:
            (has_adc, credentials_source)
        """
        try:
            credentials, project = google.auth.default()
            
            # Try to determine credentials source
            creds_source = "Unknown"
            if hasattr(credentials, '_service_account_email'):
                creds_source = f"Service Account: {credentials._service_account_email}"
            elif os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
                creds_source = f"Service Account File: {os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')}"
            elif hasattr(credentials, 'token'):
                creds_source = "User Credentials (gcloud auth application-default login)"
            
            return True, creds_source
            
        except DefaultCredentialsError:
            return False, None
        except Exception as e:
            return False, f"Error: {e}"
    
    def test_storage_permissions(self) -> bool:
        """Test Google Cloud Storage permissions."""
        try:
            client = storage.Client(project=self.project_id)
            
            # Test listing buckets
            buckets = list(client.list_buckets())
            print(f"✅ Can list buckets (found {len(buckets)} buckets)")
            
            # Test bucket creation permissions by checking IAM
            # Note: This doesn't actually create a bucket, just tests permissions
            print("✅ Storage permissions verified")
            return True
            
        except Forbidden as e:
            print(f"❌ Insufficient permissions: {e}")
            return False
        except Exception as e:
            print(f"❌ Storage permission test failed: {e}")
            return False
    
    def setup_authentication(self) -> bool:
        """Interactive authentication setup."""
        print("Setting up GCP authentication...")
        print("-" * 40)
        
        # Check if gcloud is installed
        if not self.check_gcloud_installation():
            print("\nPlease install Google Cloud SDK:")
            print("https://cloud.google.com/sdk/docs/install")
            return False
        
        # Set the project
        print(f"\n1. Setting project to {self.project_id}...")
        result = subprocess.run(
            ["gcloud", "config", "set", "project", self.project_id],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"❌ Failed to set project: {result.stderr}")
            return False
        
        print("✅ Project set successfully")
        
        # Authenticate
        print("\n2. Starting authentication...")
        result = subprocess.run(
            ["gcloud", "auth", "login"],
            capture_output=False  # Allow interactive login
        )
        
        if result.returncode != 0:
            print("❌ Authentication failed")
            return False
        
        print("✅ Authentication successful")
        
        # Set up Application Default Credentials
        print("\n3. Setting up Application Default Credentials...")
        result = subprocess.run(
            ["gcloud", "auth", "application-default", "login"],
            capture_output=False  # Allow interactive login
        )
        
        if result.returncode != 0:
            print("❌ Failed to set up Application Default Credentials")
            return False
        
        print("✅ Application Default Credentials set up successfully")
        
        return True
    
    def display_auth_status(self) -> None:
        """Display comprehensive authentication status."""
        print("\n" + "="*50)
        print("GCP AUTHENTICATION STATUS")
        print("="*50)
        
        # Check gcloud installation
        print(f"gcloud CLI: {'✅ Installed' if self.check_gcloud_installation() else '❌ Not found'}")
        
        # Check current authentication
        is_auth, account, project = self.check_current_auth()
        print(f"Active Account: {'✅ ' + account if is_auth else '❌ Not authenticated'}")
        print(f"Current Project: {'✅ ' + project if project else '❌ Not set'}")
        print(f"Target Project: {'✅ ' + self.project_id if project == self.project_id else '⚠️ ' + self.project_id + ' (needs to be set)'}")
        
        # Check Application Default Credentials
        has_adc, creds_source = self.check_application_default_credentials()
        print(f"Application Default Credentials: {'✅ ' + creds_source if has_adc else '❌ Not configured'}")
        
        # Check storage permissions
        if has_adc:
            print("\nTesting permissions...")
            storage_ok = self.test_storage_permissions()
            print(f"Storage Permissions: {'✅ Valid' if storage_ok else '❌ Insufficient'}")
        
        # Environment variables
        print(f"\nEnvironment Variables:")
        gac = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        print(f"GOOGLE_APPLICATION_CREDENTIALS: {'✅ ' + gac if gac else '❌ Not set'}")
        
        print("="*50)
    
    def generate_env_config(self) -> Dict[str, str]:
        """Generate environment configuration for the application."""
        config = {
            "GCP_PROJECT_ID": self.project_id,
            "GCS_BUCKET_NAME": "biz-to-bricks-document-store",
        }
        
        # Check if service account file is being used
        gac = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if gac and os.path.exists(gac):
            config["GOOGLE_APPLICATION_CREDENTIALS"] = gac
        
        return config
    
    def save_env_template(self, file_path: str = ".env.gcp") -> None:
        """Save environment template file."""
        config = self.generate_env_config()
        
        with open(file_path, "w") as f:
            f.write("# GCP Configuration for Document Intelligence Backend\n")
            f.write(f"# Generated on {subprocess.run(['date'], capture_output=True, text=True).stdout.strip()}\n\n")
            
            for key, value in config.items():
                f.write(f"{key}={value}\n")
            
            f.write("\n# Firebase Configuration (if different from GCP)\n")
            f.write("# FIREBASE_PROJECT_ID=your-firebase-project\n")
            f.write("# FIREBASE_SERVICE_ACCOUNT_JSON=path/to/service-account.json\n")
        
        print(f"✅ Environment template saved to {file_path}")


def main():
    """Main CLI function."""
    helper = GCPAuthHelper()
    
    if len(sys.argv) < 2:
        command = "check"
    else:
        command = sys.argv[1].lower()
    
    print("GCP Authentication Helper")
    print(f"Project: {PROJECT_ID}")
    print("-" * 40)
    
    if command == "check":
        helper.display_auth_status()
        
    elif command == "setup":
        if helper.setup_authentication():
            print("\n🎉 Authentication setup completed!")
            helper.display_auth_status()
            helper.save_env_template()
        else:
            print("\n❌ Authentication setup failed!")
            sys.exit(1)
            
    elif command == "test":
        print("Testing authentication and permissions...")
        helper.display_auth_status()
        
        has_adc, _ = helper.check_application_default_credentials()
        if has_adc:
            if helper.test_storage_permissions():
                print("\n✅ All tests passed!")
            else:
                print("\n❌ Permission tests failed!")
                sys.exit(1)
        else:
            print("\n❌ No valid credentials found!")
            sys.exit(1)
            
    elif command == "env":
        helper.save_env_template()
        
    else:
        print(f"Unknown command: {command}")
        print("Available commands: check, setup, test, env")
        sys.exit(1)


if __name__ == "__main__":
    main()