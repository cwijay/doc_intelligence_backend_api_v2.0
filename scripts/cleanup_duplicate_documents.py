#!/usr/bin/env python3
"""
Cleanup script to remove orphaned Firestore documents that don't have corresponding GCS files.
This script should be run after the diagnostic script to clean up sync issues.
"""

import asyncio
import sys
import json
from pathlib import Path
from typing import List, Dict, Any, Set
from datetime import datetime

# Add the app directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.firebase_client import firebase_manager, get_collection
from app.core.gcs_client import gcs_client
from app.services.document_service import document_service
from app.models.schemas import PaginationParams, DocumentFilters
from app.models.document import Document

class DocumentCleanup:
    """Clean up orphaned Firestore documents."""
    
    def __init__(self):
        self.org_id: str = ""
        self.folder_id: str = ""
        self.firestore_docs: List[Document] = []
        self.gcs_files: Set[str] = set()
        self.orphaned_docs: List[Document] = []
        self.backup_data: List[Dict[str, Any]] = []

    async def cleanup_organization_documents(self, org_id: str, folder_id: str = None, dry_run: bool = True):
        """
        Clean up orphaned documents for a specific organization and folder.
        
        Args:
            org_id: Organization ID to clean up
            folder_id: Optional folder ID to filter by
            dry_run: If True, only simulate cleanup without actually deleting
        """
        self.org_id = org_id
        self.folder_id = folder_id
        
        print(f"🧹 Document Cleanup Tool")
        print(f"Organization: {org_id}")
        if folder_id:
            print(f"Folder: {folder_id}")
        print(f"Mode: {'DRY RUN (simulation)' if dry_run else 'LIVE DELETION'}")
        print("=" * 80)
        
        # Get current state
        await self._analyze_documents()
        
        # Create backup
        self._create_backup()
        
        # Perform cleanup
        if self.orphaned_docs:
            if dry_run:
                self._simulate_cleanup()
            else:
                await self._perform_cleanup()
        else:
            print("✅ No orphaned documents found - nothing to clean up!")

    async def _analyze_documents(self):
        """Analyze documents to find orphaned entries."""
        print("🔍 Analyzing documents...")
        
        # Get Firestore documents
        await self._get_firestore_documents()
        
        # Get GCS files
        await self._get_gcs_files()
        
        # Find orphaned documents
        self._find_orphaned_documents()

    async def _get_firestore_documents(self):
        """Get all Firestore documents for the organization/folder."""
        print("📊 Fetching Firestore documents...")
        
        try:
            pagination = PaginationParams(page=1, per_page=100)
            filters = None
            if self.folder_id:
                filters = DocumentFilters(folder_id=self.folder_id)
            
            result = await document_service.list_documents(self.org_id, pagination, filters)
            self.firestore_docs = result.documents
            
            print(f"   ✅ Found {len(self.firestore_docs)} documents in Firestore")
            
        except Exception as e:
            print(f"   ❌ Error fetching Firestore documents: {e}")
            self.firestore_docs = []

    async def _get_gcs_files(self):
        """Get all GCS files for the organization/folder."""
        print("☁️  Fetching GCS files...")
        
        if not gcs_client.is_initialized:
            print("   ❌ GCS client not initialized")
            return
        
        try:
            # Get organization name for proper path construction
            org_name = await self._get_org_name()
            if not org_name:
                print("   ❌ Could not determine organization name")
                return
            
            if self.folder_id:
                prefix = f"{org_name}/original/{self.folder_id}/"
            else:
                prefix = f"{org_name}/original/"
            
            # List files in GCS
            blobs = list(gcs_client.bucket.list_blobs(prefix=prefix))
            
            self.gcs_files = set()
            for blob in blobs:
                # Skip folder placeholders
                if not blob.name.endswith(('.keep', '.folder_placeholder')):
                    self.gcs_files.add(blob.name)
            
            print(f"   ✅ Found {len(self.gcs_files)} files in GCS")
            
        except Exception as e:
            print(f"   ❌ Error fetching GCS files: {e}")
            self.gcs_files = set()

    async def _get_org_name(self) -> str:
        """Get organization name from documents or organization service."""
        # Try to get from documents first
        if self.firestore_docs:
            for doc in self.firestore_docs:
                if doc.storage_path:
                    # Extract org name from storage path
                    parts = doc.storage_path.split('/')
                    if len(parts) >= 2:
                        return parts[0]
        
        # Fallback: get from organization service
        try:
            from app.services.org_service import organization_service
            org = await organization_service.get_organization(self.org_id)
            return org.name
        except Exception:
            return None

    def _find_orphaned_documents(self):
        """Find Firestore documents that don't have corresponding GCS files."""
        print("🔗 Finding orphaned documents...")
        
        self.orphaned_docs = []
        
        for doc in self.firestore_docs:
            if doc.storage_path not in self.gcs_files:
                self.orphaned_docs.append(doc)
        
        print(f"   🚨 Found {len(self.orphaned_docs)} orphaned Firestore documents")
        
        # Display orphaned documents
        if self.orphaned_docs:
            print("\n   📋 Orphaned Documents:")
            for i, doc in enumerate(self.orphaned_docs, 1):
                print(f"   {i:2d}. {doc.filename} (ID: {doc.id[:8]}...)")
                print(f"       Expected GCS Path: {doc.storage_path}")
                print(f"       Created: {doc.created_at}")
                print()

    def _create_backup(self):
        """Create backup of documents to be deleted."""
        if not self.orphaned_docs:
            return
        
        print("💾 Creating backup of documents to be deleted...")
        
        self.backup_data = []
        for doc in self.orphaned_docs:
            backup_entry = {
                "id": doc.id,
                "filename": doc.filename,
                "original_filename": doc.original_filename,
                "storage_path": doc.storage_path,
                "folder_id": doc.folder_id,
                "org_id": doc.org_id,
                "file_type": doc.file_type.value,
                "file_size": doc.file_size,
                "status": doc.status.value,
                "uploaded_by": doc.uploaded_by,
                "metadata": doc.metadata,
                "is_active": doc.is_active,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
                "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
            }
            self.backup_data.append(backup_entry)
        
        # Save backup to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"document_cleanup_backup_{self.org_id}_{timestamp}.json"
        backup_path = Path(__file__).parent / backup_filename
        
        with open(backup_path, 'w') as f:
            json.dump({
                "backup_info": {
                    "org_id": self.org_id,
                    "folder_id": self.folder_id,
                    "timestamp": timestamp,
                    "total_documents": len(self.backup_data)
                },
                "documents": self.backup_data
            }, f, indent=2)
        
        print(f"   ✅ Backup saved to: {backup_path}")
        print(f"   📊 Backed up {len(self.backup_data)} documents")

    def _simulate_cleanup(self):
        """Simulate cleanup without actually deleting anything."""
        print("\n🧪 SIMULATION MODE - No actual deletions will be performed")
        print("=" * 60)
        
        if not self.orphaned_docs:
            print("✅ No orphaned documents to clean up!")
            return
        
        print(f"📋 Would delete {len(self.orphaned_docs)} orphaned documents:")
        print()
        
        for i, doc in enumerate(self.orphaned_docs, 1):
            print(f"   {i:2d}. DELETE: {doc.filename}")
            print(f"       Firestore ID: {doc.id}")
            print(f"       Missing GCS Path: {doc.storage_path}")
            print(f"       Created: {doc.created_at}")
            print(f"       Size: {doc.file_size} bytes")
            print()
        
        print("💡 To perform actual cleanup, run with --live flag:")
        print(f"   python cleanup_duplicate_documents.py {self.org_id} {self.folder_id or ''} --live")

    async def _perform_cleanup(self):
        """Actually delete the orphaned Firestore documents."""
        print("\n🚨 LIVE DELETION MODE - Permanently removing orphaned documents")
        print("=" * 60)
        
        if not self.orphaned_docs:
            print("✅ No orphaned documents to clean up!")
            return
        
        print(f"🗑️  Deleting {len(self.orphaned_docs)} orphaned documents...")
        print()
        
        deleted_count = 0
        errors = []
        
        collection = get_collection(f"organizations/{self.org_id}/documents")
        
        for i, doc in enumerate(self.orphaned_docs, 1):
            try:
                print(f"   {i:2d}/{len(self.orphaned_docs)} Deleting: {doc.filename} (ID: {doc.id[:8]}...)")
                
                # Delete from Firestore
                doc_ref = collection.document(doc.id)
                await doc_ref.delete()
                
                deleted_count += 1
                print(f"       ✅ Deleted successfully")
                
            except Exception as e:
                error_msg = f"Failed to delete {doc.filename} (ID: {doc.id}): {e}"
                errors.append(error_msg)
                print(f"       ❌ Error: {e}")
        
        print()
        print("=" * 60)
        print("🧹 CLEANUP SUMMARY")
        print("=" * 60)
        print(f"✅ Successfully deleted: {deleted_count} documents")
        print(f"❌ Errors: {len(errors)}")
        
        if errors:
            print("\n🚨 Deletion Errors:")
            for error in errors:
                print(f"   - {error}")
        
        if deleted_count > 0:
            print(f"\n💾 Backup file contains all deleted document metadata")
            print(f"📊 The folder should now show only the correct number of documents")

