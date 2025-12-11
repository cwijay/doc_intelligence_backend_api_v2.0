#!/usr/bin/env python3
"""
GCP Bucket Setup Script for Document Intelligence Backend

This script creates and configures the required GCS bucket for the document intelligence system.

Usage:
    python setup_gcp_bucket.py

    # With custom configuration
    GCP_PROJECT_ID=my-project GCS_BUCKET_NAME=my-bucket python setup_gcp_bucket.py

Environment Variables:
    GCP_PROJECT_ID - Your GCP project ID
    GCS_BUCKET_NAME - Name for the GCS bucket
    GCS_REGION - Region (default: us-central1)

Requirements:
    - Google Cloud SDK installed and authenticated
    - Required permissions to create buckets
"""

import os
import sys
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path

from google.cloud import storage
from google.auth.exceptions import DefaultCredentialsError
from google.api_core.exceptions import GoogleAPIError, Conflict, NotFound
import google.auth

# Load environment variables from .env if available
from dotenv import load_dotenv
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration from environment variables with defaults
PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "")
BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", "")
REGION = os.environ.get("GCS_REGION", "us-central1")
STORAGE_CLASS = "STANDARD"

# Required folder structure prefixes for testing
TEST_FOLDERS = [
    "test-org/original/test-folder/",
    "test-org/parsed/test-folder/",
    "test-org/bm-25/test-folder/"
]


