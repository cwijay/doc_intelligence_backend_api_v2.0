import logging
import json
from typing import Optional, Any, Dict, List
from contextlib import asynccontextmanager

import firebase_admin
from firebase_admin import credentials, firestore
from firebase_admin.firestore import SERVER_TIMESTAMP
from google.cloud.firestore import AsyncClient
from google.cloud.firestore_v1 import FieldFilter
from google.api_core.exceptions import GoogleAPIError, NotFound

from app.core.config import settings

logger = logging.getLogger(__name__)


class FirestoreErrorContext:
    """Context manager for consistent Firestore error handling and logging."""
    
    def __init__(self, operation: str, **context):
        self.operation = operation
        self.context = context
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            if isinstance(exc_val, GoogleAPIError):
                logger.error(f"Firestore {self.operation} failed", 
                           error=str(exc_val),
                           error_code=getattr(exc_val, 'code', None),
                           **self.context)
            elif isinstance(exc_val, NotFound):
                logger.warning(f"Firestore {self.operation} - resource not found",
                             **self.context)
            else:
                logger.error(f"Firestore {self.operation} failed with unexpected error",
                           error=str(exc_val),
                           error_type=type(exc_val).__name__,
                           **self.context)
        return False  # Don't suppress exceptions


class FirebaseManager:
    """Firebase/Firestore connection manager."""
    
    def __init__(self):
        self._app: Optional[firebase_admin.App] = None
        self._client: Optional[AsyncClient] = None
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize Firebase connection."""
        if self._initialized:
            logger.info("Firebase already initialized")
            return

        try:
            # Validate required configuration first
            self._validate_configuration()

            # Initialize Firebase Admin SDK
            if not firebase_admin._apps:
                cred = self._get_credentials()
                if cred:
                    self._app = firebase_admin.initialize_app(cred)
                else:
                    # Use default application credentials (for Cloud Run, etc.)
                    logger.info("No explicit Firebase credentials found. Attempting to use default application credentials (ADC)")
                    logger.warning("If you're running locally, you may need to run 'gcloud auth application-default login' or provide service account credentials")

                    # Ensure project ID is available for ADC
                    import os
                    if not os.getenv('GOOGLE_CLOUD_PROJECT') and not settings.FIREBASE_PROJECT_ID:
                        raise EnvironmentError(
                            "GOOGLE_CLOUD_PROJECT environment variable is required when using Application Default Credentials (ADC). "
                            "Either set GOOGLE_CLOUD_PROJECT or provide Firebase service account credentials."
                        )

                    self._app = firebase_admin.initialize_app()
            else:
                self._app = firebase_admin.get_app()

            # Initialize Firestore client with specific database ID
            database_id = settings.firebase_database_id
            logger.info(f"Initializing Firestore client with database ID: {database_id}")

            # Set project ID explicitly if available
            project_id = self._get_project_id()
            if project_id:
                self._client = firestore.AsyncClient(project=project_id, database=database_id)
            else:
                self._client = firestore.AsyncClient(database=database_id)

            # Test connection
            await self.health_check()

            self._initialized = True
            logger.info("Firebase initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {str(e)}")
            raise
    
    async def close(self) -> None:
        """Close Firebase connections."""
        if self._client:
            self._client.close()
            self._client = None
        
        if self._app:
            firebase_admin.delete_app(self._app)
            self._app = None
        
        self._initialized = False
        logger.info("Firebase connections closed")
    
    @property
    def client(self) -> AsyncClient:
        """Get the Firestore client."""
        if not self._initialized or not self._client:
            raise RuntimeError("Firebase not initialized")
        return self._client
    
    @property
    def is_initialized(self) -> bool:
        """Check if Firebase is initialized."""
        return self._initialized
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform Firebase health check."""
        status = {
            "firebase_initialized": self._initialized,
            "firestore_available": False,
        }
        
        if not self._initialized or not self._client:
            return status
        
        try:
            # Test Firestore connection by attempting to read a document
            # We'll try to read from a system collection
            test_doc = self._client.collection('_health_check').document('test')
            await test_doc.get()  # This will succeed even if document doesn't exist
            status["firestore_available"] = True
            
        except GoogleAPIError as e:
            logger.warning(f"Firestore health check failed: {str(e)}")
            status["error"] = str(e)
        except Exception as e:
            logger.error(f"Unexpected error in Firebase health check: {str(e)}")
            status["error"] = str(e)
        
        return status
    
    def collection(self, collection_name: str):
        """Get a collection reference."""
        if not self._client:
            raise RuntimeError("Firebase not initialized")
        return self._client.collection(collection_name)
    
    def document(self, document_path: str):
        """Get a document reference."""
        if not self._client:
            raise RuntimeError("Firebase not initialized")
        return self._client.document(document_path)
    
    def get_server_timestamp(self):
        """Get Firestore server timestamp for document updates."""
        return SERVER_TIMESTAMP
    
    @asynccontextmanager
    async def transaction(self):
        """Get a Firestore transaction context manager."""
        if not self._client:
            raise RuntimeError("Firebase not initialized")
        
        transaction = self._client.transaction()
        try:
            yield transaction
        except Exception as e:
            logger.error(f"Transaction error: {str(e)}")
            raise
    
    def _validate_configuration(self) -> None:
        """Validate Firebase configuration before initialization."""
        if not settings.FIREBASE_PROJECT_ID:
            raise EnvironmentError(
                "FIREBASE_PROJECT_ID is required. Please set it in your environment variables."
            )

        if not settings.FIREBASE_DATABASE_ID:
            logger.warning("FIREBASE_DATABASE_ID not set, using '(default)' database")

    def _get_project_id(self) -> Optional[str]:
        """Get the project ID from various sources."""
        import os

        # Priority order: env var, Firebase project ID, GCP project ID
        project_id = (
            os.getenv('GOOGLE_CLOUD_PROJECT') or
            settings.FIREBASE_PROJECT_ID or
            settings.GCP_PROJECT_ID
        )

        if project_id:
            logger.info(f"Using project ID: {project_id}")
        else:
            logger.warning("No project ID found in configuration")

        return project_id

    def _get_credentials(self):
        """Get Firebase credentials from various sources."""
        # Option 1: Service account JSON string from environment variable
        if settings.FIREBASE_SERVICE_ACCOUNT_JSON:
            try:
                service_account_info = json.loads(settings.FIREBASE_SERVICE_ACCOUNT_JSON)
                # Validate required fields
                required_fields = ['type', 'project_id', 'private_key_id', 'private_key', 'client_email', 'token_uri']
                missing_fields = [field for field in required_fields if field not in service_account_info]
                if missing_fields:
                    raise ValueError(f"Service account JSON missing required fields: {', '.join(missing_fields)}")
                
                logger.info("Using Firebase service account from JSON string")
                return credentials.Certificate(service_account_info)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid Firebase service account JSON format: {str(e)}")
                raise
            except ValueError as e:
                logger.error(f"Invalid Firebase service account JSON: {str(e)}")
                raise
        
        # Option 2: Service account file path from environment variable
        if settings.GOOGLE_APPLICATION_CREDENTIALS:
            import os
            if not os.path.exists(settings.GOOGLE_APPLICATION_CREDENTIALS):
                logger.error(f"Firebase service account file not found: {settings.GOOGLE_APPLICATION_CREDENTIALS}")
                raise FileNotFoundError(f"Service account file not found: {settings.GOOGLE_APPLICATION_CREDENTIALS}")
            
            try:
                logger.info(f"Using Firebase service account from file: {settings.GOOGLE_APPLICATION_CREDENTIALS}")
                return credentials.Certificate(settings.GOOGLE_APPLICATION_CREDENTIALS)
            except Exception as e:
                logger.error(f"Failed to load Firebase credentials from file: {str(e)}")
                raise
        
        # Option 3: Default application credentials (ADC)
        logger.info("No explicit Firebase credentials found. Attempting to use default application credentials (ADC)")
        logger.warning("If you're running locally, you may need to run 'gcloud auth application-default login' or provide service account credentials")
        return None