async def main():
    """Main function to run the cleanup."""
    print("Document Cleanup Tool")
    print("Removes orphaned Firestore documents that don't have corresponding GCS files")
    print()
    
    # Parse command line arguments
    if len(sys.argv) < 2:
        print("Usage: python cleanup_duplicate_documents.py <org_id> [folder_id] [--live] [--confirm]")
        print("Example: python cleanup_duplicate_documents.py GUbmPT49OSDO3eFDU2r5 control-docs")
        print("Example: python cleanup_duplicate_documents.py GUbmPT49OSDO3eFDU2r5 control-docs --live --confirm")
        print()
        print("Flags:")
        print("  --live      Perform actual deletion (default is dry run)")
        print("  --confirm   Required with --live to confirm deletion")
        sys.exit(1)
    
    org_id = sys.argv[1]
    folder_id = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith('--') else None
    dry_run = '--live' not in sys.argv
    
    try:
        # Initialize Firebase and GCS
        print("🔧 Initializing Firebase and GCS...")
        await firebase_manager.initialize()
        print("✅ Firebase initialized!")
        
        if not gcs_client.is_initialized:
            print("❌ GCS client not initialized - some features may not work")
        else:
            print("✅ GCS client initialized!")
        print()
        
        # Confirm deletion if in live mode
        if not dry_run:
            print("🚨 WARNING: You are about to permanently delete orphaned documents!")
            print("This action cannot be undone!")
            print("   Add --confirm flag to proceed with deletion")
            if '--confirm' not in sys.argv:
                print("❌ Cleanup cancelled - missing --confirm flag")
                return
            print("✅ Deletion confirmed via --confirm flag")
            print()
        
        # Run cleanup
        cleanup = DocumentCleanup()
        await cleanup.cleanup_organization_documents(org_id, folder_id, dry_run)
        
    except KeyboardInterrupt:
        print("\n⏹️  Cleanup interrupted by user")
    except Exception as e:
        print(f"❌ Cleanup failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Close connections
        try:
            await firebase_manager.close()
            print("🔒 Firebase connection closed")
        except Exception:
            pass

if __name__ == "__main__":
    asyncio.run(main())