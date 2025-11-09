#!/usr/bin/env python3
"""
Firestore Composite Index Manual Creation Helper
Document Intelligence API v1.0

This script helps identify missing Firestore composite indexes and provides 
gcloud CLI commands to create them manually. It tests queries that require 
indexes and generates the appropriate creation commands.

Usage:
    python create_firestore_indexes.py
    python create_firestore_indexes.py --project-id YOUR_PROJECT_ID
"""

import asyncio
import argparse
import sys
from pathlib import Path

# Add the app directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

from app.core.firebase_client import firebase_manager
from app.services.org_service import organization_service
from app.services.user_service import user_service
from app.services.document_service import document_service
from app.models.schemas import PaginationParams, OrganizationFilters, UserFilters, DocumentFilters
from app.models.organization import PlanType
from app.models.user import UserRole
from app.models.document import DocumentStatus, FileType

def generate_index_commands(project_id: str):
    """Generate gcloud commands for creating composite indexes."""
    print("📋 Required Firestore Composite Indexes")
    print("=" * 60)
    print()
    print("🔧 Use these gcloud commands to create the required indexes:")
    print()
    
    commands = [
        # Organizations - basic listing
        {
            "description": "Organizations: is_active + created_at ordering",
            "command": f"gcloud firestore indexes composite create --collection-group=organizations --query-scope=COLLECTION --field-config field-path=is_active,order=ASCENDING --field-config field-path=created_at,order=DESCENDING --project={project_id}"
        },
        # Organizations - with plan type filter
        {
            "description": "Organizations: is_active + plan_type + created_at ordering", 
            "command": f"gcloud firestore indexes composite create --collection-group=organizations --query-scope=COLLECTION --field-config field-path=is_active,order=ASCENDING --field-config field-path=plan_type,order=ASCENDING --field-config field-path=created_at,order=DESCENDING --project={project_id}"
        },
        # Users - basic listing
        {
            "description": "Users: org_id + is_active + created_at ordering",
            "command": f"gcloud firestore indexes composite create --collection-group=users --query-scope=COLLECTION --field-config field-path=org_id,order=ASCENDING --field-config field-path=is_active,order=ASCENDING --field-config field-path=created_at,order=DESCENDING --project={project_id}"
        },
        # Users - with role filter
        {
            "description": "Users: org_id + is_active + role + created_at ordering",
            "command": f"gcloud firestore indexes composite create --collection-group=users --query-scope=COLLECTION --field-config field-path=org_id,order=ASCENDING --field-config field-path=is_active,order=ASCENDING --field-config field-path=role,order=ASCENDING --field-config field-path=created_at,order=DESCENDING --project={project_id}"
        },
        # Documents - basic listing
        {
            "description": "Documents: org_id + is_active + created_at ordering",
            "command": f"gcloud firestore indexes composite create --collection-group=documents --query-scope=COLLECTION --field-config field-path=org_id,order=ASCENDING --field-config field-path=is_active,order=ASCENDING --field-config field-path=created_at,order=DESCENDING --project={project_id}"
        },
        # Documents - with folder_id filter
        {
            "description": "Documents: org_id + is_active + folder_id + created_at ordering",
            "command": f"gcloud firestore indexes composite create --collection-group=documents --query-scope=COLLECTION --field-config field-path=org_id,order=ASCENDING --field-config field-path=is_active,order=ASCENDING --field-config field-path=folder_id,order=ASCENDING --field-config field-path=created_at,order=DESCENDING --project={project_id}"
        },
        # Documents - with file_type filter
        {
            "description": "Documents: org_id + is_active + file_type + created_at ordering",
            "command": f"gcloud firestore indexes composite create --collection-group=documents --query-scope=COLLECTION --field-config field-path=org_id,order=ASCENDING --field-config field-path=is_active,order=ASCENDING --field-config field-path=file_type,order=ASCENDING --field-config field-path=created_at,order=DESCENDING --project={project_id}"
        },
        # Documents - with status filter
        {
            "description": "Documents: org_id + is_active + status + created_at ordering",
            "command": f"gcloud firestore indexes composite create --collection-group=documents --query-scope=COLLECTION --field-config field-path=org_id,order=ASCENDING --field-config field-path=is_active,order=ASCENDING --field-config field-path=status,order=ASCENDING --field-config field-path=created_at,order=DESCENDING --project={project_id}"
        }
    ]
    
    for i, cmd_info in enumerate(commands, 1):
        print(f"{i}. {cmd_info['description']}")
        print(f"   {cmd_info['command']}")
        print()
    
    print("💡 Alternative Methods:")
    print("1. Use Firebase CLI:")
    print(f"   firebase deploy --only firestore:indexes --project {project_id}")
    print()
    print("2. Use automated script:")
    print(f"   python deploy_firestore_indexes.py --project-id {project_id}")
    print()
    print("3. Create via Firebase Console:")
    print(f"   https://console.firebase.google.com/project/{project_id}/firestore/indexes")
    print()