# Global Firebase manager instance
firebase_manager = FirebaseManager()


# Helper functions for compatibility
async def init_firebase() -> None:
    """Initialize Firebase connection."""
    await firebase_manager.initialize()


async def close_firebase() -> None:
    """Close Firebase connections."""
    await firebase_manager.close()


def get_firestore_client() -> AsyncClient:
    """Get Firestore client."""
    return firebase_manager.client


def get_collection(collection_name: str):
    """Get a Firestore collection."""
    return firebase_manager.collection(collection_name)


def get_document(document_path: str):
    """Get a Firestore document."""
    return firebase_manager.document(document_path)


async def get_firebase_health() -> Dict[str, Any]:
    """Get Firebase health status."""
    return await firebase_manager.health_check()


# Firestore utility functions
async def create_document(collection_name: str, data: Dict[str, Any], document_id: Optional[str] = None) -> str:
    """Create a document in Firestore."""
    collection = get_collection(collection_name)
    
    if document_id:
        doc_ref = collection.document(document_id)
        await doc_ref.set(data)
        return document_id
    else:
        doc_ref = await collection.add(data)
        return doc_ref.id


async def get_document_by_id(collection_name: str, document_id: str) -> Optional[Dict[str, Any]]:
    """Get a document by ID."""
    doc_ref = get_collection(collection_name).document(document_id)
    doc = await doc_ref.get()
    
    if doc.exists:
        data = doc.to_dict()
        data['id'] = doc.id
        return data
    return None


async def update_document(collection_name: str, document_id: str, data: Dict[str, Any]) -> bool:
    """Update a document."""
    try:
        doc_ref = get_collection(collection_name).document(document_id)
        await doc_ref.update(data)
        return True
    except NotFound:
        return False


async def delete_document(collection_name: str, document_id: str) -> bool:
    """Delete a document."""
    try:
        doc_ref = get_collection(collection_name).document(document_id)
        await doc_ref.delete()
        return True
    except NotFound:
        return False


async def query_documents(
    collection_name: str, 
    filters: Optional[List[FieldFilter]] = None,
    limit: Optional[int] = None,
    order_by: Optional[str] = None,
    order_direction: str = "desc"
) -> List[Dict[str, Any]]:
    """Query documents with filters."""
    query = get_collection(collection_name)
    
    if filters:
        for filter_obj in filters:
            query = query.where(filter=filter_obj)
    
    if order_by:
        from google.cloud.firestore import Query
        direction = Query.DESCENDING if order_direction.lower() == "desc" else Query.ASCENDING
        query = query.order_by(order_by, direction=direction)
    
    if limit:
        query = query.limit(limit)
    
    docs = query.stream()
    results = []
    async for doc in docs:
        data = doc.to_dict()
        data['id'] = doc.id
        results.append(data)
    
    return results