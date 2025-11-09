#!/usr/bin/env python3
"""
Firestore Composite Index Deployment Script
Document Intelligence API v1.0

This script deploys Firestore composite indexes using Firebase CLI or gcloud CLI.
It automatically creates all indexes required for the application's queries.

Usage:
    python deploy_firestore_indexes.py --project-id YOUR_PROJECT_ID
    python deploy_firestore_indexes.py --project-id YOUR_PROJECT_ID --method gcloud
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class Colors:
    """Console color codes for pretty output."""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


class FirestoreIndexDeployer:
    """Automated Firestore composite index deployment."""
    
    def __init__(self, project_id: str, method: str = "firebase"):
        self.project_id = project_id
        self.method = method  # "firebase" or "gcloud"
        self.indexes_file = "firestore.indexes.json"
        
    def log(self, message: str, level: str = "INFO"):
        """Log messages with colors and emojis."""
        emoji_map = {
            "INFO": "ℹ️",
            "SUCCESS": "✅", 
            "WARNING": "⚠️",
            "ERROR": "❌",
            "PROGRESS": "🔄"
        }
        
        color_map = {
            "INFO": Colors.OKBLUE,
            "SUCCESS": Colors.OKGREEN,
            "WARNING": Colors.WARNING,
            "ERROR": Colors.FAIL,
            "PROGRESS": Colors.HEADER
        }
        
        emoji = emoji_map.get(level, "")
        color = color_map.get(level, "")
        print(f"{color}{emoji} {message}{Colors.ENDC}")
    
    def run_command(self, command: List[str], capture_output: bool = False, 
                   check: bool = True) -> Tuple[bool, str]:
        """Execute shell command with error handling."""
        try:
            self.log(f"Running: {' '.join(command)}", "PROGRESS")
            
            if capture_output:
                result = subprocess.run(command, capture_output=True, text=True, check=check)
                return True, result.stdout.strip()
            else:
                result = subprocess.run(command, check=check)
                return True, ""
                
        except subprocess.CalledProcessError as e:
            error_msg = f"Command failed: {' '.join(command)}"
            if hasattr(e, 'stderr') and e.stderr:
                error_msg += f"\\nError: {e.stderr}"
            self.log(error_msg, "ERROR")
            return False, ""
        except FileNotFoundError:
            self.log(f"Command not found: {command[0]}", "ERROR")
            return False, ""
    
    def check_prerequisites(self) -> bool:
        """Check if required tools are installed."""
        self.log("🔍 Checking prerequisites...", "INFO")
        
        if self.method == "firebase":
            # Check Firebase CLI
            success, version = self.run_command(["firebase", "--version"], capture_output=True, check=False)
            if not success:
                self.log("Firebase CLI is not installed", "ERROR")
                self.log("Install with: npm install -g firebase-tools", "INFO")
                return False
            self.log("✓ Firebase CLI installed", "SUCCESS")
            
        elif self.method == "gcloud":
            # Check gcloud CLI
            success, version = self.run_command(["gcloud", "version"], capture_output=True, check=False)
            if not success:
                self.log("Google Cloud SDK (gcloud) is not installed", "ERROR")
                self.log("Install from: https://cloud.google.com/sdk/docs/install", "INFO")
                return False
            self.log("✓ Google Cloud SDK installed", "SUCCESS")
        
        # Check if indexes file exists
        if not Path(self.indexes_file).exists():
            self.log(f"{self.indexes_file} not found", "ERROR")
            return False
        self.log(f"✓ {self.indexes_file} found", "SUCCESS")
        
        return True
    
    def load_indexes_config(self) -> Optional[Dict]:
        """Load and validate the indexes configuration file."""
        try:
            with open(self.indexes_file, 'r') as f:
                config = json.load(f)
            
            if 'indexes' not in config:
                self.log("Invalid indexes file: missing 'indexes' key", "ERROR")
                return None
            
            index_count = len(config['indexes'])
            self.log(f"Loaded {index_count} composite indexes from {self.indexes_file}", "SUCCESS")
            
            return config
        except Exception as e:
            self.log(f"Failed to load {self.indexes_file}: {str(e)}", "ERROR")
            return None
    
    def deploy_with_firebase(self) -> bool:
        """Deploy indexes using Firebase CLI."""
        self.log("🚀 Deploying indexes with Firebase CLI...", "INFO")
        
        # Initialize Firebase project if needed
        if not Path(".firebaserc").exists():
            self.log("Initializing Firebase project...", "INFO")
            success, _ = self.run_command([
                "firebase", "use", "--add", self.project_id
            ])
            if not success:
                return False
        
        # Deploy indexes
        success, _ = self.run_command([
            "firebase", "deploy", "--only", "firestore:indexes", "--project", self.project_id
        ])
        
        if success:
            self.log("✓ Indexes deployed successfully with Firebase CLI", "SUCCESS")
        
        return success
    
    def deploy_with_gcloud(self) -> bool:
        """Deploy indexes using gcloud CLI."""
        self.log("🚀 Deploying indexes with gcloud CLI...", "INFO")
        
        # Load indexes configuration
        config = self.load_indexes_config()
        if not config:
            return False
        
        # Set project
        success, _ = self.run_command(["gcloud", "config", "set", "project", self.project_id])
        if not success:
            return False
        
        success_count = 0
        total_count = len(config['indexes'])
        
        for i, index in enumerate(config['indexes'], 1):
            self.log(f"Creating index {i}/{total_count} for collection '{index['collectionGroup']}'...", "INFO")
            
            # Build gcloud command
            cmd = [
                "gcloud", "firestore", "indexes", "composite", "create",
                "--collection-group", index['collectionGroup'],
                "--query-scope", index['queryScope']
            ]
            
            # Add fields
            for field in index['fields']:
                cmd.extend([
                    "--field-config",
                    f"field-path={field['fieldPath']},order={field['order']}"
                ])
            
            # Add project
            cmd.extend(["--project", self.project_id])
            
            # Execute command
            success, _ = self.run_command(cmd, check=False)
            if success:
                success_count += 1
                self.log(f"  ✓ Index {i} created successfully", "SUCCESS")
            else:
                self.log(f"  ❌ Failed to create index {i}", "ERROR")
        
        if success_count == total_count:
            self.log(f"✓ All {total_count} indexes created successfully", "SUCCESS")
            return True
        else:
            self.log(f"⚠️ Created {success_count}/{total_count} indexes", "WARNING")
            return False
    
    def check_index_status(self) -> bool:
        """Check the status of deployed indexes."""
        self.log("📊 Checking index status...", "INFO")
        
        if self.method == "firebase":
            # Firebase CLI doesn't have a direct way to check index status
            self.log("Index status check not available with Firebase CLI", "WARNING")
            self.log("Check status in Firebase Console: https://console.firebase.google.com/project/" + 
                    self.project_id + "/firestore/indexes", "INFO")
        else:
            # Use gcloud to list indexes
            success, output = self.run_command([
                "gcloud", "firestore", "indexes", "composite", "list",
                "--project", self.project_id,
                "--format", "table(name,state,queryScope)"
            ], capture_output=True, check=False)
            
            if success:
                self.log("Current index status:", "INFO")
                print(output)
            else:
                self.log("Could not retrieve index status", "WARNING")
        
        return True
    
    def deploy(self) -> bool:
        """Main deployment workflow."""
        self.log(f"🚀 Starting Firestore index deployment using {self.method.upper()}", "INFO")
        
        if not self.check_prerequisites():
            return False
        
        if self.method == "firebase":
            success = self.deploy_with_firebase()
        else:
            success = self.deploy_with_gcloud()
        
        if success:
            self.check_index_status()
            self.log("🎉 Index deployment completed!", "SUCCESS")
            self.log("📋 Next Steps:", "INFO")
            self.log("1. Wait for indexes to finish building (can take several minutes)", "INFO")
            self.log("2. Test your API endpoints", "INFO")
            self.log("3. Check Firebase Console for index status", "INFO")
        
        return success


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Deploy Firestore composite indexes",
        epilog="""
Examples:
  # Deploy using Firebase CLI (recommended)
  python deploy_firestore_indexes.py --project-id my-project-123
  
  # Deploy using gcloud CLI
  python deploy_firestore_indexes.py --project-id my-project-123 --method gcloud
  
  # Check index status
  python deploy_firestore_indexes.py --project-id my-project-123 --method gcloud
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--project-id", 
        required=True,
        help="Google Cloud Project ID"
    )
    parser.add_argument(
        "--method",
        choices=["firebase", "gcloud"],
        default="firebase",
        help="Method to use for index deployment (default: firebase)"
    )
    
    args = parser.parse_args()
    
    deployer = FirestoreIndexDeployer(
        project_id=args.project_id,
        method=args.method
    )
    
    success = deployer.deploy()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()