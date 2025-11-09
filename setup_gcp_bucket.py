#!/usr/bin/env python3
"""
GCP Bucket Setup Script for Document Intelligence Backend

This script creates and configures the required GCS bucket for the document intelligence system.
Based on patterns from: https://github.com/cwijayasundara/biz_to_bricks_v3/tree/main/server

Usage:
    python setup_gcp_bucket.py

Requirements:
    - Google Cloud SDK installed and authenticated
    - Project ID: ibm-keras
    - Required permissions to create buckets
"""

import os
import sys
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from google.cloud import storage
from google.auth.exceptions import DefaultCredentialsError
from google.api_core.exceptions import GoogleAPIError, Conflict, NotFound
import google.auth

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
PROJECT_ID = "ibm-keras"
BUCKET_NAME = "biz-to-bricks-document-store"
REGION = "us-central1"  # Change as needed
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
        print("\n" + "="*60)
        print("GCP BUCKET SETUP SUMMARY")
        print("="*60)
        print(f"Project ID: {self.project_id}")
        print(f"Bucket Name: {self.bucket_name}")
        print(f"Bucket URI: gs://{self.bucket_name}")
        print(f"Region: {self.bucket.location if self.bucket else 'Unknown'}")
        print(f"Storage Class: {self.bucket.storage_class if self.bucket else 'Unknown'}")
        print("\nFolder Structure:")
        print("- <organization_name>/original/<folder_path>/")
        print("- <organization_name>/parsed/<folder_path>/")
        print("- <organization_name>/bm-25/<folder_path>/")
        print("\nNext Steps:")
        print("1. Update your .env file with:")
        print(f"   GCP_PROJECT_ID={self.project_id}")
        print(f"   GCS_BUCKET_NAME={self.bucket_name}")
        print("2. Ensure GOOGLE_APPLICATION_CREDENTIALS is set")
        print("3. Test the folder management API endpoints")
        print("="*60)


def main():
    """Main setup function."""
    print("GCP Bucket Setup for Document Intelligence Backend")
    print(f"Project: {PROJECT_ID}")
    print(f"Bucket: {BUCKET_NAME}")
    print("-" * 60)
    
    # Initialize setup
    setup = GCPBucketSetup(PROJECT_ID, BUCKET_NAME)
    
    # Step 1: Authenticate
    print("\n1. Authenticating with Google Cloud...")
    if not setup.authenticate():
        print("❌ Authentication failed. Please check your credentials.")
        sys.exit(1)
    print("✅ Authentication successful")
    
    # Step 2: Check if bucket exists
    print("\n2. Checking if bucket exists...")
    bucket_exists = setup.check_bucket_exists()
    
    # Step 3: Create bucket if needed
    if not bucket_exists:
        print("\n3. Creating bucket...")
        if not setup.create_bucket():
            print("❌ Bucket creation failed.")
            sys.exit(1)
        print("✅ Bucket created successfully")
    else:
        print("\n3. Using existing bucket...")
        setup.bucket = setup.client.bucket(BUCKET_NAME)
    
    # Step 4: Configure bucket
    print("\n4. Configuring bucket permissions...")
    if not setup.configure_bucket_permissions():
        print("⚠️ Warning: Bucket configuration failed, but continuing...")
    else:
        print("✅ Bucket configured successfully")
    
    # Step 5: Test folder structure
    print("\n5. Creating test folder structure...")
    if not setup.create_folder_structure_test():
        print("❌ Test folder creation failed.")
        sys.exit(1)
    print("✅ Test folder structure created")
    
    # Step 6: Verify setup
    print("\n6. Verifying setup...")
    if not setup.verify_setup():
        print("❌ Setup verification failed.")
        sys.exit(1)
    print("✅ Setup verification successful")
    
    # Step 7: Cleanup test data
    print("\n7. Cleaning up test data...")
    if not setup.cleanup_test_data():
        print("⚠️ Warning: Test data cleanup failed")
    else:
        print("✅ Test data cleaned up")
    
    # Display summary
    setup.display_summary()
    
    print("\n🎉 GCP bucket setup completed successfully!")
    print("Your document intelligence backend is now ready to use GCS storage.")


if __name__ == "__main__":
    main()