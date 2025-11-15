"""
Unit tests for app/models/folder.py

Tests Folder model functionality including path operations.
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

from app.models.folder import Folder, _find_node_in_tree


class TestFolderModel:
    """Test Folder model creation and validation."""

    def test_folder_creation_with_required_fields(self, mock_folder_data):
        """Test creating folder with all required fields."""
        folder = Folder(**mock_folder_data)

        assert folder.id == "folder123"
        assert folder.org_id == "org123"
        assert folder.name == "Test Folder"
        assert folder.parent_folder_id is None
        assert folder.is_active is True

    def test_folder_creation_defaults(self):
        """Test folder creation with default values."""
        folder = Folder(
            org_id="org123",
            name="Test Folder",
            path="/Test Folder",
            created_by="user123",
        )

        assert folder.is_active is True
        assert isinstance(folder.created_at, datetime)
        assert isinstance(folder.updated_at, datetime)

    def test_folder_to_dict(self, mock_folder_data):
        """Test converting folder to dictionary."""
        folder = Folder(**mock_folder_data)
        folder_dict = folder.to_dict()

        assert "id" not in folder_dict  # ID excluded
        assert folder_dict["org_id"] == "org123"
        assert folder_dict["name"] == "Test Folder"
        assert isinstance(folder_dict["created_at"], str)  # ISO format

    def test_folder_from_dict(self, mock_folder_data):
        """Test creating folder from dictionary."""
        folder = Folder.from_dict(mock_folder_data, doc_id="folder123")

        assert folder.id == "folder123"
        assert folder.org_id == "org123"
        assert folder.name == "Test Folder"


class TestFolderNameValidation:
    """Test folder name validation."""

    def test_valid_folder_name(self):
        """Test creating folder with valid name."""
        folder = Folder(
            org_id="org123",
            name="Valid Folder Name",
            path="/Valid Folder Name",
            created_by="user123",
        )

        assert folder.name == "Valid Folder Name"

    def test_folder_name_empty_raises_error(self):
        """Test that empty folder name raises error."""
        with pytest.raises(ValidationError) as exc_info:
            Folder(
                org_id="org123",
                name="",
                path="/",
                created_by="user123",
            )

        assert "Folder name cannot be empty" in str(exc_info.value)

    def test_folder_name_whitespace_only_raises_error(self):
        """Test that whitespace-only name raises error."""
        with pytest.raises(ValidationError) as exc_info:
            Folder(
                org_id="org123",
                name="   ",
                path="/",
                created_by="user123",
            )

        assert "Folder name cannot be empty" in str(exc_info.value)

    def test_folder_name_too_long_raises_error(self):
        """Test that overly long folder name raises error."""
        long_name = "a" * 256

        with pytest.raises(ValidationError) as exc_info:
            Folder(
                org_id="org123",
                name=long_name,
                path=f"/{long_name}",
                created_by="user123",
            )

        assert "must be between 1 and 255 characters" in str(exc_info.value)

    def test_folder_name_with_slash_raises_error(self):
        """Test that folder name with slash raises error."""
        with pytest.raises(ValidationError) as exc_info:
            Folder(
                org_id="org123",
                name="Invalid/Name",
                path="/Invalid/Name",
                created_by="user123",
            )

        assert "cannot contain" in str(exc_info.value)

    def test_folder_name_with_invalid_chars_raises_error(self):
        """Test that folder name with invalid characters raises error."""
        invalid_names = ["name:test", "name*test", "name?test", 'name"test']

        for invalid_name in invalid_names:
            with pytest.raises(ValidationError):
                Folder(
                    org_id="org123",
                    name=invalid_name,
                    path=f"/{invalid_name}",
                    created_by="user123",
                )

    def test_folder_name_dot_raises_error(self):
        """Test that folder name '.' raises error."""
        with pytest.raises(ValidationError) as exc_info:
            Folder(
                org_id="org123",
                name=".",
                path="/.",
                created_by="user123",
            )

        assert "cannot be '.' or '..'" in str(exc_info.value)

    def test_folder_name_dotdot_raises_error(self):
        """Test that folder name '..' raises error."""
        with pytest.raises(ValidationError) as exc_info:
            Folder(
                org_id="org123",
                name="..",
                path="/..",
                created_by="user123",
            )

        assert "cannot be '.' or '..'" in str(exc_info.value)


class TestFolderPathValidation:
    """Test folder path validation."""

    def test_valid_folder_path(self):
        """Test creating folder with valid path."""
        folder = Folder(
            org_id="org123",
            name="Test",
            path="/Test",
            created_by="user123",
        )

        assert folder.path == "/Test"

    def test_folder_path_empty_raises_error(self):
        """Test that empty path raises error."""
        with pytest.raises(ValidationError) as exc_info:
            Folder(
                org_id="org123",
                name="Test",
                path="",
                created_by="user123",
            )

        assert "Folder path cannot be empty" in str(exc_info.value)

    def test_folder_path_without_leading_slash_raises_error(self):
        """Test that path without leading slash raises error."""
        with pytest.raises(ValidationError) as exc_info:
            Folder(
                org_id="org123",
                name="Test",
                path="Test",
                created_by="user123",
            )

        assert "must start with '/'" in str(exc_info.value)

    def test_folder_path_max_depth_raises_error(self):
        """Test that path exceeding max depth raises error."""
        deep_path = "/level1/level2/level3/level4/level5/level6"

        with pytest.raises(ValidationError) as exc_info:
            Folder(
                org_id="org123",
                name="level6",
                path=deep_path,
                created_by="user123",
            )

        assert "Maximum folder nesting depth is 5 levels" in str(exc_info.value)


class TestFolderProperties:
    """Test folder properties and computed values."""

    def test_depth_property_root(self):
        """Test depth property for root folder."""
        folder = Folder(
            org_id="org123",
            name="Root",
            path="/Root",
            created_by="user123",
        )

        assert folder.depth == 1

    def test_depth_property_nested(self):
        """Test depth property for nested folder."""
        folder = Folder(
            org_id="org123",
            name="Sub",
            parent_folder_id="parent123",
            path="/Parent/Sub",
            created_by="user123",
        )

        assert folder.depth == 2

    def test_parent_path_property_root(self):
        """Test parent_path for root folder."""
        folder = Folder(
            org_id="org123",
            name="Root",
            path="/Root",
            created_by="user123",
        )

        assert folder.parent_path is None

    def test_parent_path_property_nested(self):
        """Test parent_path for nested folder."""
        folder = Folder(
            org_id="org123",
            name="Sub",
            parent_folder_id="parent123",
            path="/Parent/Sub",
            created_by="user123",
        )

        assert folder.parent_path == "/Parent"

    def test_is_root_property_true(self):
        """Test is_root property for root folder."""
        folder = Folder(
            org_id="org123",
            name="Root",
            path="/Root",
            created_by="user123",
        )

        assert folder.is_root is True

    def test_is_root_property_false(self):
        """Test is_root property for non-root folder."""
        folder = Folder(
            org_id="org123",
            name="Sub",
            parent_folder_id="parent123",
            path="/Parent/Sub",
            created_by="user123",
        )

        assert folder.is_root is False


class TestFolderMethods:
    """Test folder methods."""

    def test_update_timestamp(self, mock_folder_data):
        """Test updating timestamp."""
        folder = Folder(**mock_folder_data)
        original_updated_at = folder.updated_at

        # Wait and update
        import time
        time.sleep(0.01)
        folder.update_timestamp()

        assert folder.updated_at > original_updated_at

    def test_calculate_path_root(self):
        """Test calculating path for root folder."""
        folder = Folder(
            org_id="org123",
            name="Root",
            path="/temp",
            created_by="user123",
        )

        path = folder.calculate_path(None)

        assert path == "/Root"

    def test_calculate_path_nested(self):
        """Test calculating path for nested folder."""
        folder = Folder(
            org_id="org123",
            name="Sub",
            parent_folder_id="parent123",
            path="/temp",
            created_by="user123",
        )

        path = folder.calculate_path("/Parent")

        assert path == "/Parent/Sub"

    def test_update_path(self):
        """Test updating folder path."""
        folder = Folder(
            org_id="org123",
            name="Test",
            path="/old/path",
            created_by="user123",
        )

        folder.update_path("/new/parent")

        assert folder.path == "/new/parent/Test"

    def test_can_be_moved_to_root(self):
        """Test that folder can be moved to root."""
        folder = Folder(
            org_id="org123",
            name="Test",
            path="/Parent/Test",
            created_by="user123",
        )

        assert folder.can_be_moved_to(None) is True

    def test_cannot_be_moved_to_itself(self):
        """Test that folder cannot be moved to itself."""
        folder = Folder(
            org_id="org123",
            name="Test",
            path="/Parent/Test",
            created_by="user123",
        )

        assert folder.can_be_moved_to("/Parent/Test") is False

    def test_cannot_be_moved_to_descendant(self):
        """Test that folder cannot be moved to its descendant."""
        folder = Folder(
            org_id="org123",
            name="Parent",
            path="/Parent",
            created_by="user123",
        )

        assert folder.can_be_moved_to("/Parent/Child") is False

    def test_cannot_be_moved_if_exceeds_depth(self):
        """Test that folder cannot be moved if it exceeds max depth."""
        folder = Folder(
            org_id="org123",
            name="Test",
            path="/Test",
            created_by="user123",
        )

        deep_path = "/a/b/c/d/e"  # Already at depth 5

        assert folder.can_be_moved_to(deep_path) is False


class TestFolderStaticMethods:
    """Test folder static methods."""

    def test_generate_id(self):
        """Test generating folder ID."""
        id1 = Folder.generate_id()
        id2 = Folder.generate_id()

        assert isinstance(id1, str)
        assert isinstance(id2, str)
        assert id1 != id2

    def test_normalize_path_empty(self):
        """Test normalizing empty path."""
        assert Folder.normalize_path("") == "/"

    def test_normalize_path_adds_leading_slash(self):
        """Test normalizing path adds leading slash."""
        assert Folder.normalize_path("test") == "/test"

    def test_normalize_path_removes_double_slashes(self):
        """Test normalizing path removes double slashes."""
        assert Folder.normalize_path("/test//path///folder") == "/test/path/folder"

    def test_normalize_path_removes_trailing_slash(self):
        """Test normalizing path removes trailing slash."""
        assert Folder.normalize_path("/test/path/") == "/test/path"


class TestFolderTreeStructure:
    """Test folder tree building."""

    def test_build_tree_structure_single_root(self):
        """Test building tree with single root folder."""
        folder = Folder(
            id="folder1",
            org_id="org123",
            name="Root",
            path="/Root",
            created_by="user123",
        )

        tree = Folder.build_tree_structure([folder])

        assert "folder1" in tree
        assert tree["folder1"]["folder"] == folder
        assert len(tree["folder1"]["children"]) == 0

    def test_build_tree_structure_with_children(self):
        """Test building tree with parent and children."""
        root = Folder(
            id="root",
            org_id="org123",
            name="Root",
            path="/Root",
            created_by="user123",
        )
        child = Folder(
            id="child",
            org_id="org123",
            name="Child",
            parent_folder_id="root",
            path="/Root/Child",
            created_by="user123",
        )

        tree = Folder.build_tree_structure([root, child])

        assert "root" in tree
        assert "child" in tree["root"]["children"]
