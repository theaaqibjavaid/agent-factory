"""
File Tools — Read, write, and analyze local files.

These tools provide file system operations that agents can use
to inspect and modify code during development.
"""

import os
import glob
import fnmatch
from typing import Optional, List
from agentfactory.base_tools import tool, SafetyLevel


@tool("write_text_file", category="file", safety_level=SafetyLevel.MODIFIED, tags=["file", "write", "create"])
def write_text_file(file_path: str, content: str, append: bool = False) -> str:
    """
    Write or append text to a file.

    Args:
        file_path: Absolute path to the file
        content: Text content to write
        append: If True, append to existing file (default: overwrite)

    Returns:
        Status message
    """
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        mode = "a" if append else "w"
        with open(file_path, mode, encoding="utf-8") as f:
            f.write(content)

        action = "appended to" if append else "wrote"
        return f"Successfully {action} {file_path} ({len(content)} bytes)"
    except Exception as e:
        return f"Error writing file: {str(e)}"


@tool("read_text_file", category="file", tags=["file", "read"])
def read_text_file(file_path: str, max_lines: int = 1000) -> str:
    """
    Read text content from a file.

    Args:
        file_path: Absolute path to the file
        max_lines: Maximum number of lines to read

    Returns:
        File contents or error message
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        if len(lines) > max_lines:
            return f"File truncated (showing first {max_lines} of {len(lines)} lines):\n" + "".join(lines[:max_lines])

        return "".join(lines)
    except FileNotFoundError:
        return f"File not found: {file_path}"
    except Exception as e:
        return f"Error reading file: {str(e)}"


@tool("list_directory_contents", category="file", tags=["file", "list", "scan"])
def list_directory_contents(
    directory_path: str,
    patterns: Optional[List[str]] = None,
    max_depth: int = 3,
    exclude: Optional[List[str]] = None,
) -> str:
    """
    List directory contents with optional filtering.

    Args:
        directory_path: Path to list
        patterns: List of glob patterns to match (e.g., ["*.py", "*.ts"])
        max_depth: Maximum directory depth to traverse
        exclude: Directories to exclude

    Returns:
        Formatted list of files and directories
    """
    if patterns is None:
        patterns = ["*"]
    if exclude is None:
        exclude = ["__pycache__", ".git", "node_modules", "venv", ".venv", "dist", "build"]

    results = []
    visited = set()

    def _scan(path: str, depth: int):
        if depth > max_depth or path in visited:
            return

        visited.add(path)

        try:
            for entry in os.listdir(path):
                if entry.startswith("."):
                    continue

                full_path = os.path.join(path, entry)

                if os.path.isdir(full_path):
                    if entry not in exclude:
                        results.append(f"[{dir}] {full_path}/")
                        _scan(full_path, depth + 1)
                else:
                    # Check if file matches any pattern
                    if any(fnmatch.fnmatch(entry, p) for p in patterns):
                        results.append(f"    {full_path}")
        except PermissionError:
            pass

    _scan(directory_path, 0)
    return f"Directory contents ({len(results)} items):\n" + "\n".join(results[:100])


@tool("delete_file", category="file", safety_level=SafetyLevel.DESTRUCTIVE, tags=["file", "delete"])
def delete_file(file_path: str, confirm: bool = True) -> str:
    """
    Delete a file (with confirmation safety check).

    WARNING: This operation cannot be undone.

    Args:
        file_path: Path to the file to delete
        confirm: Must be True to proceed

    Returns:
        Status message
    """
    if not confirm:
        return "File deletion requires confirmation=True"

    if not os.path.exists(file_path):
        return f"File not found: {file_path}"

    try:
        os.remove(file_path)
        return f"Deleted: {file_path}"
    except Exception as e:
        return f"Error deleting file: {str(e)}"


@tool("create_directory", category="file", safety_level=SafetyLevel.MODIFIED, tags=["file", "directory", "create"])
def create_directory(dir_path: str, exist_ok: bool = True) -> str:
    """
    Create a directory.

    Args:
        dir_path: Path to the directory to create
        exist_ok: If True, don't raise error if directory already exists

    Returns:
        Status message
    """
    try:
        os.makedirs(dir_path, exist_ok=exist_ok)
        return f"Created directory: {dir_path}"
    except Exception as e:
        return f"Error creating directory: {str(e)}"


@tool("search_files_by_pattern", category="file", tags=["file", "search", "pattern"])
def search_files_by_pattern(
    directory: str,
    pattern: str,
    max_depth: int = 5,
    exclude: Optional[List[str]] = None,
) -> str:
    """
    Search for files matching a pattern in a directory.

    Args:
        directory: Root directory to search
        pattern: Glob pattern to match (e.g., "*.py", "test_*.*")
        max_depth: Maximum directory depth to search
        exclude: Directories to exclude

    Returns:
        List of matching file paths
    """
    if exclude is None:
        exclude = ["__pycache__", ".git", "node_modules", "venv", ".venv", "dist", "build"]

    matching_files = []

    def _search(path: str, depth: int):
        if depth > max_depth:
            return

        try:
            for entry in os.listdir(path):
                if entry.startswith("."):
                    continue
                full_path = os.path.join(path, entry)

                if os.path.isdir(full_path):
                    if entry not in exclude:
                        _search(full_path, depth + 1)
                elif fnmatch.fnmatch(entry, pattern):
                    matching_files.append(full_path)
        except PermissionError:
            pass

    _search(directory, 0)

    if not matching_files:
        return f"No files matching '{pattern}' found in {directory}"

    return f"Found {len(matching_files)} files matching '{pattern}':\n" + "\n".join(matching_files[:50])


@tool("count_lines_in_file", category="file", tags=["file", "count", "analyze"])
def count_lines_in_file(file_path: str) -> str:
    """
    Count the number of lines in a file.

    Args:
        file_path: Path to the file

    Returns:
        Line count information
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            line_count = 0
            char_count = 0
            for line in f:
                line_count += 1
                char_count += len(line)

        return f"File: {file_path}\nLines: {line_count}\nCharacters: {char_count}"
    except FileNotFoundError:
        return f"File not found: {file_path}"
    except Exception as e:
        return f"Error counting lines: {str(e)}"
