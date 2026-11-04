"""
Unit tests for MIND User-Directed Project Creation and File Operations.
Verifies authoritative destination handling, project name preservation,
real filesystem CRUD, confirmation on destructive actions, path traversal rejection,
and system-protected path enforcement.
"""

import tempfile
import pytest
from pathlib import Path

from MIND_GameDev.config import GameDevConfig
from MIND_GameDev.orchestrator import GameDevOrchestrator
from MIND_GameDev.models import ActionType, ProjectType, SafePathValidator
from MIND_GameDev.tools.workspace_files import (
    SafeWorkspaceManager,
    ConfirmationRequiredError,
    FileOverwriteError,
    WorkspaceSecurityError,
)
from MIND_GameDev.tools.instruction_parser import InstructionParser


def test_instruction_parser_destination_and_name_extraction():
    cmd = "Create a modern banking website, save the project to D:\\TheWebsite, and name it TheWebsite."
    inst = InstructionParser.parse(cmd)

    assert inst.action == ActionType.CREATE_PROJECT
    assert inst.destination_dir == "D:\\TheWebsite"
    assert inst.project_name == "TheWebsite"
    assert inst.project_type == ProjectType.WEBSITE


def test_instruction_parser_crud_actions():
    inst_list = InstructionParser.parse("List the files in this project", active_project_path="D:\\Site")
    assert inst_list.action == ActionType.LIST_FILES

    inst_read = InstructionParser.parse("Read the authentication module and explain it", active_project_path="D:\\Site")
    assert inst_read.action == ActionType.READ_FILE
    assert inst_read.target_path == "js/app.js"

    inst_update = InstructionParser.parse("Update the CSS without changing the existing JavaScript", active_project_path="D:\\Site")
    assert inst_update.action == ActionType.UPDATE_FILE
    assert inst_update.target_path == "style.css"

    inst_add = InstructionParser.parse("Add a contact page to the existing project", active_project_path="D:\\Site")
    assert inst_add.action == ActionType.ADD_PAGE
    assert inst_add.target_path == "contact.html"

    inst_rename = InstructionParser.parse("Rename old.js to new.js", active_project_path="D:\\Site")
    assert inst_rename.action == ActionType.RENAME_PATH
    assert inst_rename.target_path == "old.js"
    assert inst_rename.new_path == "new.js"

    inst_move = InstructionParser.parse("Move assets into public/assets", active_project_path="D:\\Site")
    assert inst_move.action == ActionType.MOVE_PATH

    inst_del_unconfirmed = InstructionParser.parse("Delete the generated temporary file", active_project_path="D:\\Site")
    assert inst_del_unconfirmed.action == ActionType.DELETE_PATH
    assert inst_del_unconfirmed.confirmed is False

    inst_del_confirmed = InstructionParser.parse("Delete temp.txt --force", active_project_path="D:\\Site")
    assert inst_del_confirmed.action == ActionType.DELETE_PATH
    assert inst_del_confirmed.confirmed is True


def test_explicit_destination_and_name_project_creation():
    with tempfile.TemporaryDirectory() as tmpdir:
        target_dir = Path(tmpdir) / "TheWebsite"
        cfg = GameDevConfig.load()
        cfg.test_mode = True

        orch = GameDevOrchestrator(config=cfg, enable_voice=False)
        cmd = f"Create a modern banking website, save the project to {target_dir}, and name it TheWebsite."
        plan_res = orch.execute_command(cmd)
        assert plan_res["status"] == "APPROVAL_REQUIRED"

        res = orch.execute_command("approve")
        assert res["status"] == "SUCCESS"
        assert res["project"]["name"] == "TheWebsite"
        assert Path(res["project"]["root_path"]).resolve() == target_dir.resolve()

        # Verify real files created on disk
        assert (target_dir / "index.html").exists()
        assert (target_dir / "style.css").exists()
        assert (target_dir / "js" / "main.js").exists()
        assert (target_dir / "project.json").exists()

        # Verify entry point
        assert Path(res["entry_point"]).exists()
        assert res["verification"]["success"] is True


