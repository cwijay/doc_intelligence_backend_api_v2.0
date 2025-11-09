#!/usr/bin/env python3
"""
Google Cloud Run Deployment Script
Document Intelligence API v1.0

This script automates the deployment of the Document Intelligence API to Google Cloud Run
with proper configuration, security, and CORS setup.

Usage:
    python deploy_to_cloudrun.py --project-id YOUR_PROJECT_ID
    python deploy_to_cloudrun.py --project-id YOUR_PROJECT_ID --region us-west1 --service-name my-api
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import yaml
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


class CloudRunDeployer:
    """Automated Google Cloud Run deployment for Document Intelligence API."""
    
    def __init__(self, project_id: str, region: str = "us-central1", 
                 service_name: str = "document-intelligence-api", env_file: Optional[str] = None,
                 interactive: bool = False):
        self.project_id = project_id
        self.region = region
        self.service_name = service_name
        self.env_file = env_file
        self.interactive = interactive
        self.image_name = f"gcr.io/{project_id}/{service_name}"
        self.required_apis = [
            "run.googleapis.com",
            "cloudbuild.googleapis.com",
            "containerregistry.googleapis.com",
            "iam.googleapis.com",
            "firestore.googleapis.com",
            "storage-component.googleapis.com"
        ]
        
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
                error_msg += f"\nError: {e.stderr}"
            self.log(error_msg, "ERROR")
            return False, ""
        except FileNotFoundError:
            self.log(f"Command not found: {command[0]}", "ERROR")
            return False, ""
    
    def check_prerequisites(self) -> bool:
        """Check if required tools are installed."""
        self.log("🔍 Checking prerequisites...", "INFO")
        
        # Check gcloud CLI
        success, version = self.run_command(["gcloud", "version"], capture_output=True, check=False)
        if not success:
            self.log("Google Cloud SDK (gcloud) is not installed", "ERROR")
            self.log("Install from: https://cloud.google.com/sdk/docs/install", "INFO")
            return False
        self.log("✓ Google Cloud SDK installed", "SUCCESS")
        
        # Check Docker
        success, version = self.run_command(["docker", "--version"], capture_output=True, check=False)
        if not success:
            self.log("Docker is not installed", "ERROR")
            self.log("Install from: https://docs.docker.com/get-docker/", "INFO")
            return False
        self.log("✓ Docker installed", "SUCCESS")
        
        # Check if Dockerfile exists
        if not Path("Dockerfile").exists():
            self.log("Dockerfile not found in current directory", "ERROR")
            return False
        self.log("✓ Dockerfile found", "SUCCESS")
        
        # Check if pyproject.toml exists (UV-based project)
        if not Path("pyproject.toml").exists():
            self.log("pyproject.toml not found", "ERROR")
            self.log("This project uses UV dependency management. Please ensure pyproject.toml exists.", "INFO")
            return False
        self.log("✓ pyproject.toml found", "SUCCESS")

        # Check if uv.lock exists
        if not Path("uv.lock").exists():
            self.log("uv.lock not found", "WARNING")
            self.log("Run 'uv sync' to generate uv.lock file", "INFO")
        else:
            self.log("✓ uv.lock found", "SUCCESS")
        
        return True
    
    def authenticate_gcloud(self) -> bool:
        """Ensure gcloud is authenticated and project is set."""
        self.log("🔐 Checking Google Cloud authentication...", "INFO")
        
        # Check current project
        success, current_project = self.run_command(
            ["gcloud", "config", "get-value", "project"], 
            capture_output=True, check=False
        )
        
        if not success or current_project != self.project_id:
            self.log(f"Setting project to {self.project_id}", "INFO")
            success, _ = self.run_command(["gcloud", "config", "set", "project", self.project_id])
            if not success:
                return False
        
        # Test authentication
        success, _ = self.run_command(
            ["gcloud", "auth", "list", "--filter=status:ACTIVE", "--format=value(account)"],
            capture_output=True, check=False
        )
        
        if not success:
            self.log("Please authenticate with Google Cloud", "WARNING")
            success, _ = self.run_command(["gcloud", "auth", "login"])
            if not success:
                return False
        
        self.log("✓ Google Cloud authenticated", "SUCCESS")
        return True
    
    def enable_apis(self) -> bool:
        """Enable required Google Cloud APIs."""
        self.log("🔌 Enabling required APIs...", "INFO")
        
        for api in self.required_apis:
            self.log(f"Enabling {api}...", "PROGRESS")
            success, _ = self.run_command(["gcloud", "services", "enable", api])
            if not success:
                self.log(f"Failed to enable {api}", "ERROR")
                return False
        
        self.log("✓ All APIs enabled", "SUCCESS")
        return True
    
    def configure_docker_auth(self) -> bool:
        """Configure Docker authentication for Google Container Registry."""
        self.log("🐳 Configuring Docker authentication...", "INFO")
        
        success, _ = self.run_command(["gcloud", "auth", "configure-docker", "--quiet"])
        if not success:
            return False
        
        self.log("✓ Docker authentication configured", "SUCCESS")
        return True
    
    def build_and_push_image(self) -> bool:
        """Build Docker image and push to Google Container Registry."""
        self.log("🏗️ Building Docker image...", "INFO")
        
        # Build image with multiple tags
        tags = [
            f"{self.image_name}:latest",
            f"{self.image_name}:{int(time.time())}"  # Timestamp tag
        ]
        
        # Force AMD64 platform for Cloud Run compatibility
        build_args = ["docker", "build", "--platform", "linux/amd64"]
        for tag in tags:
            build_args.extend(["-t", tag])
        build_args.append(".")
        
        self.log("🔧 Building for linux/amd64 platform (Cloud Run compatibility)", "INFO")
        success, _ = self.run_command(build_args)
        if not success:
            return False
        
        self.log("✓ Docker image built successfully", "SUCCESS")
        
        # Push all tags
        self.log("📤 Pushing image to Google Container Registry...", "INFO")
        for tag in tags:
            success, _ = self.run_command(["docker", "push", tag])
            if not success:
                return False
        
        self.log("✓ Image pushed to registry", "SUCCESS")
        return True
    
    def load_env_file(self, env_file: str) -> Dict[str, str]:
        """Load environment variables from .env file."""
        env_vars = {}
        
        if not os.path.exists(env_file):
            return env_vars
        
        try:
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    
                    # Skip comments and empty lines
                    if not line or line.startswith('#'):
                        continue
                    
                    # Parse KEY=VALUE format
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        
                        # Remove quotes if present
                        if value.startswith('"') and value.endswith('"'):
                            value = value[1:-1]
                        elif value.startswith("'") and value.endswith("'"):
                            value = value[1:-1]
                        
                        env_vars[key] = value
            
            self.log(f"✓ Loaded {len(env_vars)} variables from {env_file}", "SUCCESS")
            
        except Exception as e:
            self.log(f"⚠️ Error reading {env_file}: {e}", "WARNING")
        
        return env_vars
    
    def validate_required_variables(self, env_vars: Dict[str, str]) -> bool:
        """Validate that required environment variables are present."""
        required_vars = {
            "FIREBASE_PROJECT_ID": "Firebase Project ID",
            "GCP_PROJECT_ID": "Google Cloud Project ID"
        }
        
        missing_vars = []
        for var, description in required_vars.items():
            if not env_vars.get(var):
                missing_vars.append(f"{var} ({description})")
        
        if missing_vars:
            self.log("❌ Missing required environment variables:", "ERROR")
            for var in missing_vars:
                self.log(f"   • {var}", "ERROR")
            return False
        
        return True
    
    def get_environment_variables(self, env_file: Optional[str] = None) -> Dict[str, str]:
        """Get environment variables for Cloud Run deployment."""
        # Base required variables
        env_vars = {
            "ENVIRONMENT": "production",
            "FIREBASE_PROJECT_ID": self.project_id,
            "GCP_PROJECT_ID": self.project_id,
            "GOOGLE_CLOUD_PROJECT": self.project_id,  # Required for ADC
            "LOG_LEVEL": "INFO",
            "LOG_FORMAT": "json"
        }
        
        # Try to load from .env file first
        env_file_vars = {}
        env_file_used = None
        
        # Check for .env files in order of preference
        env_files_to_try = []
        if env_file:
            env_files_to_try.append(env_file)
        
        env_files_to_try.extend([
            ".env.production",
            ".env.prod", 
            ".env"
        ])
        
        for env_file_path in env_files_to_try:
            if os.path.exists(env_file_path):
                self.log(f"📄 Found environment file: {env_file_path}", "INFO")
                env_file_vars = self.load_env_file(env_file_path)
                env_file_used = env_file_path
                break
        
        # Merge environment file variables
        if env_file_vars:
            # Add relevant production variables from .env file
            production_vars = {
                "FIREBASE_DATABASE_ID", "GCS_BUCKET_NAME", "JWT_SECRET_KEY",
                "PRODUCTION_CORS_ORIGINS", "FRONTEND_DOMAIN", "CLOUD_RUN_SERVICE_URL",
                "ENABLE_CORS_DEBUG", "MAX_FILE_SIZE", "ALLOWED_FILE_TYPES",
                "DOCUMENT_UPLOAD_TIMEOUT", "GOOGLE_CLOUD_PROJECT",
                # AI/ML Service API Keys
                "OPENAI_API_KEY", "OPENAI_MODEL", "LLAMAPARSE_API_KEY",
                "PINECONE_API_KEY", "PINECONE_INDEX_NAME", "PINECONE_NAMESPACE",
                "PINECONE_ENVIRONMENT",
                # Session and auth configuration
                "JWT_ALGORITHM", "ACCESS_TOKEN_EXPIRE_MINUTES", "REFRESH_TOKEN_EXPIRE_DAYS",
                "SESSION_DURATION_HOURS", "REFRESH_SESSION_DURATION_DAYS",
                "TOKEN_GRACE_PERIOD_MINUTES", "SIGNED_URL_EXPIRATION_MINUTES"
            }
            
            loaded_vars = []
            for var in production_vars:
                if var in env_file_vars:
                    env_vars[var] = env_file_vars[var]
                    loaded_vars.append(var)
            
            if loaded_vars:
                self.log(f"⚙️ Loaded {len(loaded_vars)} variables from {env_file_used}", "SUCCESS")
                for var in loaded_vars:
                    value_display = env_vars[var]
                    if len(value_display) > 50:
                        value_display = value_display[:47] + "..."
                    self.log(f"  ✓ {var} = {value_display}", "INFO")
            
            # Interactive mode: allow overrides
            if self.interactive:
                self.log("\n🔄 Interactive mode: Override any values?", "INFO")
                self._prompt_for_overrides(env_vars)
            else:
                self.log("✨ Using environment file values directly (use --interactive to override)", "SUCCESS")
        else:
            # No environment file found - always prompt for required values
            self.log("⚙️ No environment file found. Manual configuration required:", "WARNING")
            self._prompt_for_required_values(env_vars)
        
        # Validate that we have all required variables
        if not self.validate_required_variables(env_vars):
            raise RuntimeError("Missing required environment variables")
        
        return env_vars
    
    def _prompt_for_overrides(self, env_vars: Dict[str, str]):
        """Prompt user to override environment variables in interactive mode."""
        optional_vars = {
            "GCS_BUCKET_NAME": "Document storage bucket name",
            "JWT_SECRET_KEY": "JWT secret key for authentication", 
            "PRODUCTION_CORS_ORIGINS": "Production CORS origins (JSON array)",
            "FRONTEND_DOMAIN": "Frontend domain for CORS"
        }
        
        for var, description in optional_vars.items():
            current_value = env_vars.get(var, "")
            prompt = f"Enter {var} ({description})"
            if current_value:
                prompt += f" [current: {current_value[:30]}{'...' if len(current_value) > 30 else ''}]"
            prompt += " [Enter to keep/skip]: "
            
            value = input(prompt).strip()
            if value:
                env_vars[var] = value
                self.log(f"  ✓ Updated {var}", "SUCCESS")
    
    def _prompt_for_required_values(self, env_vars: Dict[str, str]):
        """Prompt user for required environment variables when no file is found."""
        required_vars = {
            "GCS_BUCKET_NAME": "Document storage bucket name",
            "JWT_SECRET_KEY": "JWT secret key for authentication",
            "PRODUCTION_CORS_ORIGINS": "Production CORS origins (JSON array)", 
            "FRONTEND_DOMAIN": "Frontend domain for CORS"
        }
        
        self.log("Please provide the following environment variables:", "INFO")
        
        for var, description in required_vars.items():
            while True:
                value = input(f"Enter {var} ({description}): ").strip()
                if value:
                    env_vars[var] = value
                    break
                else:
                    self.log(f"Please provide a value for {var}", "WARNING")
    
    def deploy_to_cloudrun(self, env_vars: Dict[str, str]) -> bool:
        """Deploy the service to Cloud Run."""
        import tempfile
        import yaml

        self.log("🚀 Deploying to Cloud Run...", "INFO")

        # Prepare deployment command
        deploy_cmd = [
            "gcloud", "run", "deploy", self.service_name,
            "--image", f"{self.image_name}:latest",
            "--platform", "managed",
            "--region", self.region,
            "--allow-unauthenticated",
            "--memory", "1Gi",
            "--cpu", "1",
            "--concurrency", "80",
            "--max-instances", "10",
            "--timeout", "300"
        ]

        # Handle environment variables using a YAML file to avoid escaping issues
        if env_vars:
            try:
                # Create a temporary YAML file for environment variables
                with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as env_file:
                    # Write environment variables to YAML format
                    yaml.dump(env_vars, env_file, default_flow_style=False)
                    env_file_path = env_file.name

                self.log(f"Created temporary environment variables file: {env_file_path}", "INFO")

                # Log environment variables for debugging (hide sensitive values)
                self.log("Environment variables to be set:", "INFO")
                for key, value in env_vars.items():
                    if any(sensitive in key.lower() for sensitive in ['key', 'secret', 'password', 'token']):
                        display_value = value[:4] + "..." if len(value) > 4 else "***"
                    elif len(str(value)) > 100:
                        display_value = str(value)[:97] + "..."
                    else:
                        display_value = value
                    self.log(f"  {key}: {display_value}", "INFO")

                # Use --env-vars-file instead of --set-env-vars
                deploy_cmd.extend(["--env-vars-file", env_file_path])

                # Run the deployment command
                success, _ = self.run_command(deploy_cmd)

                # Clean up the temporary file
                try:
                    os.unlink(env_file_path)
                    self.log(f"Cleaned up temporary file: {env_file_path}", "INFO")
                except Exception as e:
                    self.log(f"Warning: Could not delete temporary file {env_file_path}: {e}", "WARNING")

                if not success:
                    return False

            except Exception as e:
                self.log(f"Error handling environment variables: {e}", "ERROR")
                return False
        else:
            # No environment variables, run deployment without them
            success, _ = self.run_command(deploy_cmd)
            if not success:
                return False

        self.log("✓ Service deployed successfully", "SUCCESS")
        return True
    
    def get_service_url(self) -> Optional[str]:
        """Get the deployed service URL."""
        success, url = self.run_command([
            "gcloud", "run", "services", "describe", self.service_name,
            "--platform", "managed",
            "--region", self.region,
            "--format", "value(status.url)"
        ], capture_output=True, check=False)
        
        return url if success else None
    
    def test_deployment(self) -> bool:
        """Test the deployed service."""
        self.log("🧪 Testing deployment...", "INFO")
        
        service_url = self.get_service_url()
        if not service_url:
            self.log("Could not get service URL", "ERROR")
            return False
        
        self.log(f"Service URL: {service_url}", "INFO")
        
        # Test health endpoint
        try:
            import requests
            response = requests.get(f"{service_url}/health", timeout=30)
            if response.status_code == 200:
                self.log("✓ Health check passed", "SUCCESS")
            else:
                self.log(f"Health check failed: {response.status_code}", "WARNING")
        except ImportError:
            self.log("requests library not available, skipping HTTP test", "WARNING")
        except Exception as e:
            self.log(f"Health check failed: {e}", "WARNING")
        
        return True
    
    def setup_firestore_indexes(self) -> bool:
        """Setup Firestore indexes using automated deployment."""
        self.log("📊 Setting up Firestore indexes...", "INFO")
        
        # Try Firebase CLI first (recommended method)
        if Path("firestore.indexes.json").exists():
            self.log("Using Firebase CLI for index deployment...", "INFO")
            success, _ = self.run_command([
                sys.executable, "deploy_firestore_indexes.py", 
                "--project-id", self.project_id,
                "--method", "firebase"
            ], check=False)
            
            if success:
                self.log("✓ Firestore indexes deployed with Firebase CLI", "SUCCESS")
                return True
            else:
                self.log("⚠️ Firebase CLI deployment failed, trying gcloud...", "WARNING")
                
                # Fallback to gcloud method
                success, _ = self.run_command([
                    sys.executable, "deploy_firestore_indexes.py",
                    "--project-id", self.project_id, 
                    "--method", "gcloud"
                ], check=False)
                
                if success:
                    self.log("✓ Firestore indexes deployed with gcloud CLI", "SUCCESS")
                    return True
                else:
                    self.log("⚠️ Automated index deployment failed", "WARNING")
        
        # Fallback to old method if new scripts don't exist
        if Path("create_firestore_indexes.py").exists():
            self.log("Using legacy index creation script...", "INFO")
            success, _ = self.run_command([sys.executable, "create_firestore_indexes.py"], check=False)
            if success:
                self.log("✓ Legacy index script completed", "SUCCESS")
            else:
                self.log("⚠️ Legacy index script failed", "WARNING")
        
        self.log("📋 Manual Index Creation:", "INFO")
        self.log(f"If indexes are missing, create them manually:", "INFO")
        self.log(f"1. Go to: https://console.firebase.google.com/project/{self.project_id}/firestore/indexes", "INFO")
        self.log(f"2. Or run: python deploy_firestore_indexes.py --project-id {self.project_id}", "INFO")
        
        return True
    
    def display_deployment_info(self):
        """Display deployment information and next steps."""
        service_url = self.get_service_url()
        
        print(f"\n{Colors.BOLD}{Colors.OKGREEN}🎉 Deployment Complete!{Colors.ENDC}")
        print(f"\n{Colors.BOLD}📋 Deployment Information:{Colors.ENDC}")
        print(f"   • Project ID: {self.project_id}")
        print(f"   • Service Name: {self.service_name}")
        print(f"   • Region: {self.region}")
        print(f"   • Service URL: {service_url}")
        
        print(f"\n{Colors.BOLD}🔗 API Endpoints:{Colors.ENDC}")
        print(f"   • Health Check: {service_url}/health")
        print(f"   • API Status: {service_url}/status")
        print(f"   • API Documentation: {service_url}/docs")
        print(f"   • OpenAPI Schema: {service_url}/openapi.json")
        
        print(f"\n{Colors.BOLD}📚 Next Steps:{Colors.ENDC}")
        print(f"   1. Update your frontend to use: {service_url}")
        print(f"   2. Configure custom domain (optional)")
        print(f"   3. Set up monitoring and alerting")
        print(f"   4. Test all API endpoints")
        print(f"   5. Update CORS origins for production")
        
        print(f"\n{Colors.BOLD}🛠️ Management Commands:{Colors.ENDC}")
        print(f"   • View logs: gcloud run services logs tail {self.service_name} --region={self.region}")
        print(f"   • Update service: gcloud run services update {self.service_name} --region={self.region}")
        print(f"   • Delete service: gcloud run services delete {self.service_name} --region={self.region}")
    
    def deploy(self) -> bool:
        """Main deployment workflow."""
        self.log(f"🚀 Starting deployment of {self.service_name} to Cloud Run", "INFO")
        
        steps = [
            ("Prerequisites", self.check_prerequisites),
            ("Authentication", self.authenticate_gcloud),
            ("Enable APIs", self.enable_apis),
            ("Docker Auth", self.configure_docker_auth),
            ("Build & Push", self.build_and_push_image),
            ("Deploy Service", lambda: self.deploy_to_cloudrun(self.get_environment_variables(self.env_file))),
            ("Test Deployment", self.test_deployment),
            ("Setup Indexes", self.setup_firestore_indexes)
        ]
        
        for step_name, step_func in steps:
            self.log(f"📋 Step: {step_name}", "INFO")
            if not step_func():
                self.log(f"❌ Deployment failed at step: {step_name}", "ERROR")
                return False
        
        self.display_deployment_info()
        return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Deploy Document Intelligence API to Google Cloud Run",
        epilog="""
