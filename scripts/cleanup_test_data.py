#!/usr/bin/env python3
"""
Comprehensive GCP Test Data Cleanup Script

This script cleans up all test data from Firestore and GCS created during testing.
It can be run in different modes:
- All test data (default)
- Specific organization
- Specific date range
- Dry run (show what would be deleted without actually deleting)

Usage:
    # Clean all test data (organizations starting with "Test")
    python scripts/cleanup_test_data.py --all

    # Clean specific organization
    python scripts/cleanup_test_data.py --org-id ORG_ID

    # Clean test data from a specific date
    python scripts/cleanup_test_data.py --since "2025-11-15"

    # Dry run (show what would be deleted)
    python scripts/cleanup_test_data.py --all --dry-run

    # Clean everything (DANGEROUS - requires confirmation)
    python scripts/cleanup_test_data.py --force-clean-all
"""

import asyncio
import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Set
import re

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
import os

# Load environment variables
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    load_dotenv(env_file)
else:
    load_dotenv()  # Load from system

# Import after loading env
from google.cloud import firestore
from google.cloud import storage
from app.core.config import settings

class TestDataCleaner:
    """Comprehensive test data cleanup for Firestore and GCS"""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.db = firestore.AsyncClient(
            project=settings.FIREBASE_PROJECT_ID,
            database=settings.FIREBASE_DATABASE_ID
        )
        self.storage_client = storage.Client(project=settings.GCP_PROJECT_ID)
        self.bucket = self.storage_client.bucket(settings.GCS_BUCKET_NAME)

        # Statistics
        self.stats = {
            "organizations_deleted": 0,
            "users_deleted": 0,
            "documents_deleted": 0,
            "folders_deleted": 0,
            "gcs_files_deleted": 0,
            "sessions_deleted": 0,
        }

    async def find_test_organizations(
        self,
        name_pattern: str = "Test",
        since_date: datetime = None
    ) -> List[Dict]:
        """
        Find all test organizations.

        Args:
            name_pattern: Pattern to match in organization name (default: "Test")
            since_date: Only find orgs created after this date

        Returns:
            List of organization documents
        """
        print(f"\n🔍 Searching for organizations matching pattern: '{name_pattern}'...")

        orgs = []
        query = self.db.collection("organizations")

        # Add date filter if provided
        if since_date:
            query = query.where("created_at", ">=", since_date)

        async for doc in query.stream():
            org_data = doc.to_dict()
            org_name = org_data.get("name", "")

            # Check if name matches pattern
            if name_pattern.lower() in org_name.lower():
                orgs.append({"id": doc.id, **org_data})
                print(f"  Found: {org_name} ({doc.id})")

        print(f"  Total: {len(orgs)} organizations found")
        return orgs

    async def find_organization_users(self, org_id: str) -> List[Dict]:
        """Find all users in an organization"""
        users = []
        query = self.db.collection("users").where("org_id", "==", org_id)

        async for doc in query.stream():
            user_data = doc.to_dict()
            users.append({"id": doc.id, **user_data})

        return users

    async def find_organization_documents(self, org_id: str) -> List[Dict]:
        """Find all documents in an organization"""
        documents = []
        query = self.db.collection("documents").where("organization_id", "==", org_id)

        async for doc in query.stream():
            doc_data = doc.to_dict()
            documents.append({"id": doc.id, **doc_data})

        return documents

    async def find_organization_folders(self, org_id: str) -> List[Dict]:
        """Find all folders in an organization"""
        folders = []
        query = self.db.collection("folders").where("organization_id", "==", org_id)

        async for doc in query.stream():
            folder_data = doc.to_dict()
            folders.append({"id": doc.id, **folder_data})

        return folders

    async def find_user_sessions(self, user_id: str) -> List[Dict]:
        """Find all sessions for a user"""
        sessions = []
        query = self.db.collection("sessions").where("user_id", "==", user_id)

        async for doc in query.stream():
            session_data = doc.to_dict()
            sessions.append({"id": doc.id, **session_data})

        return sessions

    async def delete_gcs_files(self, storage_paths: List[str]):
        """Delete files from GCS"""
        for path in storage_paths:
            try:
                if self.dry_run:
                    print(f"    [DRY RUN] Would delete GCS file: {path}")
                else:
                    blob = self.bucket.blob(path)
                    if blob.exists():
                        blob.delete()
                        print(f"    ✓ Deleted GCS file: {path}")
                        self.stats["gcs_files_deleted"] += 1
                    else:
                        print(f"    ⚠ GCS file not found: {path}")
            except Exception as e:
                print(f"    ✗ Error deleting GCS file {path}: {e}")

    async def delete_organization(
        self,
        org_id: str,
        org_name: str,
        delete_cascade: bool = True
    ):
        """
        Delete an organization and optionally all related data.

        Args:
            org_id: Organization ID
            org_name: Organization name (for logging)
            delete_cascade: If True, delete all related data (users, docs, etc.)
        """
        print(f"\n{'🗑️  [DRY RUN] ' if self.dry_run else '🗑️  '}Deleting organization: {org_name} ({org_id})")

        if delete_cascade:
            # 1. Find and delete all documents
            documents = await self.find_organization_documents(org_id)
            if documents:
                print(f"  📄 Found {len(documents)} documents")
                storage_paths = []
                for doc in documents:
                    if self.dry_run:
                        print(f"    [DRY RUN] Would delete document: {doc.get('filename')} ({doc['id']})")
                    else:
                        # Delete Firestore document
                        await self.db.collection("documents").document(doc["id"]).delete()
                        print(f"    ✓ Deleted document: {doc.get('filename')} ({doc['id']})")
                        self.stats["documents_deleted"] += 1

                    # Collect GCS paths
                    if doc.get("storage_path"):
                        storage_paths.append(doc["storage_path"])

                # Delete GCS files
                if storage_paths:
                    print(f"  💾 Deleting {len(storage_paths)} GCS files...")
                    await self.delete_gcs_files(storage_paths)

            # 2. Find and delete all folders
            folders = await self.find_organization_folders(org_id)
            if folders:
                print(f"  📁 Found {len(folders)} folders")
                for folder in folders:
                    if self.dry_run:
                        print(f"    [DRY RUN] Would delete folder: {folder.get('name')} ({folder['id']})")
                    else:
                        await self.db.collection("folders").document(folder["id"]).delete()
                        print(f"    ✓ Deleted folder: {folder.get('name')} ({folder['id']})")
                        self.stats["folders_deleted"] += 1

            # 3. Find and delete all users (and their sessions)
            users = await self.find_organization_users(org_id)
            if users:
                print(f"  👤 Found {len(users)} users")
                for user in users:
                    # Delete user sessions first
                    sessions = await self.find_user_sessions(user["id"])
                    if sessions:
                        for session in sessions:
                            if self.dry_run:
                                print(f"    [DRY RUN] Would delete session: {session['id']}")
                            else:
                                await self.db.collection("sessions").document(session["id"]).delete()
                                self.stats["sessions_deleted"] += 1

                    # Delete user
                    if self.dry_run:
                        print(f"    [DRY RUN] Would delete user: {user.get('email')} ({user['id']})")
                    else:
                        await self.db.collection("users").document(user["id"]).delete()
                        print(f"    ✓ Deleted user: {user.get('email')} ({user['id']})")
                        self.stats["users_deleted"] += 1

        # 4. Finally, delete the organization itself
        if self.dry_run:
            print(f"  [DRY RUN] Would delete organization: {org_name}")
        else:
            await self.db.collection("organizations").document(org_id).delete()
            print(f"  ✓ Deleted organization: {org_name}")
            self.stats["organizations_deleted"] += 1

    async def cleanup_test_organizations(
        self,
        name_pattern: str = "Test",
        since_date: datetime = None
    ):
        """Clean up all test organizations and their related data"""
        # Find test organizations
        orgs = await self.find_test_organizations(name_pattern, since_date)

        if not orgs:
            print("\n✓ No test organizations found to clean up")
            return

        # Confirm deletion
        if not self.dry_run:
            print(f"\n⚠️  WARNING: About to delete {len(orgs)} organizations and all related data!")
            print("  This action cannot be undone.")
            response = input("\nType 'yes' to confirm deletion: ")
            if response.lower() != 'yes':
                print("❌ Cleanup cancelled")
                return

        # Delete each organization
        for org in orgs:
            await self.delete_organization(
                org["id"],
                org.get("name", "Unknown"),
                delete_cascade=True
            )

    async def cleanup_single_organization(self, org_id: str):
        """Clean up a single organization by ID"""
        try:
            org_ref = self.db.collection("organizations").document(org_id)
            org_doc = await org_ref.get()

            if not org_doc.exists:
                print(f"❌ Organization {org_id} not found")
                return

            org_data = org_doc.to_dict()
            org_name = org_data.get("name", "Unknown")

            # Confirm deletion
            if not self.dry_run:
                print(f"\n⚠️  WARNING: About to delete organization '{org_name}' and all related data!")
                print("  This action cannot be undone.")
                response = input("\nType 'yes' to confirm deletion: ")
                if response.lower() != 'yes':
                    print("❌ Cleanup cancelled")
                    return

            await self.delete_organization(org_id, org_name, delete_cascade=True)

        except Exception as e:
            print(f"❌ Error cleaning up organization {org_id}: {e}")

    async def cleanup_all_organizations(self):
        """Clean up ALL organizations (DANGEROUS - requires explicit confirmation)"""
        print("\n🚨 WARNING: This will delete ALL organizations in the database!")
        print("  This is intended for development/test environments only.")
        print("  This action cannot be undone.\n")

        if not self.dry_run:
            response = input("Type 'DELETE ALL ORGANIZATIONS' to confirm: ")
            if response != "DELETE ALL ORGANIZATIONS":
                print("❌ Cleanup cancelled")
                return

        # Get all organizations
        orgs = []
        async for doc in self.db.collection("organizations").stream():
            org_data = doc.to_dict()
            orgs.append({"id": doc.id, **org_data})

        print(f"\n🗑️  Deleting {len(orgs)} organizations...")

        for org in orgs:
            await self.delete_organization(
                org["id"],
                org.get("name", "Unknown"),
                delete_cascade=True
            )

    def print_summary(self):
        """Print cleanup summary"""
        print("\n" + "=" * 60)
        print("CLEANUP SUMMARY")
        print("=" * 60)
        if self.dry_run:
            print("MODE: DRY RUN (no actual deletions)")
        else:
            print("MODE: LIVE (deletions performed)")
        print()
        print(f"  Organizations: {self.stats['organizations_deleted']}")
        print(f"  Users: {self.stats['users_deleted']}")
        print(f"  Documents: {self.stats['documents_deleted']}")
        print(f"  Folders: {self.stats['folders_deleted']}")
        print(f"  GCS Files: {self.stats['gcs_files_deleted']}")
        print(f"  Sessions: {self.stats['sessions_deleted']}")
        print("=" * 60 + "\n")

    async def close(self):
        """Close connections"""
        await self.db.close()


