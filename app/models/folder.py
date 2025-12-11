import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator


class Folder(BaseModel):
    """Folder model for hierarchical document organization."""

    # Primary key
    id: Optional[str] = Field(None, description="Unique folder identifier")

    # Multi-tenancy
    org_id: str = Field(..., description="Organization ID (foreign key)")

    # Core fields
    name: str = Field(..., description="Folder name (unique within parent)")
    parent_folder_id: Optional[str] = Field(
        None, description="Parent folder ID (null for root folders)"
    )
    path: str = Field(
        ..., description="Full folder path (e.g., /root/folder1/subfolder)"
    )

    # Metadata
    created_by: str = Field(..., description="User ID who created the folder")

    # Status
    is_active: bool = Field(
        default=True, description="Whether folder is active (for soft delete)"
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When folder was created",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When folder was last updated",
    )

    model_config = ConfigDict()

    @field_serializer("created_at", "updated_at")
    def serialize_datetime(self, value: datetime) -> str:
        """Serialize datetime fields to ISO format."""
        return value.isoformat() if value else None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate folder name."""
        if not v or not v.strip():
            raise ValueError("Folder name cannot be empty")

        v = v.strip()

        # Check length
        if len(v) < 1 or len(v) > 255:
            raise ValueError("Folder name must be between 1 and 255 characters")

        # Check for invalid characters (no slashes, backslashes, or special chars that could break paths)
        invalid_chars = ["/", "\\", ":", "*", "?", '"', "<", ">", "|", "\n", "\r", "\t"]
        for char in invalid_chars:
            if char in v:
                raise ValueError(f"Folder name cannot contain '{char}'")

        # Cannot be just dots (. or ..)
        if v in [".", ".."]:
            raise ValueError("Folder name cannot be '.' or '..'")

        return v

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        """Validate folder path."""
        if not v:
            raise ValueError("Folder path cannot be empty")

        # Path should start with /
        if not v.startswith("/"):
            raise ValueError("Folder path must start with '/'")

        # Check path depth (maximum 5 levels)
        path_parts = [part for part in v.split("/") if part]
        if len(path_parts) > 5:
            raise ValueError("Maximum folder nesting depth is 5 levels")

        return v

    def __repr__(self) -> str:
        return f"<Folder(id={self.id}, name='{self.name}', org_id='{self.org_id}', path='{self.path}')>"

    def to_dict(self) -> Dict[str, Any]:
        """Convert folder to dictionary for database storage."""
        data = self.model_dump(exclude={"id"})
        # Convert datetime objects to ISO format
        if "created_at" in data:
            data["created_at"] = self.created_at.isoformat()
        if "updated_at" in data:
            data["updated_at"] = self.updated_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any], doc_id: Optional[str] = None) -> "Folder":
        """Create Folder from database record."""
        # Handle datetime parsing
        if "created_at" in data and isinstance(data["created_at"], str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if "updated_at" in data and isinstance(data["updated_at"], str):
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])

        # Add document ID if provided
        if doc_id:
            data["id"] = doc_id

        return cls(**data)

    @property
    def depth(self) -> int:
        """Get folder depth (number of levels)."""
        return len([part for part in self.path.split("/") if part])

    @property
    def parent_path(self) -> Optional[str]:
        """Get parent folder path."""
        if self.parent_folder_id is None:
            return None

        path_parts = [part for part in self.path.split("/") if part]
        if len(path_parts) <= 1:
            return None

        parent_parts = path_parts[:-1]
        return "/" + "/".join(parent_parts)

    @property
    def is_root(self) -> bool:
        """Check if this is a root folder."""
        return self.parent_folder_id is None

    def update_timestamp(self):
        """Update the updated_at timestamp."""
        self.updated_at = datetime.now(timezone.utc)

    def calculate_path(self, parent_path: Optional[str] = None) -> str:
        """
        Calculate the full path for this folder.

        Args:
            parent_path: Path of the parent folder (if any)

        Returns:
            Full path for this folder
        """
        if parent_path is None or parent_path == "/":
            return f"/{self.name}"
        else:
            return f"{parent_path}/{self.name}"

    def update_path(self, new_parent_path: Optional[str] = None):
        """
        Update the folder path based on new parent.

        Args:
            new_parent_path: New parent folder path
        """
        self.path = self.calculate_path(new_parent_path)
        self.update_timestamp()

    def can_be_moved_to(self, target_parent_path: Optional[str]) -> bool:
        """
        Check if this folder can be moved to target parent.

        Args:
            target_parent_path: Target parent folder path

        Returns:
            True if move is valid, False otherwise
        """
        if target_parent_path is None:
            # Moving to root is always allowed
            return True

        # Cannot move to itself or its own descendants
        if target_parent_path.startswith(self.path):
            return False

        # Check depth after move
        target_depth = len([part for part in target_parent_path.split("/") if part]) + 1
        if target_depth > 5:
            return False

        return True

    @staticmethod
    def generate_id() -> str:
        """Generate a new folder ID."""
        return str(uuid.uuid4())

    @staticmethod
    def normalize_path(path: str) -> str:
        """
        Normalize a folder path.

        Args:
            path: Raw folder path

        Returns:
            Normalized path
        """
        if not path:
            return "/"

        # Ensure starts with /
        if not path.startswith("/"):
            path = "/" + path

        # Remove double slashes and trailing slashes
        parts = [part for part in path.split("/") if part]
        if not parts:
            return "/"

        return "/" + "/".join(parts)

    @staticmethod
    def build_tree_structure(folders: List["Folder"]) -> Dict[str, Any]:
        """
        Build a tree structure from a flat list of folders.

        Args:
            folders: List of folder objects

        Returns:
            Nested dictionary representing folder tree
        """
        # Create lookup dictionary
        folder_dict = {folder.id: folder for folder in folders if folder.id}

        # Build tree
        tree = {}

        # First pass: add root folders
        for folder in folders:
            if folder.is_root:
                tree[folder.id] = {"folder": folder, "children": {}}

        # Second pass: add child folders
        for folder in folders:
            if not folder.is_root and folder.parent_folder_id in folder_dict:
                # Find the parent in the tree
                parent_node = _find_node_in_tree(tree, folder.parent_folder_id)
                if parent_node:
                    parent_node["children"][folder.id] = {
                        "folder": folder,
                        "children": {},
                    }

        return tree


def _find_node_in_tree(
    tree: Dict[str, Any], folder_id: str
) -> Optional[Dict[str, Any]]:
    """
    Find a node in the folder tree by folder ID.

    Args:
        tree: Folder tree structure
        folder_id: ID of folder to find

    Returns:
        Node dictionary if found, None otherwise
    """
    # Check root level
    if folder_id in tree:
        return tree[folder_id]

    # Search recursively
    for node in tree.values():
        result = _find_node_in_tree(node["children"], folder_id)
        if result:
            return result

    return None
