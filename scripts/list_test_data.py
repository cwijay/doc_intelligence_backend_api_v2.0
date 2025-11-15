#!/usr/bin/env python3
"""
List Test Data Script

Quick script to view what test data exists in Firestore without deleting anything.

Usage:
    python scripts/list_test_data.py
    python scripts/list_test_data.py --pattern "Test"
    python scripts/list_test_data.py --all
"""

import asyncio
import argparse
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

# Load environment variables
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    load_dotenv(env_file)
else:
    load_dotenv()

from google.cloud import firestore
from app.core.config import settings


async def list_organizations(pattern: str = None, show_all: bool = False):
    """List all organizations, optionally filtered by pattern"""

    db = firestore.AsyncClient(
        project=settings.FIREBASE_PROJECT_ID,
        database=settings.FIREBASE_DATABASE_ID
    )

    try:
        print("=" * 80)
        print("ORGANIZATIONS IN FIRESTORE")
        print("=" * 80)
        print(f"Project: {settings.FIREBASE_PROJECT_ID}")
        print(f"Database: {settings.FIREBASE_DATABASE_ID}")
        print("=" * 80)
        print()

        orgs = []
        async for doc in db.collection("organizations").stream():
            org_data = doc.to_dict()
            org_name = org_data.get("name", "Unknown")

            # Filter by pattern if provided
            if pattern and not show_all:
                if pattern.lower() not in org_name.lower():
                    continue

            orgs.append({
                "id": doc.id,
                "name": org_name,
                "plan_type": org_data.get("plan_type", "unknown"),
                "created_at": org_data.get("created_at"),
                "is_active": org_data.get("is_active", True)
            })

        if not orgs:
            if pattern:
                print(f"No organizations found matching pattern: '{pattern}'")
            else:
                print("No organizations found in database")
            return

        # Sort by created_at
        orgs.sort(key=lambda x: x.get("created_at") or datetime.min, reverse=True)

        # Print organizations
        print(f"Found {len(orgs)} organization(s):\n")
        for i, org in enumerate(orgs, 1):
            print(f"{i}. {org['name']}")
            print(f"   ID: {org['id']}")
            print(f"   Plan: {org['plan_type']}")
            print(f"   Active: {org['is_active']}")
            if org.get("created_at"):
                print(f"   Created: {org['created_at']}")
            print()

        # Count statistics
        print("=" * 80)
        print("STATISTICS")
        print("=" * 80)

        # Count users
        user_count = 0
        async for _ in db.collection("users").stream():
            user_count += 1

        # Count documents
        doc_count = 0
        async for _ in db.collection("documents").stream():
            doc_count += 1

        # Count folders
        folder_count = 0
        async for _ in db.collection("folders").stream():
            folder_count += 1

        # Count sessions
        session_count = 0
        async for _ in db.collection("sessions").stream():
            session_count += 1

        print(f"Total Organizations: {len(orgs)}")
        print(f"Total Users: {user_count}")
        print(f"Total Documents: {doc_count}")
        print(f"Total Folders: {folder_count}")
        print(f"Total Sessions: {session_count}")
        print("=" * 80)

    finally:
        await db.close()


async def main():
    parser = argparse.ArgumentParser(description="List test data in Firestore")
    parser.add_argument(
        "--pattern",
        type=str,
        default="Test",
        help="Name pattern to filter organizations (default: 'Test')"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Show all organizations (ignore pattern)"
    )

    args = parser.parse_args()

    try:
        await list_organizations(
            pattern=None if args.all else args.pattern,
            show_all=args.all
        )
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
