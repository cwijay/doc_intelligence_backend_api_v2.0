#!/usr/bin/env python3
"""
Enhanced cleanup script to remove duplicate Firestore documents that have the same storage_path.
This handles the specific case where multiple Firestore documents reference the same GCS file.
"""

import asyncio
import sys
import json
from pathlib import Path
from typing import List, Dict, Any, Set
from datetime import datetime
from collections import defaultdict

# Add the app directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.firebase_client import firebase_manager, get_collection
from app.core.gcs_client import gcs_client
from app.services.document_service import document_service
from app.models.schemas import PaginationParams, DocumentFilters
from app.models.document import Document

class DuplicateStoragePathCleanup:
    """Clean up duplicate Firestore documents with same storage_path."""
    
    def __init__(self):
        self.org_id: str = ""
        self.folder_id: str = ""
        self.firestore_docs: List[Document] = []
        self.storage_path_groups: Dict[str, List[Document]] = defaultdict(list)
        self.duplicate_groups: Dict[str, List[Document]] = {}
        self.docs_to_keep: List[Document] = []
        self.docs_to_delete: List[Document] = []
        self.backup_data: List[Dict[str, Any]] = []

    async def cleanup_duplicate_storage_paths(self, org_id: str, folder_id: str = None, dry_run: bool = True):
        """
        Clean up documents with duplicate storage_paths.
        
        Args:
            org_id: Organization ID to clean up
            folder_id: Optional folder ID to filter by
            dry_run: If True, only simulate cleanup without actually deleting
        """
        self.org_id = org_id
        self.folder_id = folder_id
        
        print(f"🔄 Duplicate Storage Path Cleanup Tool")
        print(f"Organization: {org_id}")
        if folder_id:
            print(f"Folder: {folder_id}")
        print(f"Mode: {'DRY RUN (simulation)' if dry_run else 'LIVE DELETION'}")
        print("=" * 80)
        
        # Analyze documents and find duplicates
        await self._analyze_duplicates()
        
        # Create backup
        self._create_backup()
        
        # Perform cleanup
        if self.docs_to_delete:
            if dry_run:
                self._simulate_cleanup()
            else:
                await self._perform_cleanup()
        else:
            print("✅ No duplicate storage paths found - nothing to clean up!")

    async def _analyze_duplicates(self):
        """Analyze documents to find those with duplicate storage_paths."""
        print("🔍 Analyzing documents for duplicate storage paths...")
        
        # Get Firestore documents
        await self._get_firestore_documents()
        
        # Group by storage_path
        self._group_by_storage_path()
        
        # Find duplicates and decide which to keep/delete
        self._identify_duplicates_and_decide()

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

    def _group_by_storage_path(self):
        """Group documents by their storage_path."""
        print("📋 Grouping documents by storage_path...")
        
        self.storage_path_groups = defaultdict(list)
        
        for doc in self.firestore_docs:
            if doc.storage_path:
                # Convert DocumentResponse back to Document for easier handling
                doc_obj = Document(
                    id=doc.id,
                    org_id=doc.org_id,
                    folder_id=doc.folder_id,
                    filename=doc.filename,
                    original_filename=doc.original_filename,
                    file_type=doc.file_type,
                    file_size=doc.file_size,
                    storage_path=doc.storage_path,
                    status=doc.status,
                    uploaded_by=doc.uploaded_by,
                    metadata=doc.metadata,
                    is_active=doc.is_active,
                    created_at=doc.created_at,
                    updated_at=doc.updated_at
                )
                self.storage_path_groups[doc.storage_path].append(doc_obj)
        
        # Find groups with duplicates
        total_groups = len(self.storage_path_groups)
        duplicate_count = sum(1 for docs in self.storage_path_groups.values() if len(docs) > 1)
        
        print(f"   📊 Total storage paths: {total_groups}")
        print(f"   🚨 Storage paths with duplicates: {duplicate_count}")

    def _identify_duplicates_and_decide(self):
        """Identify duplicate groups and decide which documents to keep vs delete."""
        print("🧠 Deciding which documents to keep and which to delete...")
        
        self.duplicate_groups = {}
        self.docs_to_keep = []
        self.docs_to_delete = []
        
        for storage_path, docs in self.storage_path_groups.items():
            if len(docs) > 1:
                # This is a duplicate group
                self.duplicate_groups[storage_path] = docs
                
                # Decision logic: Keep the one with correct file size, or latest if sizes match
                best_doc = self._choose_best_document(docs, storage_path)
                self.docs_to_keep.append(best_doc)
                
                # Mark others for deletion
                for doc in docs:
                    if doc.id != best_doc.id:
                        self.docs_to_delete.append(doc)
            else:
                # Single document, keep it
                self.docs_to_keep.append(docs[0])
        
        print(f"   ✅ Documents to keep: {len(self.docs_to_keep)}")
        print(f"   🗑️  Documents to delete: {len(self.docs_to_delete)}")
        print()
        
        # Display duplicate groups
        if self.duplicate_groups:
            print("📋 DUPLICATE GROUPS FOUND:")
            print("-" * 50)
            for i, (storage_path, docs) in enumerate(self.duplicate_groups.items(), 1):
                print(f"   {i}. Storage Path: {storage_path}")
                print(f"      📄 {len(docs)} duplicate documents:")
                
                for j, doc in enumerate(docs, 1):
                    keep_indicator = "✅ KEEP" if doc.id in [d.id for d in self.docs_to_keep] else "🗑️  DELETE"
                    print(f"         {j}. {keep_indicator} | ID: {doc.id[:8]}... | Size: {doc.file_size} bytes")
                    print(f"            Created: {doc.created_at} | File: {doc.filename}")
                print()

    def _choose_best_document(self, docs: List[Document], storage_path: str) -> Document:
        """
        Choose the best document to keep from a duplicate group.
        
        Logic:
        1. Check if GCS file exists and get its actual size
        2. Keep document with matching file size
        3. If no exact match or can't check GCS, keep the latest created
        """
        try:
            # Try to get actual GCS file size
            if gcs_client.is_initialized:
                try:
                    blob = gcs_client.bucket.blob(storage_path)
                    blob.reload()
                    actual_gcs_size = blob.size
                    
                    print(f"      🔍 GCS file size for {storage_path}: {actual_gcs_size} bytes")
                    
                    # Find document with matching file size
                    for doc in docs:
                        if doc.file_size == actual_gcs_size:
                            print(f"      ✅ Found document with matching size: {doc.id[:8]}...")
                            return doc
                    
                    print(f"      ⚠️  No document has matching size, choosing latest")
                    
                except Exception as e:
                    print(f"      ⚠️  Could not check GCS file size: {e}")
            
        except Exception as e:
            print(f"      ⚠️  Error checking GCS: {e}")
        
        # Fallback: choose the most recently created document
        latest_doc = max(docs, key=lambda d: d.created_at or datetime.min)
        print(f"      📅 Choosing latest document: {latest_doc.id[:8]}... (created: {latest_doc.created_at})")
        return latest_doc

    def _create_backup(self):
        """Create backup of documents to be deleted."""
        if not self.docs_to_delete:
            return
        
        print("💾 Creating backup of documents to be deleted...")
        
        self.backup_data = []
        for doc in self.docs_to_delete:
            backup_entry = {
                "id": doc.id,
                "filename": doc.filename,
                "original_filename": doc.original_filename,
                "storage_path": doc.storage_path,
                "folder_id": doc.folder_id,
                "org_id": doc.org_id,
                "file_type": doc.file_type.value if hasattr(doc.file_type, 'value') else doc.file_type,
                "file_size": doc.file_size,
                "status": doc.status.value if hasattr(doc.status, 'value') else doc.status,
                "uploaded_by": doc.uploaded_by,
                "metadata": doc.metadata,
                "is_active": doc.is_active,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
                "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
                "duplicate_reason": "same_storage_path"
            }
            self.backup_data.append(backup_entry)
        
        # Save backup to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"duplicate_storage_path_cleanup_{self.org_id}_{timestamp}.json"
        backup_path = Path(__file__).parent / backup_filename
        
        with open(backup_path, 'w') as f:
            json.dump({
                "backup_info": {
                    "org_id": self.org_id,
                    "folder_id": self.folder_id,
                    "timestamp": timestamp,
                    "cleanup_type": "duplicate_storage_path",
                    "total_documents": len(self.backup_data),
                    "duplicate_groups": len(self.duplicate_groups)
                },
                "documents": self.backup_data
            }, f, indent=2)
        
        print(f"   ✅ Backup saved to: {backup_path}")
        print(f"   📊 Backed up {len(self.backup_data)} documents")

    def _simulate_cleanup(self):
        """Simulate cleanup without actually deleting anything."""
        print("\n🧪 SIMULATION MODE - No actual deletions will be performed")
        print("=" * 60)
        
        if not self.docs_to_delete:
            print("✅ No duplicate documents to clean up!")
            return
        
        print(f"📋 Would delete {len(self.docs_to_delete)} duplicate documents:")
        print()
        
        for i, doc in enumerate(self.docs_to_delete, 1):
            print(f"   {i:2d}. DELETE: {doc.filename}")
            print(f"       Firestore ID: {doc.id}")
            print(f"       Storage Path: {doc.storage_path}")
            print(f"       Created: {doc.created_at}")
            print(f"       Size: {doc.file_size} bytes")
            print(f"       Reason: Duplicate storage_path")
            print()
        
        print(f"📊 SUMMARY:")
        print(f"   - Documents to keep: {len(self.docs_to_keep)}")
        print(f"   - Documents to delete: {len(self.docs_to_delete)}")
        print(f"   - Duplicate groups resolved: {len(self.duplicate_groups)}")
        print()
        print("💡 To perform actual cleanup, run with --live flag:")
        print(f"   python cleanup_duplicate_storage_paths.py {self.org_id} {self.folder_id or ''} --live")

    async def _perform_cleanup(self):
        """Actually delete the duplicate Firestore documents."""
        print("\n🚨 LIVE DELETION MODE - Permanently removing duplicate documents")
        print("=" * 60)
        
        if not self.docs_to_delete:
            print("✅ No duplicate documents to clean up!")
            return
        
        print(f"🗑️  Deleting {len(self.docs_to_delete)} duplicate documents...")
        print()
        
        deleted_count = 0
        errors = []
        
        collection = get_collection(f"organizations/{self.org_id}/documents")
        
        for i, doc in enumerate(self.docs_to_delete, 1):
            try:
                print(f"   {i:2d}/{len(self.docs_to_delete)} Deleting: {doc.filename} (ID: {doc.id[:8]}...)")
                print(f"       Storage Path: {doc.storage_path}")
                print(f"       Reason: Duplicate (keeping newer/correct-size document)")
                
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
        print("🧹 DUPLICATE CLEANUP SUMMARY")
        print("=" * 60)
        print(f"✅ Successfully deleted: {deleted_count} duplicate documents")
        print(f"📄 Documents remaining: {len(self.docs_to_keep)}")
        print(f"❌ Errors: {len(errors)}")
        
        if errors:
            print("\n🚨 Deletion Errors:")
            for error in errors:
                print(f"   - {error}")
        
        if deleted_count > 0:
            print(f"\n💾 Backup file contains all deleted document metadata")
            print(f"🎉 Folder should now show only {len(self.docs_to_keep)} unique documents")
            print(f"📊 Resolved {len(self.duplicate_groups)} duplicate storage path groups")

