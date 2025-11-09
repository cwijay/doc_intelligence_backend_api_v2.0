#!/usr/bin/env python3
"""
GCS Setup Verification Script

Verifies that the GCS bucket and folder management system is working correctly
for the document intelligence backend.

Usage:
    python scripts/verify_gcs_setup.py

This script will:
1. Check GCS client initialization
2. Verify bucket access
3. Test folder structure creation
4. Validate organization name lookup
5. Test all folder operations (create, move, delete)
"""

import os
import sys
import asyncio
import logging
from typing import Dict, Any, List
from datetime import datetime
from pathlib import Path

# Add the app directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings
from app.core.gcs_client import gcs_client, GCSClientError
from app.core.firebase_client import firebase_manager
from app.services.org_service import organization_service, OrganizationNotFoundError
from app.services.folder_service import folder_service, FolderValidationError
from app.models.schemas import OrganizationCreate, FolderCreate
from app.models.organization import PlanType

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class GCSVerification:
    """GCS setup verification utility."""
    
    def __init__(self):
        self.test_org_id: str = None
        self.test_folder_id: str = None
        self.cleanup_items: List[Dict[str, Any]] = []
    
    async def check_configuration(self) -> bool:
        """Check configuration settings."""
        logger.info("Checking configuration...")
        
        issues = []
        
        # Check required settings
        if not settings.GCP_PROJECT_ID:
            issues.append("GCP_PROJECT_ID not set")
        else:
            logger.info(f"✅ GCP_PROJECT_ID: {settings.GCP_PROJECT_ID}")
        
        if not settings.GCS_BUCKET_NAME:
            issues.append("GCS_BUCKET_NAME not set")
        else:
            logger.info(f"✅ GCS_BUCKET_NAME: {settings.GCS_BUCKET_NAME}")
        
        # Check authentication
        gac = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if not gac and not settings.GOOGLE_APPLICATION_CREDENTIALS:
            issues.append("GOOGLE_APPLICATION_CREDENTIALS not set")
        else:
            logger.info("✅ Authentication credentials configured")
        
        if issues:
            logger.error("Configuration issues found:")
            for issue in issues:
                logger.error(f"  - {issue}")
            return False
        
        logger.info("✅ Configuration check passed")
        return True
    
    def check_gcs_client_initialization(self) -> bool:
        """Check GCS client initialization."""
        logger.info("Checking GCS client initialization...")
        
        if not gcs_client.is_initialized:
            error = gcs_client.initialization_error or "Unknown error"
            logger.error(f"❌ GCS client not initialized: {error}")
            return False
        
        logger.info("✅ GCS client initialized successfully")
        
        # Test health check
        if gcs_client.health_check():
            logger.info("✅ GCS health check passed")
            return True
        else:
            logger.error("❌ GCS health check failed")
            return False
    
    async def check_firebase_initialization(self) -> bool:
        """Check Firebase initialization."""
        logger.info("Checking Firebase initialization...")
        
        try:
            # Test Firebase connection
            if not firebase_manager.is_initialized:
                await firebase_manager.initialize()
            
            if firebase_manager.is_initialized:
                logger.info("✅ Firebase initialized successfully")
                return True
            else:
                logger.error("❌ Firebase not initialized")
                return False
                
        except Exception as e:
            logger.error(f"❌ Firebase initialization failed: {e}")
            return False
    
    async def create_test_organization(self) -> bool:
        """Create a test organization for verification."""
        logger.info("Creating test organization...")
        
        try:
            org_data = OrganizationCreate(
                name=f"test-org-verification-{int(datetime.utcnow().timestamp())}",
                domain="test-verification.example.com",
                plan_type=PlanType.FREE,
                settings={}
            )
            
            org_response = await organization_service.create_organization(org_data)
            self.test_org_id = org_response.id
            
            # Add to cleanup list
            self.cleanup_items.append({
                "type": "organization",
                "id": org_response.id,
                "name": org_response.name
            })
            
            logger.info(f"✅ Test organization created: {org_response.name} (ID: {org_response.id})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to create test organization: {e}")
            return False
    
    async def test_organization_name_lookup(self) -> bool:
        """Test organization name lookup functionality."""
        logger.info("Testing organization name lookup...")
        
        if not self.test_org_id:
            logger.error("No test organization ID available")
            return False
        
        try:
            org_response = await organization_service.get_organization(self.test_org_id)
            logger.info(f"✅ Organization name lookup successful: {org_response.name}")
            return True
            
        except OrganizationNotFoundError:
            logger.error("❌ Test organization not found")
            return False
        except Exception as e:
            logger.error(f"❌ Organization name lookup failed: {e}")
            return False
    
    async def test_folder_creation_with_gcs(self) -> bool:
        """Test folder creation with GCS integration."""
        logger.info("Testing folder creation with GCS integration...")
        
        if not self.test_org_id:
            logger.error("No test organization ID available")
            return False
        
        try:
            folder_data = FolderCreate(
                name=f"test-folder-{int(datetime.utcnow().timestamp())}",
                parent_folder_id=None
            )
            
            folder_response = await folder_service.create_folder(
                self.test_org_id,
                folder_data,
                "test-user-id"
            )
            
            self.test_folder_id = folder_response.id
            
            # Add to cleanup list
            self.cleanup_items.append({
                "type": "folder",
                "org_id": self.test_org_id,
                "id": folder_response.id,
                "name": folder_response.name
            })
            
            logger.info(f"✅ Folder created successfully: {folder_response.name} (ID: {folder_response.id})")
            logger.info(f"   Path: {folder_response.path}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Folder creation failed: {e}")
            return False
    
    def test_gcs_folder_structure(self) -> bool:
        """Test GCS folder structure creation directly."""
        logger.info("Testing GCS folder structure creation...")
        
        if not gcs_client.is_initialized:
            logger.error("GCS client not initialized")
            return False
        
        try:
            test_org_name = "test-verification-org"
            test_folder_path = f"test-folder-{int(datetime.utcnow().timestamp())}"
            
            # Create folder structure
            result = gcs_client.create_folder_structure(test_org_name, test_folder_path)
            
            logger.info("✅ GCS folder structure created:")
            for folder_type, success in result.items():
                status = "✅" if success else "❌"
                logger.info(f"   {status} {test_org_name}/{folder_type}/{test_folder_path}/")
            
            # Add to cleanup list
            self.cleanup_items.append({
                "type": "gcs_folder",
                "org_name": test_org_name,
                "folder_path": test_folder_path
            })
            
            return all(result.values())
            
        except GCSClientError as e:
            logger.error(f"❌ GCS folder structure creation failed: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Unexpected error in GCS folder structure test: {e}")
            return False
    
    def test_gcs_file_operations(self) -> bool:
        """Test basic GCS file operations."""
        logger.info("Testing GCS file operations...")
        
        if not gcs_client.is_initialized:
            logger.error("GCS client not initialized")
            return False
        
        try:
            test_org_name = "test-file-ops"
            test_folder_path = "test-uploads"
            test_file_name = f"test-file-{int(datetime.utcnow().timestamp())}.txt"
            test_content = f"Test file content created at {datetime.utcnow().isoformat()}"
            
            # Upload test file
            gcs_path = gcs_client.upload_file(
                test_org_name,
                test_folder_path,
                test_file_name,
                test_content.encode("utf-8"),
                "original"
            )
            
            logger.info(f"✅ File uploaded to: gs://{settings.GCS_BUCKET_NAME}/{gcs_path}")
            
            # List folder contents
            files = gcs_client.list_folder_contents(test_org_name, test_folder_path, "original")
            logger.info(f"✅ Folder contents listed: {len(files)} files")
            
            if test_file_name in files:
                logger.info(f"✅ Test file found in listing")
            else:
                logger.warning(f"⚠️ Test file not found in listing")
            
            # Add to cleanup list
            self.cleanup_items.append({
                "type": "gcs_file",
                "org_name": test_org_name,
                "folder_path": test_folder_path,
                "file_name": test_file_name
            })
            
            return True
            
        except Exception as e:
            logger.error(f"❌ GCS file operations test failed: {e}")
            return False
    
    async def test_folder_move_operation(self) -> bool:
        """Test folder move operation."""
        logger.info("Testing folder move operation...")
        
        if not self.test_org_id or not self.test_folder_id:
            logger.error("Test folder not available for move test")
            return False
        
        try:
            # Create a parent folder to move into
            parent_folder_data = FolderCreate(
                name=f"parent-folder-{int(datetime.utcnow().timestamp())}",
                parent_folder_id=None
            )
            
            parent_folder_response = await folder_service.create_folder(
                self.test_org_id,
                parent_folder_data,
                "test-user-id"
            )
            
            # Add parent to cleanup list
            self.cleanup_items.append({
                "type": "folder",
                "org_id": self.test_org_id,
                "id": parent_folder_response.id,
                "name": parent_folder_response.name
            })
            
            # Move the test folder into the parent
            moved_folder = await folder_service.move_folder(
                self.test_org_id,
                self.test_folder_id,
                parent_folder_response.id
            )
            
            logger.info(f"✅ Folder moved successfully")
            logger.info(f"   New path: {moved_folder.path}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Folder move operation failed: {e}")
            return False
    
    async def cleanup_test_data(self) -> None:
        """Clean up all test data created during verification."""
        logger.info("Cleaning up test data...")
        
        # Clean up in reverse order
        for item in reversed(self.cleanup_items):
            try:
                if item["type"] == "folder":
                    await folder_service.delete_folder(item["org_id"], item["id"])
                    logger.info(f"✅ Deleted test folder: {item['name']}")
                    
                elif item["type"] == "organization":
                    await organization_service.delete_organization(item["id"])
                    logger.info(f"✅ Deleted test organization: {item['name']}")
                    
                elif item["type"] == "gcs_folder":
                    gcs_client.delete_folder_structure(item["org_name"], item["folder_path"])
                    logger.info(f"✅ Deleted GCS folder: {item['org_name']}/{item['folder_path']}")
                    
                elif item["type"] == "gcs_file":
                    # Delete individual file
                    blob_name = f"{item['org_name']}/original/{item['folder_path']}/{item['file_name']}"
                    blob = gcs_client.bucket.blob(blob_name)
                    if blob.exists():
                        blob.delete()
                        logger.info(f"✅ Deleted GCS file: {blob_name}")
                        
            except Exception as e:
                logger.warning(f"⚠️ Failed to clean up {item['type']}: {e}")
    
    def display_summary(self, results: Dict[str, bool]) -> None:
        """Display verification summary."""
        print("\n" + "="*60)
        print("GCS SETUP VERIFICATION SUMMARY")
        print("="*60)
        
        passed = sum(results.values())
        total = len(results)
        
        print(f"Tests Passed: {passed}/{total}")
        print()
        
        for test_name, result in results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{status} {test_name}")
        
        print("="*60)
        
        if passed == total:
            print("🎉 All verification tests passed!")
            print("Your GCS setup is working correctly.")
        else:
            print(f"⚠️ {total - passed} test(s) failed.")
            print("Please review the errors above and fix any issues.")
        
        print("="*60)