async def test_queries_and_identify_missing_indexes(project_id: str):
    """Test queries and identify missing indexes."""
    print("🔍 Testing queries to identify missing indexes...")
    print("=" * 60)
    
    try:
        # Initialize Firebase
        print("🔧 Initializing Firebase...")
        await firebase_manager.initialize()
        print("✅ Firebase initialized successfully!")
        print()
        
        # Test queries that require composite indexes
        print("📊 Testing queries that require composite indexes...")
        print("   This will generate errors with links to create the required indexes.")
        print()
        
        # Query 1: Basic organization listing with is_active filter and created_at ordering
        print("1️⃣ Testing basic organization listing (is_active + created_at ordering)...")
        try:
            pagination = PaginationParams(page=1, per_page=5)
            result = await organization_service.list_organizations(pagination)
            print(f"   ✅ Query succeeded: Found {result.total} organizations")
        except Exception as e:
            if "index" in str(e).lower():
                print(f"   🎯 Index required! Error: {str(e)}")
            else:
                print(f"   ❌ Unexpected error: {str(e)}")
        print()
        
        # Query 2: Organization listing with plan_type filter
        print("2️⃣ Testing organization listing with plan_type filter (is_active + plan_type + created_at ordering)...")
        try:
            pagination = PaginationParams(page=1, per_page=5)
            filters = OrganizationFilters(plan_type=PlanType.STARTER)
            result = await organization_service.list_organizations(pagination, filters)
            print(f"   ✅ Query succeeded: Found {result.total} organizations")
        except Exception as e:
            if "index" in str(e).lower():
                print(f"   🎯 Index required! Error: {str(e)}")
            else:
                print(f"   ❌ Unexpected error: {str(e)}")
        print()
        
        # Query 3: Test with different plan type
        print("3️⃣ Testing organization listing with PRO plan_type filter...")
        try:
            pagination = PaginationParams(page=1, per_page=5)
            filters = OrganizationFilters(plan_type=PlanType.PRO)
            result = await organization_service.list_organizations(pagination, filters)
            print(f"   ✅ Query succeeded: Found {result.total} organizations")
        except Exception as e:
            if "index" in str(e).lower():
                print(f"   🎯 Index required! Error: {str(e)}")
            else:
                print(f"   ❌ Unexpected error: {str(e)}")
        print()
        
        # Query 4: Test user listing that requires composite index
        print("4️⃣ Testing user listing with active filter and created_at ordering...")
        try:
            # Need a real organization ID to test - let's get one from the orgs we listed
            pagination = PaginationParams(page=1, per_page=5)
            orgs = await organization_service.list_organizations(pagination)
            if orgs.organizations:
                org_id = orgs.organizations[0].id
                print(f"   Using organization ID: {org_id}")
                
                # This should trigger the index requirement
                user_pagination = PaginationParams(page=1, per_page=10)
                user_result = await user_service.list_users(org_id, user_pagination)
                print(f"   ✅ Query succeeded: Found {user_result.total} users")
            else:
                print("   ⚠️ No organizations found to test user listing")
        except Exception as e:
            if "index" in str(e).lower():
                print(f"   🎯 Index required! Error: {str(e)}")
            else:
                print(f"   ❌ Unexpected error: {str(e)}")
        print()
        
        # Query 5: Test user listing with role filter
        print("5️⃣ Testing user listing with role filter (is_active + role + created_at ordering)...")
        try:
            if orgs.organizations:
                org_id = orgs.organizations[0].id
                user_pagination = PaginationParams(page=1, per_page=10)
                user_filters = UserFilters(role=UserRole.ADMIN)
                user_result = await user_service.list_users(org_id, user_pagination, user_filters)
                print(f"   ✅ Query succeeded: Found {user_result.total} admin users")
            else:
                print("   ⚠️ No organizations found to test user listing with role filter")
        except Exception as e:
            if "index" in str(e).lower():
                print(f"   🎯 Index required! Error: {str(e)}")
            else:
                print(f"   ❌ Unexpected error: {str(e)}")
        print()
        
        # Query 6: Test document listing with basic filters (is_active + created_at ordering)
        print("6️⃣ Testing document listing with basic active filter and created_at ordering...")
        try:
            if orgs.organizations:
                org_id = orgs.organizations[0].id
                print(f"   Using organization ID: {org_id}")
                
                doc_pagination = PaginationParams(page=1, per_page=10)
                doc_result = await document_service.list_documents(org_id, doc_pagination)
                print(f"   ✅ Query succeeded: Found {doc_result.total} documents")
            else:
                print("   ⚠️ No organizations found to test document listing")
        except Exception as e:
            if "index" in str(e).lower():
                print(f"   🎯 Index required! Error: {str(e)}")
            else:
                print(f"   ❌ Unexpected error: {str(e)}")
        print()
        
        # Query 7: Test document listing with folder_id filter
        print("7️⃣ Testing document listing with folder_id filter (is_active + folder_id + created_at ordering)...")
        try:
            if orgs.organizations:
                org_id = orgs.organizations[0].id
                doc_pagination = PaginationParams(page=1, per_page=10)
                doc_filters = DocumentFilters(folder_id="control-docs")
                doc_result = await document_service.list_documents(org_id, doc_pagination, doc_filters)
                print(f"   ✅ Query succeeded: Found {doc_result.total} documents with folder_id filter")
            else:
                print("   ⚠️ No organizations found to test document listing with folder_id")
        except Exception as e:
            if "index" in str(e).lower():
                print(f"   🎯 Index required! Error: {str(e)}")
            else:
                print(f"   ❌ Unexpected error: {str(e)}")
        print()
        
        # Query 8: Test document listing with folder_path filter
        print("8️⃣ Testing document listing with folder_path filter (is_active + folder_path + created_at ordering)...")
        try:
            if orgs.organizations:
                org_id = orgs.organizations[0].id
                doc_pagination = PaginationParams(page=1, per_page=10)
                doc_filters = DocumentFilters(folder_path="invoices")
                doc_result = await document_service.list_documents(org_id, doc_pagination, doc_filters)
                print(f"   ✅ Query succeeded: Found {doc_result.total} documents with folder_path filter")
            else:
                print("   ⚠️ No organizations found to test document listing with folder_path")
        except Exception as e:
            if "index" in str(e).lower():
                print(f"   🎯 Index required! Error: {str(e)}")
            else:
                print(f"   ❌ Unexpected error: {str(e)}")
        print()
        
        # Query 9: Test document listing with file_type filter
        print("9️⃣ Testing document listing with file_type filter (is_active + file_type + created_at ordering)...")
        try:
            if orgs.organizations:
                org_id = orgs.organizations[0].id
                doc_pagination = PaginationParams(page=1, per_page=10)
                doc_filters = DocumentFilters(file_type=FileType.PDF)
                doc_result = await document_service.list_documents(org_id, doc_pagination, doc_filters)
                print(f"   ✅ Query succeeded: Found {doc_result.total} PDF documents")
            else:
                print("   ⚠️ No organizations found to test document listing with file_type")
        except Exception as e:
            if "index" in str(e).lower():
                print(f"   🎯 Index required! Error: {str(e)}")
            else:
                print(f"   ❌ Unexpected error: {str(e)}")
        print()
        
        # Query 10: Test document listing with status filter
        print("🔟 Testing document listing with status filter (is_active + status + created_at ordering)...")
        try:
            if orgs.organizations:
                org_id = orgs.organizations[0].id
                doc_pagination = PaginationParams(page=1, per_page=10)
                doc_filters = DocumentFilters(status=DocumentStatus.UPLOADED)
                doc_result = await document_service.list_documents(org_id, doc_pagination, doc_filters)
                print(f"   ✅ Query succeeded: Found {doc_result.total} uploaded documents")
            else:
                print("   ⚠️ No organizations found to test document listing with status")
        except Exception as e:
            if "index" in str(e).lower():
                print(f"   🎯 Index required! Error: {str(e)}")
            else:
                print(f"   ❌ Unexpected error: {str(e)}")
        print()
        
        # Query 11: Test document listing with combined filters
        print("1️⃣1️⃣ Testing document listing with combined filters (is_active + folder_id + file_type + created_at ordering)...")
        try:
            if orgs.organizations:
                org_id = orgs.organizations[0].id
                doc_pagination = PaginationParams(page=1, per_page=10)
                doc_filters = DocumentFilters(
                    folder_id="control-docs",
                    file_type=FileType.PDF,
                    status=DocumentStatus.UPLOADED
                )
                doc_result = await document_service.list_documents(org_id, doc_pagination, doc_filters)
                print(f"   ✅ Query succeeded: Found {doc_result.total} documents with combined filters")
            else:
                print("   ⚠️ No organizations found to test document listing with combined filters")
        except Exception as e:
            if "index" in str(e).lower():
                print(f"   🎯 Index required! Error: {str(e)}")
            else:
                print(f"   ❌ Unexpected error: {str(e)}")
        print()
        
        print("🎉 Query testing completed!")
        print()
        print("📋 Next Steps:")
        print("   1. If you saw index errors above, use the gcloud commands provided")
        print("   2. Or use the automated deployment script:")
        print(f"      python deploy_firestore_indexes.py --project-id {project_id}")
        print("   3. Wait for indexes to finish building (several minutes)")
        print("   4. Test your API endpoints")
        
    except Exception as e:
        print(f"❌ Script failed: {str(e)}")
        return False
    
    finally:
        # Close Firebase connection
        try:
            await firebase_manager.close()
            print("🔒 Firebase connection closed")
        except Exception:
            pass
    
    return True