Examples:
  # Deploy using .env.production (automatic, no prompts)
  python deploy_to_cloudrun.py --project-id my-project-123
  
  # Deploy with interactive mode (allow overrides)
  python deploy_to_cloudrun.py --project-id my-project-123 --interactive
  
  # Deploy with custom environment file
  python deploy_to_cloudrun.py --project-id my-project-123 --env-file .env.staging
  
  # Deploy to different region with custom service name
  python deploy_to_cloudrun.py --project-id my-project-123 --region us-west1 --service-name my-api

Environment File Priority:
  1. --env-file (if specified)
  2. .env.production (preferred)
  3. .env.prod (alternative) 
  4. .env (fallback)
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--project-id", 
        required=True,
        help="Google Cloud Project ID"
    )
    parser.add_argument(
        "--region",
        default="us-central1",
        help="Cloud Run region (default: us-central1)"
    )
    parser.add_argument(
        "--service-name",
        default="document-intelligence-api",
        help="Cloud Run service name (default: document-intelligence-api)"
    )
    parser.add_argument(
        "--env-file",
        help="Path to environment file (default: searches for .env.production, .env.prod, .env)"
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Enable interactive mode to override environment file values (default: use file values directly)"
    )
    
    args = parser.parse_args()
    
    deployer = CloudRunDeployer(
        project_id=args.project_id,
        region=args.region,
        service_name=args.service_name,
        env_file=args.env_file,
        interactive=args.interactive
    )
    
    success = deployer.deploy()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()