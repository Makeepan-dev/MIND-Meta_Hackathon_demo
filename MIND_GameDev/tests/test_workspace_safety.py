"""
Unit tests for SafeWorkspaceManager and SafePathValidator:
Ensures directory containment, blocks directory traversal attacks,
prevents prefix collisions, enforces overwrite flags and extension whitelists.
"""

import os
import tempfile
import pytest
from pathlib import Path

from MIND_GameDev.tools.workspace_files import SafeWorkspaceManager
from MIND_GameDev.models import SafePathValidator


def test_safe_path_resolution_within_workspace():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir).resolve()
        resolved = SafePathValidator.validate_containment(base / "js" / "game.js", base)
        assert resolved == (base / "js" / "game.js").resolve()


def test_traversal_attack_blocked():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir).resolve()
        with pytest.raises(PermissionError):
            SafePathValidator.validate_containment(base / ".." / "system.ini", base)

        with pytest.raises(PermissionError):
            SafePathValidator.validate_containment(base / "subdir" / ".." / ".." / "secret.txt", base)


def test_prefix_collision_blocked():
    """Validates that a directory named `workspace_evil` is NOT treated as inside `workspace`."""
    with tempfile.TemporaryDirectory() as tmpdir:
        parent = Path(tmpdir).resolve()
        base = parent / "workspace"
        base.mkdir()
        evil = parent / "workspace_evil"
        evil.mkdir()

        with pytest.raises(PermissionError):
            SafePathValidator.validate_containment(evil / "file.txt", base)


def test_dangerous_extension_rejection():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = SafeWorkspaceManager(Path(tmpdir))
        with pytest.raises(ValueError):
            ws.write_file("trojan.exe", "binary")
        with pytest.raises(ValueError):
            ws.write_file("script.bat", "echo off")
        with pytest.raises(ValueError):
            ws.write_file("lib.dll", "bytes")


def test_overwrite_protection():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = SafeWorkspaceManager(Path(tmpdir))
        ws.write_file("file.txt", "Initial content")

        # Overwrite=False must raise FileExistsError
        with pytest.raises(FileExistsError):
            ws.write_file("file.txt", "New content", overwrite=False)

        # Overwrite=True should succeed
        ws.write_file("file.txt", "Updated content", overwrite=True)
        assert ws.read_file("file.txt") == "Updated content"


def test_directory_creation_and_listing():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = SafeWorkspaceManager(Path(tmpdir))
        ws.create_directory("assets/models")
        ws.write_file("assets/models/character.obj", "v 0 0 0\n")

        files = ws.list_files("assets/models")
        assert len(files) == 1
        assert files[0].name == "character.obj"