def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Firestore Composite Index Manual Creation Helper",
        epilog="""
Examples:
  # Generate index creation commands
  python create_firestore_indexes.py --project-id my-project-123
  
  # Test queries and identify missing indexes  
  python create_firestore_indexes.py --project-id my-project-123 --test-queries
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--project-id",
        help="Google Cloud Project ID"
    )
    parser.add_argument(
        "--test-queries",
        action="store_true",
        help="Test queries to identify missing indexes"
    )
    
    args = parser.parse_args()
    
    # Use environment or prompt for project ID
    project_id = args.project_id
    if not project_id:
        try:
            import os
            project_id = os.environ.get('FIREBASE_PROJECT_ID') or os.environ.get('GCP_PROJECT_ID')
            if not project_id:
                project_id = input("Enter your Google Cloud Project ID: ").strip()
        except:
            print("❌ Project ID is required")
            sys.exit(1)
    
    print("Firestore Composite Index Creation Helper")
    print("This script helps you create the required Firestore composite indexes.")
    print()
    
    if args.test_queries:
        # Run the async function to test queries
        try:
            result = asyncio.run(test_queries_and_identify_missing_indexes(project_id))
            sys.exit(0 if result else 1)
        except KeyboardInterrupt:
            print("\\n⏹️  Script interrupted by user")
            sys.exit(1)
    else:
        # Just generate the commands
        generate_index_commands(project_id)
        print("📋 Summary:")
        print("1. Choose one of the methods above to create the indexes")
        print("2. Wait for indexes to build (several minutes)")
        print("3. Test your API endpoints")
        print("4. Use --test-queries flag to verify indexes are working")
        sys.exit(0)

if __name__ == "__main__":
    main()