async def main():
    parser = argparse.ArgumentParser(
        description="Clean up test data from Firestore and GCS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    # Cleanup modes
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--all",
        action="store_true",
        help="Clean all test organizations (name contains 'Test')"
    )
    mode_group.add_argument(
        "--org-id",
        type=str,
        help="Clean specific organization by ID"
    )
    mode_group.add_argument(
        "--force-clean-all",
        action="store_true",
        help="Clean ALL organizations (DANGEROUS)"
    )

    # Filters
    parser.add_argument(
        "--pattern",
        type=str,
        default="Test",
        help="Name pattern to match (default: 'Test')"
    )
    parser.add_argument(
        "--since",
        type=str,
        help="Only clean orgs created after this date (YYYY-MM-DD)"
    )

    # Options
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting"
    )

    args = parser.parse_args()

    # Parse since date
    since_date = None
    if args.since:
        try:
            since_date = datetime.strptime(args.since, "%Y-%m-%d")
        except ValueError:
            print(f"❌ Invalid date format: {args.since}. Use YYYY-MM-DD")
            sys.exit(1)

    # Create cleaner
    cleaner = TestDataCleaner(dry_run=args.dry_run)

    try:
        print("=" * 60)
        print("GCP TEST DATA CLEANUP")
        print("=" * 60)
        print(f"Project: {settings.FIREBASE_PROJECT_ID}")
        print(f"Database: {settings.FIREBASE_DATABASE_ID}")
        print(f"Bucket: {settings.GCS_BUCKET_NAME}")
        print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
        print("=" * 60)

        # Execute cleanup based on mode
        if args.all:
            await cleaner.cleanup_test_organizations(
                name_pattern=args.pattern,
                since_date=since_date
            )
        elif args.org_id:
            await cleaner.cleanup_single_organization(args.org_id)
        elif args.force_clean_all:
            await cleaner.cleanup_all_organizations()

        # Print summary
        cleaner.print_summary()

    except KeyboardInterrupt:
        print("\n\n❌ Cleanup interrupted by user")
    except Exception as e:
        print(f"\n❌ Error during cleanup: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await cleaner.close()


if __name__ == "__main__":
    asyncio.run(main())