class GCPBucketSetup:
    """GCP Bucket setup and configuration utility."""
    
    def __init__(self, project_id: str, bucket_name: str):
        self.project_id = project_id
        self.bucket_name = bucket_name
        self.client: Optional[storage.Client] = None
        self.bucket: Optional[storage.Bucket] = None
        
    def authenticate(self) -> bool:
        """
        Authenticate with Google Cloud using default credentials.
        Returns True if successful, False otherwise.
        """
        try:
            # Try to get default credentials
            credentials, project = google.auth.default()
            
            if project != self.project_id:
                logger.warning(f"Default project is '{project}', but we need '{self.project_id}'")
                logger.info("Using explicit project ID for client initialization")
            
            # Initialize storage client with explicit project
            self.client = storage.Client(project=self.project_id, credentials=credentials)
            
            logger.info(f"Successfully authenticated with project: {self.project_id}")
            return True
            
        except DefaultCredentialsError as e:
            logger.error(f"Authentication failed: {e}")
            logger.error("Please run 'gcloud auth application-default login' to authenticate")
            return False
        except Exception as e:
            logger.error(f"Unexpected authentication error: {e}")
            return False

    def check_bucket_exists(self) -> bool:
        """Check if the bucket already exists."""
        try:
            self.bucket = self.client.bucket(self.bucket_name)
            self.bucket.reload()  # This will raise NotFound if bucket doesn't exist
            logger.info(f"Bucket '{self.bucket_name}' already exists")
            return True
        except NotFound:
            logger.info(f"Bucket '{self.bucket_name}' does not exist")
            return False
        except Exception as e:
            logger.error(f"Error checking bucket existence: {e}")
            return False

    def create_bucket(self, region: str = REGION, storage_class: str = STORAGE_CLASS) -> bool:
        """Create the GCS bucket with specified configuration."""
        try:
            # Create bucket with configuration
            self.bucket = self.client.bucket(self.bucket_name)
            self.bucket.location = region
            self.bucket.storage_class = storage_class
            
            # Create the bucket
            self.bucket = self.client.create_bucket(self.bucket, location=region)
            
            logger.info(f"Created bucket '{self.bucket_name}' in region '{region}'")
            logger.info(f"Storage class: {storage_class}")
            
            return True
            
        except Conflict:
            logger.warning(f"Bucket '{self.bucket_name}' already exists globally")
            # Try to get the existing bucket
            try:
                self.bucket = self.client.bucket(self.bucket_name)
                self.bucket.reload()
                logger.info("Using existing bucket")
                return True
            except Exception as e:
                logger.error(f"Cannot access existing bucket: {e}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to create bucket: {e}")
            return False

    def configure_bucket_permissions(self) -> bool:
        """Configure bucket permissions and settings."""
        try:
            if not self.bucket:
                logger.error("Bucket not initialized")
                return False
            
            # Enable versioning (recommended for document storage)
            self.bucket.versioning_enabled = True
            self.bucket.patch()
            
            logger.info("Enabled versioning on bucket")
            
            # Set lifecycle rules to manage old versions
            rule = {
                "action": {"type": "Delete"},
                "condition": {
                    "numNewerVersions": 5  # Keep last 5 versions
                }
            }
            
            self.bucket.lifecycle_rules = [rule]
            self.bucket.patch()
            
            logger.info("Configured lifecycle rules")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to configure bucket permissions: {e}")
            return False

    def create_folder_structure_test(self) -> bool:
        """Create test folder structure to verify everything works."""
        try:
            if not self.bucket:
                logger.error("Bucket not initialized")
                return False
            
            logger.info("Creating test folder structure...")
            
            for folder_path in TEST_FOLDERS:
                # Create placeholder object for folder
                blob_name = f"{folder_path}.folder_placeholder"
                blob = self.bucket.blob(blob_name)
                
                # Upload empty content to create the folder structure
                blob.upload_from_string(
                    f"Placeholder for folder: {folder_path}\nCreated: {datetime.utcnow().isoformat()}",
                    content_type="text/plain"
                )
                
                logger.info(f"Created folder: gs://{self.bucket_name}/{folder_path}")
            
            logger.info("Test folder structure created successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create test folder structure: {e}")
            return False

    def verify_setup(self) -> bool:
        """Verify the bucket setup is working correctly."""
        try:
            if not self.bucket:
                logger.error("Bucket not initialized")
                return False
            
            logger.info("Verifying bucket setup...")
            
            # Test bucket access
            self.bucket.reload()
            logger.info(f"✓ Bucket access verified")
            
            # List test objects
            blobs = list(self.bucket.list_blobs(prefix="test-org/"))
            logger.info(f"✓ Found {len(blobs)} test objects")
            
            # Test upload/download
            test_blob_name = "test-org/original/test-upload.txt"
            test_content = f"Test upload at {datetime.utcnow().isoformat()}"
            
            blob = self.bucket.blob(test_blob_name)
            blob.upload_from_string(test_content, content_type="text/plain")
            
            # Download to verify
            downloaded_content = blob.download_as_text()
            if downloaded_content == test_content:
                logger.info("✓ Upload/download test successful")
                
                # Clean up test file
                blob.delete()
                logger.info("✓ Test cleanup successful")
            else:
                logger.error("Upload/download test failed - content mismatch")
                return False
            
            logger.info("Bucket setup verification completed successfully!")
            return True
            
        except Exception as e:
            logger.error(f"Verification failed: {e}")
            return False

    def cleanup_test_data(self) -> bool:
        """Clean up test folder structure."""
        try:
            if not self.bucket:
                logger.error("Bucket not initialized")
                return False
            
            logger.info("Cleaning up test data...")
            
            # Delete all test objects
            blobs = list(self.bucket.list_blobs(prefix="test-org/"))
            for blob in blobs:
                blob.delete()
                logger.info(f"Deleted: gs://{self.bucket_name}/{blob.name}")
            
            logger.info("Test data cleanup completed")
            return True
            
        except Exception as e:
            logger.error(f"Failed to clean up test data: {e}")
            return False

    def display_summary(self) -> None:
        """Display setup summary and next steps."""
        logger.info("=" * 60)
        logger.info("GCP BUCKET SETUP SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Project ID: {self.project_id}")
        logger.info(f"Bucket Name: {self.bucket_name}")
        logger.info(f"Bucket URI: gs://{self.bucket_name}")
        logger.info(f"Region: {self.bucket.location if self.bucket else 'Unknown'}")
        logger.info(f"Storage Class: {self.bucket.storage_class if self.bucket else 'Unknown'}")
        logger.info("Folder Structure:")
        logger.info("- <organization_name>/original/<folder_path>/")
        logger.info("- <organization_name>/parsed/<folder_path>/")
        logger.info("- <organization_name>/bm-25/<folder_path>/")
        logger.info("Next Steps:")
        logger.info("1. Update your .env file with:")
        logger.info(f"   GCP_PROJECT_ID={self.project_id}")
        logger.info(f"   GCS_BUCKET_NAME={self.bucket_name}")
        logger.info("2. Ensure GOOGLE_APPLICATION_CREDENTIALS is set")
        logger.info("3. Test the folder management API endpoints")
        logger.info("=" * 60)


