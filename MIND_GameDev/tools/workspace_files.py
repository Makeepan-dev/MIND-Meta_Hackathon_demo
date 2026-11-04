"""Safe Workspace Manager.

Enforces canonical path containment, prevents directory traversal, forbids
prefix-collision bypasses (e.g. 'workspace-evil'), protects against unintended
overwrites, and blocks dangerous executable extensions.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..models import SafePathValidator


class WorkspaceSecurityError(PermissionError):
    """Raised when an operation attempts to breach workspace boundaries."""
    pass


class FileOverwriteError(FileExistsError):
    """Raised when writing to an existing file without explicit overwrite approval."""
    pass


class ConfirmationRequiredError(PermissionError):
    """Raised when a destructive operation is requested without explicit confirmation."""
    pass


DANGEROUS_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".dll", ".vbs", ".ps1", ".com", ".scr", ".msi", ".pif"
}


class SafeWorkspaceManager:
    """Manages workspace operations within an explicit, contained root."""

    def __init__(
        self,
        workspace_root: str | Path,
        max_file_size_bytes: int = 10 * 1024 * 1024,
        approval_handler: Optional[Callable[[str, str, Dict[str, Any]], bool]] = None,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.max_file_size_bytes = max_file_size_bytes
        self.approval_handler = approval_handler
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    @property
    def base_directory(self) -> Path:
        """Alias property for workspace_root."""
        return self.workspace_root

    def is_path_safe(self, target_path: str | Path) -> bool:
        """Determines if a target path strictly resides within the workspace root."""
        try:
            SafePathValidator.validate_containment(Path(target_path), self.workspace_root)
            return True
        except (PermissionError, ValueError, RuntimeError):
            return False

    def validate_path(self, target_path: str | Path) -> Path:
        """Validates that a path is safe and returns its canonical resolved Path."""
        try:
            return SafePathValidator.validate_containment(Path(target_path), self.workspace_root)
        except PermissionError as e:
            raise WorkspaceSecurityError(str(e)) from e

    def create_directory(self, sub_dir: str | Path) -> Path:
        """Safely creates a directory within workspace boundaries."""
        p = Path(sub_dir)
        target = p if p.is_absolute() else self.workspace_root / p
        canonical = self.validate_path(target)
        canonical.mkdir(parents=True, exist_ok=True)
        return canonical

    def write_file(
        self,
        relative_or_absolute_path: str | Path,
        content: str | bytes,
        overwrite: bool = False,
        requester: str = "gamedev_workflow",
    ) -> Dict[str, Any]:
        """Safely writes a file to disk inside the workspace."""
        p = Path(relative_or_absolute_path)
        if p.suffix.lower() in DANGEROUS_EXTENSIONS:
            raise ValueError(f"Writing executable or dangerous files with extension '{p.suffix}' is forbidden.")

        target_path = p if p.is_absolute() else self.workspace_root / p
        canonical = self.validate_path(target_path)

        # Check existing file overwrite protection
        if canonical.exists() and not overwrite:
            approved = False
            if self.approval_handler:
                approved = self.approval_handler(
                    requester,
                    "overwrite_file",
                    {"path": str(canonical), "existing_size": canonical.stat().st_size},
                )
            if not approved:
                raise FileOverwriteError(
                    f"File '{canonical}' already exists. Overwrite permission was not granted."
                )

        # Enforce size constraints
        size = len(content) if isinstance(content, (bytes, bytearray)) else len(content.encode("utf-8"))
        if size > self.max_file_size_bytes:
            raise ValueError(
                f"Content size ({size} bytes) exceeds maximum permitted file size ({self.max_file_size_bytes} bytes)."
            )

        canonical.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(content, (bytes, bytearray)):
            canonical.write_bytes(content)
        else:
            canonical.write_text(content, encoding="utf-8")

        rel_path = str(canonical.relative_to(self.workspace_root))
        return {
            "success": True,
            "absolute_path": str(canonical),
            "relative_path": rel_path,
            "bytes_written": size,
        }

    def read_file(
        self,
        relative_or_absolute_path: str | Path,
        as_bytes: bool = False,
    ) -> str | bytes:
        """Reads a file safely from inside the workspace."""
        p = Path(relative_or_absolute_path)
        target_path = p if p.is_absolute() else self.workspace_root / p
        canonical = self.validate_path(target_path)

        if not canonical.exists():
            raise FileNotFoundError(f"File not found: {canonical}")
        if not canonical.is_file():
            raise IsADirectoryError(f"Path is a directory, not a file: {canonical}")

        size = canonical.stat().st_size
        if size > self.max_file_size_bytes:
            raise ValueError(f"File size ({size} bytes) exceeds safe read limit ({self.max_file_size_bytes} bytes).")

        if as_bytes:
            return canonical.read_bytes()
        return canonical.read_text(encoding="utf-8", errors="replace")

    def list_files(
        self,
        sub_dir: str | Path = "",
        recursive: bool = True,
        max_entries: int = 500,
    ) -> List[Path]:
        """Lists file Paths safely within a subdirectory of the workspace."""
        p = Path(sub_dir)
        target_dir = p if p.is_absolute() else self.workspace_root / p
        canonical_dir = self.validate_path(target_dir)

        if not canonical_dir.exists():
            return []

        results: List[Path] = []
        iterator = canonical_dir.rglob("*") if recursive else canonical_dir.glob("*")

        for item in iterator:
            if item.is_file():
                results.append(item)
                if len(results) >= max_entries:
                    break

        return results

    def file_exists(self, relative_or_absolute_path: str | Path) -> bool:
        """Checks if a file exists safely within workspace boundaries."""
        try:
            p = Path(relative_or_absolute_path)
            target_path = p if p.is_absolute() else self.workspace_root / p
            canonical = self.validate_path(target_path)
            return canonical.exists()
        except WorkspaceSecurityError:
            return False

    def update_file(
        self,
        relative_or_absolute_path: str | Path,
        content: str | bytes,
        append: bool = False,
        overwrite: bool = True,
        requester: str = "user",
    ) -> Dict[str, Any]:
        """Safely updates or appends to a file on disk."""
        p = Path(relative_or_absolute_path)
        if p.suffix.lower() in DANGEROUS_EXTENSIONS:
            raise ValueError(f"Writing executable or dangerous files with extension '{p.suffix}' is forbidden.")

        target_path = p if p.is_absolute() else self.workspace_root / p
        canonical = self.validate_path(target_path)

        if not canonical.exists():
            if append:
                raise FileNotFoundError(f"Cannot append to non-existent file: {canonical}")
            return self.write_file(canonical, content, overwrite=True, requester=requester)

        if not canonical.is_file():
            raise IsADirectoryError(f"Target path is a directory, not a file: {canonical}")

        if append:
            if isinstance(content, (bytes, bytearray)):
                existing = canonical.read_bytes()
                new_data = existing + content
                if len(new_data) > self.max_file_size_bytes:
                    raise ValueError(f"Updated file size exceeds maximum limit of {self.max_file_size_bytes} bytes.")
                canonical.write_bytes(new_data)
                written = len(content)
            else:
                existing = canonical.read_text(encoding="utf-8", errors="replace")
                new_data = existing + content
                if len(new_data.encode("utf-8")) > self.max_file_size_bytes:
                    raise ValueError(f"Updated file size exceeds maximum limit of {self.max_file_size_bytes} bytes.")
                canonical.write_text(new_data, encoding="utf-8")
                written = len(content.encode("utf-8"))
        else:
            if isinstance(content, (bytes, bytearray)):
                if len(content) > self.max_file_size_bytes:
                    raise ValueError(f"Content size exceeds maximum limit of {self.max_file_size_bytes} bytes.")
                canonical.write_bytes(content)
                written = len(content)
            else:
                if len(content.encode("utf-8")) > self.max_file_size_bytes:
                    raise ValueError(f"Content size exceeds maximum limit of {self.max_file_size_bytes} bytes.")
                canonical.write_text(content, encoding="utf-8")
                written = len(content.encode("utf-8"))

        rel_path = str(canonical.relative_to(self.workspace_root))
        return {
            "success": True,
            "absolute_path": str(canonical),
            "relative_path": rel_path,
            "bytes_written": written,
            "operation": "append" if append else "update",
        }

    def rename_path(
        self,
        old_path: str | Path,
        new_path: str | Path,
        overwrite: bool = False,
        requester: str = "user",
    ) -> Dict[str, Any]:
        """Safely renames or moves a file or directory within the workspace."""
        canonical_old = self.validate_path(Path(old_path) if Path(old_path).is_absolute() else self.workspace_root / old_path)
        canonical_new = self.validate_path(Path(new_path) if Path(new_path).is_absolute() else self.workspace_root / new_path)

        if not canonical_old.exists():
            raise FileNotFoundError(f"Source path not found: {canonical_old}")

        if canonical_new.exists() and not overwrite:
            raise FileOverwriteError(f"Destination '{canonical_new}' already exists. Overwrite permission was not granted.")

        canonical_new.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(canonical_old), str(canonical_new))

        return {
            "success": True,
            "old_path": str(canonical_old),
            "new_path": str(canonical_new),
            "relative_path": str(canonical_new.relative_to(self.workspace_root)),
        }

    def move_path(
        self,
        src_path: str | Path,
        dst_path: str | Path,
        overwrite: bool = False,
        requester: str = "user",
    ) -> Dict[str, Any]:
        """Safely moves a file or directory into a destination directory within the workspace."""
        canonical_src = self.validate_path(Path(src_path) if Path(src_path).is_absolute() else self.workspace_root / src_path)
        canonical_dst = self.validate_path(Path(dst_path) if Path(dst_path).is_absolute() else self.workspace_root / dst_path)

        if not canonical_src.exists():
            raise FileNotFoundError(f"Source path not found: {canonical_src}")

        if canonical_dst.exists() and canonical_dst.is_dir():
            target = canonical_dst / canonical_src.name
        else:
            target = canonical_dst

        if target.exists() and not overwrite:
            raise FileOverwriteError(f"Target '{target}' already exists. Overwrite permission was not granted.")

        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(canonical_src), str(target))

        return {
            "success": True,
            "src_path": str(canonical_src),
            "target_path": str(target),
            "relative_path": str(target.relative_to(self.workspace_root)),
        }

    def delete_file(
        self,
        relative_or_absolute_path: str | Path,
        force: bool = False,
        requester: str = "user",
    ) -> Dict[str, Any]:
        """Safely deletes a file within the workspace, requiring confirmation if not force."""
        canonical = self.validate_path(Path(relative_or_absolute_path) if Path(relative_or_absolute_path).is_absolute() else self.workspace_root / relative_or_absolute_path)

        if not canonical.exists():
            raise FileNotFoundError(f"File not found: {canonical}")

        if not canonical.is_file():
            raise IsADirectoryError(f"Path is a directory, not a file: {canonical}. Use delete_directory instead.")

        if not force:
            approved = False
            if self.approval_handler:
                approved = self.approval_handler(requester, "delete_file", {"path": str(canonical)})
            if not approved:
                raise ConfirmationRequiredError(
                    f"Destructive action requires confirmation: Deleting file '{canonical}'."
                )

        size = canonical.stat().st_size
        canonical.unlink()
        return {
            "success": True,
            "deleted_path": str(canonical),
            "size_freed_bytes": size,
        }

    def delete_directory(
        self,
        relative_or_absolute_path: str | Path,
        force: bool = False,
        recursive: bool = True,
        requester: str = "user",
    ) -> Dict[str, Any]:
        """Safely deletes a directory within the workspace, requiring confirmation if not force."""
        canonical = self.validate_path(Path(relative_or_absolute_path) if Path(relative_or_absolute_path).is_absolute() else self.workspace_root / relative_or_absolute_path)

        if not canonical.exists():
            raise FileNotFoundError(f"Directory not found: {canonical}")

        if not canonical.is_dir():
            raise NotADirectoryError(f"Path is a file, not a directory: {canonical}. Use delete_file instead.")

        # Extra safety check: Cannot delete system protected paths
        if SafePathValidator.is_system_protected_path(canonical):
            raise WorkspaceSecurityError(f"Cannot delete system-protected directory: '{canonical}'.")

        if not force:
            approved = False
            if self.approval_handler:
                approved = self.approval_handler(requester, "delete_directory", {"path": str(canonical)})
            if not approved:
                raise ConfirmationRequiredError(
                    f"Destructive action requires confirmation: Deleting directory '{canonical}'."
                )

        count = len(list(canonical.rglob("*"))) if canonical.exists() else 0
        if recursive:
            shutil.rmtree(canonical)
        else:
            canonical.rmdir()

        return {
            "success": True,
            "deleted_path": str(canonical),
            "items_deleted": count,
        }

    def detect_conflicts(self, proposed_files: List[str]) -> List[str]:
        """Returns list of proposed file paths that already exist on disk."""
        conflicts = []
        for f in proposed_files:
            try:
                target = Path(f) if Path(f).is_absolute() else self.workspace_root / f
                if target.exists():
                    conflicts.append(str(target))
            except Exception:
                pass
        return conflicts

    def inspect_structure(self, sub_dir: str | Path = "") -> Dict[str, Any]:
        """Provides a detailed structural summary of files, directories, and sizes."""
        target_dir = self.validate_path(Path(sub_dir) if Path(sub_dir).is_absolute() else self.workspace_root / sub_dir)
        if not target_dir.exists():
            return {"exists": False, "files": [], "directories": [], "total_size_bytes": 0}

        files_info = []
        dirs_info = []
        total_size = 0

        for root, dirs, files in os.walk(target_dir):
            r_path = Path(root)
            for d in dirs:
                dirs_info.append(str((r_path / d).relative_to(self.workspace_root)))
            for f in files:
                f_path = r_path / f
                try:
                    st = f_path.stat()
                    total_size += st.st_size
                    files_info.append({
                        "name": f,
                        "relative_path": str(f_path.relative_to(self.workspace_root)),
                        "size_bytes": st.st_size,
                        "modified_at": st.st_mtime,
                        "extension": f_path.suffix.lower(),
                    })
                except OSError:
                    pass

        return {
            "exists": True,
            "workspace_root": str(self.workspace_root),
            "relative_root": str(target_dir.relative_to(self.workspace_root)) if target_dir != self.workspace_root else "",
            "files": files_info,
            "directories": dirs_info,
            "total_files": len(files_info),
            "total_directories": len(dirs_info),
            "total_size_bytes": total_size,
        }

    def create_checkpoint(self, name: str) -> Path:
        """
        Snapshots current workspace files to an internal checkpoint directory,
        enabling safe rollback if subsequent repairs fail or introduce regressions.
        """
        clean_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name)
        chk_dir = self.workspace_root / ".mind_checkpoints" / clean_name
        chk_dir.mkdir(parents=True, exist_ok=True)

        for item in self.workspace_root.rglob("*"):
            if ".mind_checkpoints" in item.parts:
                continue
            rel = item.relative_to(self.workspace_root)
            dest = chk_dir / rel
            if item.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
            elif item.is_file():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dest)

        return chk_dir

    def restore_checkpoint(self, name: str) -> bool:
        """Restores workspace files from a previously saved checkpoint snapshot."""
        clean_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name)
        chk_dir = self.workspace_root / ".mind_checkpoints" / clean_name
        if not chk_dir.exists() or not chk_dir.is_dir():
            return False

        for item in chk_dir.rglob("*"):
            rel = item.relative_to(chk_dir)
            target = self.workspace_root / rel
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            elif item.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)

        return True

    def list_checkpoints(self) -> List[str]:
        """Lists available checkpoint snapshots."""
        chks_root = self.workspace_root / ".mind_checkpoints"
        if not chks_root.exists():
            return []
        return [d.name for d in chks_root.iterdir() if d.is_dir()]
