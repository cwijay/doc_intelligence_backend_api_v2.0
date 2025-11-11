"""
Document API modules.

This package contains the refactored document API endpoints, split into focused modules
following SOLID principles for better maintainability and testability.
"""

# Make the router available at package level for backward compatibility
# Import from the parent-level documents.py file since documents_main.py doesn't exist
from ..documents import router

__all__ = ["router"]