def main():
    """Main setup function."""
    global PROJECT_ID, BUCKET_NAME, REGION

    import argparse

    parser = argparse.ArgumentParser(
        description="Setup GCS bucket for Document Intelligence API"
    )
    parser.add_argument(
        "--project",
        help="GCP Project ID (overrides environment)"
    )
    parser.add_argument(
        "--bucket",
        help="Bucket name (overrides environment)"
    )
    parser.add_argument(
        "--region",
        default="us-central1",
        help="Region (default: us-central1)"
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Run without prompts (for CI/CD)"
    )
    parser.add_argument(
        "--skip-test",
        action="store_true",
        help="Skip test folder creation and verification"
    )

    args = parser.parse_args()

    logger.info("GCP Bucket Setup for Document Intelligence Backend")
    logger.info("-" * 60)

    # Get configuration from args, environment, or prompt
    if args.project:
        PROJECT_ID = args.project
    elif not PROJECT_ID:
        if args.non_interactive:
            logger.error("GCP_PROJECT_ID not set and non-interactive mode enabled")
            sys.exit(1)
        PROJECT_ID = input("Enter GCP Project ID: ").strip()
        if not PROJECT_ID:
            logger.error("Project ID is required")
            sys.exit(1)

    if args.bucket:
        BUCKET_NAME = args.bucket
    elif not BUCKET_NAME:
        default_bucket = f"{PROJECT_ID}-document-store"
        if args.non_interactive:
            BUCKET_NAME = default_bucket
        else:
            BUCKET_NAME = input(f"Enter bucket name [{default_bucket}]: ").strip() or default_bucket

    if args.region:
        REGION = args.region

    logger.info(f"Project: {PROJECT_ID}")
    logger.info(f"Bucket: {BUCKET_NAME}")
    logger.info(f"Region: {REGION}")
    logger.info("-" * 60)

    # Initialize setup
    setup = GCPBucketSetup(PROJECT_ID, BUCKET_NAME)

    # Step 1: Authenticate
    logger.info("1. Authenticating with Google Cloud...")
    if not setup.authenticate():
        logger.error("Authentication failed. Please check your credentials.")
        sys.exit(1)
    logger.info("Authentication successful")

    # Step 2: Check if bucket exists
    logger.info("2. Checking if bucket exists...")
    bucket_exists = setup.check_bucket_exists()

    # Step 3: Create bucket if needed
    if not bucket_exists:
        logger.info("3. Creating bucket...")
        if not setup.create_bucket():
            logger.error("Bucket creation failed.")
            sys.exit(1)
        logger.info("Bucket created successfully")
    else:
        logger.info("3. Using existing bucket...")
        setup.bucket = setup.client.bucket(BUCKET_NAME)

    # Step 4: Configure bucket
    logger.info("4. Configuring bucket permissions...")
    if not setup.configure_bucket_permissions():
        logger.warning("Bucket configuration failed, but continuing...")
    else:
        logger.info("Bucket configured successfully")

    # Step 5: Test folder structure (skip if --skip-test)
    if not args.skip_test:
        logger.info("5. Creating test folder structure...")
        if not setup.create_folder_structure_test():
            logger.error("Test folder creation failed.")
            sys.exit(1)
        logger.info("Test folder structure created")

        # Step 6: Verify setup
        logger.info("6. Verifying setup...")
        if not setup.verify_setup():
            logger.error("Setup verification failed.")
            sys.exit(1)
        logger.info("Setup verification successful")

        # Step 7: Cleanup test data
        logger.info("7. Cleaning up test data...")
        if not setup.cleanup_test_data():
            logger.warning("Test data cleanup failed")
        else:
            logger.info("Test data cleaned up")
    else:
        logger.info("5-7. Skipping test folder creation and verification (--skip-test)")

    # Display summary
    setup.display_summary()

    logger.info("GCP bucket setup completed successfully!")
    logger.info("Your document intelligence backend is now ready to use GCS storage.")


if __name__ == "__main__":
    main()