async def main():
    """Main verification function."""
    print("GCS Setup Verification")
    print("Project:", settings.GCP_PROJECT_ID or "Not set")
    print("Bucket:", settings.GCS_BUCKET_NAME or "Not set")
    print("-" * 60)
    
    verification = GCSVerification()
    results = {}
    
    try:
        # Step 1: Check configuration
        results["Configuration Check"] = await verification.check_configuration()
        
        # Step 2: Check GCS client
        results["GCS Client Initialization"] = verification.check_gcs_client_initialization()
        
        # Step 3: Check Firebase
        results["Firebase Initialization"] = await verification.check_firebase_initialization()
        
        # Step 4: Create test organization
        results["Test Organization Creation"] = await verification.create_test_organization()
        
        # Step 5: Test organization lookup
        if results["Test Organization Creation"]:
            results["Organization Name Lookup"] = await verification.test_organization_name_lookup()
        
        # Step 6: Test GCS folder structure directly
        if results["GCS Client Initialization"]:
            results["GCS Folder Structure Creation"] = verification.test_gcs_folder_structure()
        
        # Step 7: Test file operations
        if results["GCS Client Initialization"]:
            results["GCS File Operations"] = verification.test_gcs_file_operations()
        
        # Step 8: Test integrated folder creation
        if results["Test Organization Creation"] and results["GCS Client Initialization"]:
            results["Integrated Folder Creation"] = await verification.test_folder_creation_with_gcs()
        
        # Step 9: Test folder move
        if results.get("Integrated Folder Creation"):
            results["Folder Move Operation"] = await verification.test_folder_move_operation()
        
    except KeyboardInterrupt:
        print("\nVerification interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error during verification: {e}")
    finally:
        # Always try to clean up
        try:
            await verification.cleanup_test_data()
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    # Display summary
    verification.display_summary(results)
    
    # Exit with appropriate code
    if all(results.values()):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())