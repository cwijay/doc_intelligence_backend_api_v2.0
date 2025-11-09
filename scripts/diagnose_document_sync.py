#!/usr/bin/env python3
"""
Diagnostic script to analyze Firestore-GCS document sync issues.
Compares Firestore document metadata with actual GCS files to identify inconsistencies.
"""

import asyncio
import sys
from pathlib import Path
from typing import List, Dict, Any, Set, Tuple
import json

# Add the app directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.firebase_client import firebase_manager
from app.core.gcs_client import gcs_client
from app.services.document_service import document_service
from app.models.schemas import PaginationParams, DocumentFilters
from app.models.document import Document

class DocumentSyncDiagnostic:
    """Diagnose sync issues between Firestore documents and GCS files."""
    
    def __init__(self):
        self.firestore_docs: List[Document] = []
        self.gcs_files: List[str] = []
        self.orphaned_firestore: List[Document] = []
        self.orphaned_gcs: List[str] = []
        self.matched_pairs: List[Tuple[Document, str]] = []

    async def analyze_organization_documents(self, org_id: str, folder_id: str = None):
        """
        Analyze documents for a specific organization and optionally a specific folder.
        
        Args:
            org_id: Organization ID to analyze
            folder_id: Optional folder ID to filter by
        """
        print(f"🔍 Analyzing documents for organization: {org_id}")
        if folder_id:
            print(f"📁 Filtering by folder_id: {folder_id}")
        print("=" * 80)
        
        # Get Firestore documents
        await self._get_firestore_documents(org_id, folder_id)
        
        # Get GCS files 
        await self._get_gcs_files(org_id, folder_id)
        
        # Compare and find mismatches
        self._compare_firestore_gcs()
        
        # Generate report
        self._generate_report()

    async def _get_firestore_documents(self, org_id: str, folder_id: str = None):
        """Get all documents from Firestore for the organization."""
        print("📊 Fetching Firestore documents...")
        
        try:
            pagination = PaginationParams(page=1, per_page=100)  # Get many documents (max 100)
            filters = None
            if folder_id:
                filters = DocumentFilters(folder_id=folder_id)
            
            result = await document_service.list_documents(org_id, pagination, filters)
            self.firestore_docs = result.documents
            
            print(f"   ✅ Found {len(self.firestore_docs)} documents in Firestore")
            
            # Display document details
            for i, doc in enumerate(self.firestore_docs, 1):
                print(f"   {i:2d}. ID: {doc.id[:8]}... | File: {doc.filename} | Storage: {doc.storage_path}")
                print(f"       Folder ID: {doc.folder_id} | Status: {doc.status} | Size: {doc.file_size} bytes")
                print(f"       Created: {doc.created_at} | Active: {doc.is_active}")
                print()
                
        except Exception as e:
            print(f"   ❌ Error fetching Firestore documents: {e}")
            self.firestore_docs = []

    async def _get_gcs_files(self, org_id: str, folder_id: str = None):
        """Get all files from GCS for the organization."""
        print("☁️  Fetching GCS files...")
        
        if not gcs_client.is_initialized:
            print("   ❌ GCS client not initialized")
            return
        
        try:
            # List files in the organization's original folder
            if folder_id:
                # Try to get organization name for proper path construction
                org_name = await self._get_org_name_from_firestore_docs(org_id)
                if org_name:
                    prefix = f"{org_name}/original/{folder_id}/"
                else:
                    # Fallback: search all files and filter later
                    prefix = ""
            else:
                prefix = ""
            
            # Use GCS client to list files
            blobs = list(gcs_client.bucket.list_blobs(prefix=prefix))
            
            self.gcs_files = []
            for blob in blobs:
                # Skip folder placeholders
                if not blob.name.endswith(('.keep', '.folder_placeholder')):
                    self.gcs_files.append(blob.name)
            
            print(f"   ✅ Found {len(self.gcs_files)} files in GCS")
            
            # Display file details
            for i, file_path in enumerate(self.gcs_files, 1):
                blob = gcs_client.bucket.blob(file_path)
                try:
                    blob.reload()
                    size = blob.size or 0
                    created = blob.time_created.isoformat() if blob.time_created else "Unknown"
                    print(f"   {i:2d}. Path: {file_path}")
                    print(f"       Size: {size} bytes | Created: {created}")
                    print()
                except Exception as e:
                    print(f"   {i:2d}. Path: {file_path} (Error getting details: {e})")
                    print()
                    
        except Exception as e:
            print(f"   ❌ Error fetching GCS files: {e}")
            self.gcs_files = []

    async def _get_org_name_from_firestore_docs(self, org_id: str) -> str:
        """Extract organization name from Firestore documents or organization service."""
        # Try to get from documents first
        if self.firestore_docs:
            for doc in self.firestore_docs:
                if doc.storage_path:
                    # Extract org name from storage path: "OrgName/original/folder/file"
                    parts = doc.storage_path.split('/')
                    if len(parts) >= 2:
                        return parts[0]
        
        # Fallback: try to get from organization service
        try:
            from app.services.org_service import organization_service
            org = await organization_service.get_organization(org_id)
            return org.name
        except Exception:
            return None

    def _compare_firestore_gcs(self):
        """Compare Firestore documents with GCS files to find mismatches."""
        print("🔗 Comparing Firestore documents with GCS files...")
        
        # Create sets for comparison
        firestore_paths = {doc.storage_path for doc in self.firestore_docs if doc.storage_path}
        gcs_paths = set(self.gcs_files)
        
        print(f"   📊 Firestore storage paths: {len(firestore_paths)}")
        print(f"   📊 GCS file paths: {len(gcs_paths)}")
        
        # Find orphaned Firestore documents (no corresponding GCS file)
        for doc in self.firestore_docs:
            if doc.storage_path in gcs_paths:
                # Found matching pair
                self.matched_pairs.append((doc, doc.storage_path))
            else:
                # Orphaned Firestore document
                self.orphaned_firestore.append(doc)
        
        # Find orphaned GCS files (no corresponding Firestore document)
        for gcs_path in gcs_paths:
            if gcs_path not in firestore_paths:
                self.orphaned_gcs.append(gcs_path)
        
        print(f"   ✅ Matched pairs: {len(self.matched_pairs)}")
        print(f"   🚨 Orphaned Firestore documents: {len(self.orphaned_firestore)}")
        print(f"   🚨 Orphaned GCS files: {len(self.orphaned_gcs)}")

    def _generate_report(self):
        """Generate a detailed sync analysis report."""
        print("\n" + "=" * 80)
        print("📋 DOCUMENT SYNC ANALYSIS REPORT")
        print("=" * 80)
        
        print(f"📊 SUMMARY")
        print(f"   Total Firestore documents: {len(self.firestore_docs)}")
        print(f"   Total GCS files: {len(self.gcs_files)}")
        print(f"   Matched pairs: {len(self.matched_pairs)}")
        print(f"   Orphaned Firestore documents: {len(self.orphaned_firestore)}")
        print(f"   Orphaned GCS files: {len(self.orphaned_gcs)}")
        print()
        
        # Matched pairs
        if self.matched_pairs:
            print("✅ PROPERLY SYNCED DOCUMENTS")
            print("-" * 40)
            for i, (doc, gcs_path) in enumerate(self.matched_pairs, 1):
                print(f"   {i}. {doc.filename}")
                print(f"      Firestore ID: {doc.id}")
                print(f"      GCS Path: {gcs_path}")
                print(f"      Size: {doc.file_size} bytes")
                print()
        
        # Orphaned Firestore documents
        if self.orphaned_firestore:
            print("🚨 ORPHANED FIRESTORE DOCUMENTS (NO CORRESPONDING GCS FILE)")
            print("-" * 60)
            print("   These Firestore documents should probably be deleted:")
            for i, doc in enumerate(self.orphaned_firestore, 1):
                print(f"   {i}. {doc.filename}")
                print(f"      Firestore ID: {doc.id}")
                print(f"      Expected GCS Path: {doc.storage_path}")
                print(f"      Folder ID: {doc.folder_id}")
                print(f"      Created: {doc.created_at}")
                print(f"      Status: {doc.status}")
                print()
        
        # Orphaned GCS files
        if self.orphaned_gcs:
            print("🚨 ORPHANED GCS FILES (NO CORRESPONDING FIRESTORE DOCUMENT)")
            print("-" * 60)
            print("   These GCS files don't have Firestore metadata:")
            for i, gcs_path in enumerate(self.orphaned_gcs, 1):
                print(f"   {i}. {gcs_path}")
                print()
        
        # Recommendations
        print("💡 RECOMMENDATIONS")
        print("-" * 20)
        
        if self.orphaned_firestore:
            print(f"   1. DELETE {len(self.orphaned_firestore)} orphaned Firestore documents")
            print("      These are taking up space and causing incorrect counts in API responses")
            
        if self.orphaned_gcs:
            print(f"   2. CREATE Firestore metadata for {len(self.orphaned_gcs)} orphaned GCS files")
            print("      OR delete the GCS files if they're not needed")
            
        if not self.orphaned_firestore and not self.orphaned_gcs:
            print("   🎉 No sync issues found! Firestore and GCS are perfectly synced.")
        
        print("\n📋 Next Steps:")
        if self.orphaned_firestore:
            print("   - Run the cleanup script to remove orphaned Firestore documents")
            print("   - Backup document IDs before deletion")
        if self.orphaned_gcs:
            print("   - Decide whether to create metadata or delete orphaned GCS files")
        print("   - Fix the upload process to prevent future sync issues")

async def main():
    """Main function to run the diagnostic."""
    print("Document Sync Diagnostic Tool")
    print("Analyzes sync between Firestore documents and GCS files")
    print()
    
    # Check command line arguments
    if len(sys.argv) < 2:
        print("Usage: python diagnose_document_sync.py <org_id> [folder_id]")
        print("Example: python diagnose_document_sync.py GUbmPT49OSDO3eFDU2r5")
        print("Example: python diagnose_document_sync.py GUbmPT49OSDO3eFDU2r5 control-docs")
        sys.exit(1)
    
    org_id = sys.argv[1]
    folder_id = sys.argv[2] if len(sys.argv) > 2 else None
    
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
        
        # Run diagnostic
        diagnostic = DocumentSyncDiagnostic()
        await diagnostic.analyze_organization_documents(org_id, folder_id)
        
    except KeyboardInterrupt:
        print("\n⏹️  Diagnostic interrupted by user")
    except Exception as e:
        print(f"❌ Diagnostic failed: {e}")
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