def test_destination_collision_requires_confirmation():
    with tempfile.TemporaryDirectory() as tmpdir:
        target_dir = Path(tmpdir) / "MyProject"
        target_dir.mkdir(parents=True, exist_ok=True)
        # Seed an existing file to trigger collision
        (target_dir / "existing_data.json").write_text('{"important": true}', encoding="utf-8")

        cfg = GameDevConfig.load()
        cfg.test_mode = True
        orch = GameDevOrchestrator(config=cfg, enable_voice=False)

        # Unconfirmed creation should require confirmation
        cmd = f"Create a website in {target_dir} and name it MyProject"
        res = orch.execute_command(cmd)
        assert res["status"] == "CONFIRMATION_REQUIRED"
        assert res["conflicting_files_count"] == 1
        # Original file must NOT be destroyed
        assert (target_dir / "existing_data.json").exists()

        # Confirmed creation with --force satisfies collision safety, transitions to design approval
        cmd_force = f"Create a website in {target_dir} and name it MyProject --force"
        res_force = orch.execute_command(cmd_force)
        assert res_force["status"] == "APPROVAL_REQUIRED"

        # Explicit design approval proceeds to implementation
        res_approve = orch.execute_command("approve")
        assert res_approve["status"] == "SUCCESS"
        assert (target_dir / "index.html").exists()


def test_crud_operations_on_real_filesystem():
    with tempfile.TemporaryDirectory() as tmpdir:
        target_dir = Path(tmpdir) / "BankingApp"
        cfg = GameDevConfig.load()
        cfg.test_mode = True
        orch = GameDevOrchestrator(config=cfg, enable_voice=False)

        # 1. Create project
        plan_res = orch.execute_command(f"Create a modern banking website, save the project to {target_dir}, and name it BankingApp")
        assert plan_res["status"] == "APPROVAL_REQUIRED"
        create_res = orch.execute_command("approve")
        assert create_res["status"] == "SUCCESS"

        # 2. List files
        list_res = orch.execute_command(f"List the files in {target_dir}")
        assert list_res["status"] == "SUCCESS"
        assert "index.html" in list_res["files"]
        assert "style.css" in list_res["files"]

        # 3. Read file
        read_res = orch.execute_command(f"Read index.html in {target_dir}")
        assert read_res["status"] == "SUCCESS"
        assert "<html" in read_res["content"].lower()

        # 4. Add page
        add_res = orch.execute_command(f"Add a contact page to {target_dir}")
        assert add_res["status"] == "SUCCESS"
        assert (target_dir / "contact.html").exists()

        # 5. Rename file
        (target_dir / "old_doc.txt").write_text("Documentation content", encoding="utf-8")
        rename_res = orch.execute_command(f"Rename old_doc.txt to new_doc.txt in {target_dir}")
        assert rename_res["status"] == "SUCCESS"
        assert not (target_dir / "old_doc.txt").exists()
        assert (target_dir / "new_doc.txt").exists()
        assert (target_dir / "new_doc.txt").read_text(encoding="utf-8") == "Documentation content"

        # 6. Move file into subfolder
        (target_dir / "data.csv").write_text("col1,col2\n1,2", encoding="utf-8")
        move_res = orch.execute_command(f"Move data.csv to assets/data.csv in {target_dir}")
        assert move_res["status"] == "SUCCESS"
        assert (target_dir / "assets" / "data.csv").exists()
        assert not (target_dir / "data.csv").exists()

        # 7. Delete file - unconfirmed requires confirmation
        (target_dir / "temp.txt").write_text("temporary log", encoding="utf-8")
        del_unconfirmed = orch.execute_command(f"Delete temp.txt in {target_dir}")
        assert del_unconfirmed["status"] == "CONFIRMATION_REQUIRED"
        assert (target_dir / "temp.txt").exists()

        # 8. Delete file - confirmed deletes file
        del_confirmed = orch.execute_command(f"Delete temp.txt in {target_dir} --force")
        assert del_confirmed["status"] == "SUCCESS"
        assert not (target_dir / "temp.txt").exists()


def test_system_protected_paths_rejected():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = GameDevConfig.load()
        cfg.test_mode = True
        orch = GameDevOrchestrator(config=cfg, enable_voice=False)

        # Attempting Windows system root or drive root must be rejected
        res = orch.execute_command("Create website, save the project to C:\\Windows, and name it WindowsHack")
        assert res["status"] == "PERMISSION_DENIED"
        assert "protected system directory" in res["message"]


def test_path_traversal_and_security_containment():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws_root = Path(tmpdir) / "workspace"
        ws_root.mkdir()
        ws = SafeWorkspaceManager(ws_root)

        # Direct escape via ../
        with pytest.raises(WorkspaceSecurityError):
            ws.validate_path(ws_root / ".." / "evil.txt")

        # Prefix collision
        evil_dir = Path(tmpdir) / "workspace_evil"
        evil_dir.mkdir()
        with pytest.raises(WorkspaceSecurityError):
            ws.validate_path(evil_dir / "secret.txt")

        # Dangerous executable extensions blocked
        with pytest.raises(ValueError):
            ws.write_file("malicious.bat", "@echo off")
        with pytest.raises(ValueError):
            ws.write_file("payload.exe", b"\x00\x01")
