import unittest
import asyncio
import tempfile
import shutil
import logging
from pathlib import Path

# Import the specific tool function to test
# Ensure the path is correct relative to the project structure when running tests
try:
    from agent_system.tools.filesystem import create_directory
except ImportError:
    # If running tests from a different structure, adjust path temporarily
    import sys
    SCRIPT_DIR = Path(__file__).parent.parent.parent.resolve() # Go up to agent_system_project
    sys.path.insert(0, str(SCRIPT_DIR))
    from agent_system.tools.filesystem import create_directory

# Configure logging for tests (optional, can help debugging)
# logging.basicConfig(level=logging.DEBUG)


class TestFilesystemTools(unittest.TestCase):
    """Tests for functions in agent_system.tools.filesystem."""

    def setUp(self):
        """Set up a temporary directory for test files/dirs."""
        # Create a unique temporary directory for each test run
        self.test_dir = Path(tempfile.mkdtemp(prefix="agent_test_fs_"))
        logging.info(f"Created temporary test directory: {self.test_dir}")

    def tearDown(self):
        """Remove the temporary directory after tests."""
        if self.test_dir.exists():
            try:
                shutil.rmtree(self.test_dir)
                logging.info(f"Removed temporary test directory: {self.test_dir}")
            except Exception as e:
                logging.error(f"Failed to remove temporary test directory {self.test_dir}: {e}")

    def run_async(self, coro):
        """Helper method to run an async function within a sync test."""
        # For Python 3.7+, asyncio.run works well for simple cases.
        # For more complex async tests, consider unittest.IsolatedAsyncioTestCase (3.8+) or pytest-asyncio.
        return asyncio.run(coro)

    def test_create_directory_success(self):
        """Test successful creation of a new directory."""
        new_dir_path = self.test_dir / "new_subdir"
        expected_message = f"Successfully created directory (or it already existed): {new_dir_path}"

        # Ensure directory does NOT exist initially
        self.assertFalse(new_dir_path.exists(), f"Test setup failed: Directory {new_dir_path} already exists.")

        # Run the async tool function
        result = self.run_async(create_directory(str(new_dir_path)))

        # Assertions
        self.assertTrue(new_dir_path.exists(), f"Directory {new_dir_path} was not created.")
        self.assertTrue(new_dir_path.is_dir(), f"Path {new_dir_path} exists but is not a directory.")
        # Check the return message (allow for slight variations if path representation changes)
        self.assertTrue(result.startswith("Successfully created directory"), f"Unexpected success message: {result}")
        self.assertIn(str(new_dir_path), result, "Success message did not contain the directory path.")


    def test_create_directory_idempotent(self):
        """Test creating a directory that already exists."""
        existing_dir_path = self.test_dir / "already_exists"
        existing_dir_path.mkdir() # Create it first
        expected_message = f"Successfully created directory (or it already existed): {existing_dir_path}"

        # Ensure directory DOES exist initially
        self.assertTrue(existing_dir_path.exists(), f"Test setup failed: Directory {existing_dir_path} could not be created.")
        self.assertTrue(existing_dir_path.is_dir())

        # Run the async tool function again
        result = self.run_async(create_directory(str(existing_dir_path)))

        # Assertions
        self.assertTrue(existing_dir_path.exists(), f"Directory {existing_dir_path} should still exist.")
        self.assertTrue(existing_dir_path.is_dir())
        # Check the return message
        self.assertTrue(result.startswith("Successfully created directory"), f"Unexpected success message: {result}")
        self.assertIn(str(existing_dir_path), result, "Success message did not contain the directory path.")


    def test_create_directory_nested(self):
        """Test creating nested directories (parents=True)."""
        nested_dir_path = self.test_dir / "parent" / "child" / "grandchild"
        expected_message = f"Successfully created directory (or it already existed): {nested_dir_path}"

        # Ensure directory does NOT exist initially
        self.assertFalse(nested_dir_path.exists())
        self.assertFalse(nested_dir_path.parent.exists())
        self.assertFalse(nested_dir_path.parent.parent.exists())

        # Run the async tool function
        result = self.run_async(create_directory(str(nested_dir_path)))

        # Assertions
        self.assertTrue(nested_dir_path.exists(), f"Nested directory {nested_dir_path} was not created.")
        self.assertTrue(nested_dir_path.is_dir())
        # Check the return message
        self.assertTrue(result.startswith("Successfully created directory"), f"Unexpected success message: {result}")
        self.assertIn(str(nested_dir_path), result, "Success message did not contain the directory path.")

    # --- Tests for other filesystem tools can be added here ---
    # Example placeholder structure for read_file test
    # def test_read_file_success(self):
    #     test_file = self.test_dir / "read_test.txt"
    #     content = "Hello\nWorld!"
    #     test_file.write_text(content)
    #
    #     result = self.run_async(read_file(str(test_file)))
    #
    #     self.assertIn("Content of", result)
    #     self.assertIn(content, result)
    #
    # def test_read_file_not_found(self):
    #     non_existent_file = self.test_dir / "not_a_real_file.txt"
    #
    #     result = self.run_async(read_file(str(non_existent_file)))
    #
    #     self.assertTrue(result.startswith("Error: File not found"))


if __name__ == '__main__':
    # This allows running the tests directly using `python -m tests.tools.test_filesystem`
    unittest.main()