async def main():
    """Main function to run the duplicate cleanup."""
    print("Duplicate Storage Path Cleanup Tool")
    print("Removes duplicate Firestore documents that reference the same GCS file")
    print()
    
    # Parse command line arguments
    if len(sys.argv) < 2:
        print("Usage: python cleanup_duplicate_storage_paths.py <org_id> [folder_id] [--live] [--confirm]")
        print("Example: python cleanup_duplicate_storage_paths.py GUbmPT49OSDO3eFDU2r5 control-docs")
        print("Example: python cleanup_duplicate_storage_paths.py GUbmPT49OSDO3eFDU2r5 control-docs --live --confirm")
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
            print("⚠️  GCS client not initialized - will use fallback logic")
        else:
            print("✅ GCS client initialized!")
        print()
        
        # Confirm deletion if in live mode
        if not dry_run:
            print("🚨 WARNING: You are about to permanently delete duplicate documents!")
            print("This action cannot be undone!")
            print("   Add --confirm flag to proceed with deletion")
            if '--confirm' not in sys.argv:
                print("❌ Cleanup cancelled - missing --confirm flag")
                return
            print("✅ Deletion confirmed via --confirm flag")
            print()
        
        # Run cleanup
        cleanup = DuplicateStoragePathCleanup()
        await cleanup.cleanup_duplicate_storage_paths(org_id, folder_id, dry_run)
        
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