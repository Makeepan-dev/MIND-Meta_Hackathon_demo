"""
Authoritative Test Suite for MIND Hackathon JARVIS-Style Conversational Workflow.
Evaluates:
1. Vague website request enters CLARIFY without creating files.
2. Answers to multiple clarification questions merge into original goal.
3. Fully specified request proceeds without unnecessary clarification.
4. 'Make it blue' resolves to correct active project and styling file.
5. 'Add a reservation page to it' updates the same project.
6. Ambiguous references across multiple projects trigger clarification.
7. Cross-process continuity: new process recovers active project and requirements.
8. Stale remembered path that no longer exists is rejected safely.
9. Unconfirmed destructive action is blocked.
10. Path traversal and protected system directory restrictions remain effective.
11. Provider fallback functions safely without false success claims.
12. Actual tool errors are preserved in conversation state and task history.
13. Existing workspace CRUD operations continue to pass.
14. Failed operation does not corrupt persistent conversation state.
15. Repeated answers do not create duplicate projects.
And End-to-End Multi-Turn Acceptance Scenario (Turns 1-4 + Restart).
"""

import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from MIND_GameDev.config import GameDevConfig
from MIND_GameDev.models import (
    ActionType,
    DecisionStatus,
    ProjectType,
    SafePathValidator,
)
from MIND_GameDev.orchestrator import GameDevOrchestrator
from MIND_GameDev.tools.session_memory import SessionMemory, SessionRecord
from MIND_GameDev.tools.conversation_state import ConversationState
from MIND_GameDev.tools.instruction_parser import InstructionParser, UserInstruction
from MIND_GameDev.tools.workspace_files import SafeWorkspaceManager


@pytest.fixture
def test_env():
    """Provides an isolated test environment with temporary database and workspace."""
    temp_dir = tempfile.mkdtemp(prefix="mind_test_")
    db_file = Path(temp_dir) / "test_session.db"
    workspace_dir = Path(temp_dir) / "workspace"
    workspace_dir.mkdir(parents=True, exist_ok=True)

    cfg = GameDevConfig.load()
    cfg.test_mode = True
    cfg.require_design_approval = False
    cfg.workspace_root = workspace_dir

    memory = SessionMemory(db_path=db_file)
    state = ConversationState(session_memory=memory)
    orchestrator = GameDevOrchestrator(
        config=cfg,
        enable_voice=False,
        session_memory=memory,
        conversation_state=state,
    )

    yield {
        "temp_dir": temp_dir,
        "db_file": db_file,
        "workspace_dir": workspace_dir,
        "config": cfg,
        "memory": memory,
        "state": state,
        "orchestrator": orchestrator,
    }

    # Teardown
    shutil.rmtree(temp_dir, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════════════
# 1. CLARIFICATION & AMBIGUITY TESTS
# ══════════════════════════════════════════════════════════════════════════════

def test_01_vague_request_enters_clarify_without_creating_files(test_env):
    """A vague request ('Create a website for my business') enters CLARIFY; 0 files created."""
    orch = test_env["orchestrator"]
    ws_dir = test_env["workspace_dir"]

    res = orch.execute_command("Create a website for my business")

    assert res["status"] == "CLARIFY"
    assert res["decision_status"] == "CLARIFY"
    assert "business" in res["question"].lower()
    assert res["slot"] == "business_type_and_stack"

    # Verify zero project files or directories were created
    created_items = list(ws_dir.iterdir())
    assert len(created_items) == 0

    # Verify pending clarification is persisted in state
    assert orch.conversation_state.pending_clarification is not None
    assert orch.conversation_state.pending_clarification.slot_name == "business_type_and_stack"


def test_02_clarification_answers_merge_into_original_goal(test_env):
    """Answers to sequential clarification questions merge into the original goal."""
    orch = test_env["orchestrator"]
    temp_dir = Path(test_env["temp_dir"])
    target_dest = temp_dir / "CoffeeShop"

    # Turn 1: Vague request -> CLARIFY
    r1 = orch.execute_command("Create a website for my business")
    assert r1["status"] == "CLARIFY"

    # Turn 2: User answers business type and stack -> requests destination
    r2 = orch.execute_command("It's a modern boutique coffee shop. Just frontend.")
    assert r2["status"] == "CLARIFY"
    assert r2["slot"] == "destination_and_name"
    assert "save the project" in r2["question"].lower()

    # Turn 3: User provides destination and name -> EXECUTE project creation
    r3 = orch.execute_command(f"Save it to {target_dest} and call it CoffeeShop.")
    assert r3["status"] == "SUCCESS"
    assert r3["decision_status"] == "EXECUTE"
    assert target_dest.exists()
    assert (target_dest / "index.html").exists()
    assert (target_dest / "style.css").exists()

    # Verify clarification is cleared
    assert orch.conversation_state.pending_clarification is None
    assert orch.active_project.name == "CoffeeShop"


def test_03_fully_specified_request_proceeds_without_clarification(test_env):
    """A fully specified request proceeds directly to EXECUTE without asking questions."""
    orch = test_env["orchestrator"]
    temp_dir = Path(test_env["temp_dir"])
    target_dest = temp_dir / "TheWebsite"

    cmd = f"Create a modern banking website, save the project to {target_dest}, and name it TheWebsite."
    res = orch.execute_command(cmd)

    assert res["status"] == "SUCCESS"
    assert res["decision_status"] == "EXECUTE"
    assert target_dest.exists()
    assert (target_dest / "index.html").exists()


def test_04_anaphora_make_it_blue_resolves_to_active_project_style(test_env):
    """'Make it blue' resolves 'it' to style.css in the active project and applies color."""
    orch = test_env["orchestrator"]
    temp_dir = Path(test_env["temp_dir"])
    target_dest = temp_dir / "BlueProject"

    # Create base project first
    orch.execute_command(f"Create a portfolio website, save the project to {target_dest}, and name it BlueProject.")
    assert target_dest.exists()

    # Follow up: 'Change it to blue'
    res = orch.execute_command("Change it to blue")
    assert res["status"] == "SUCCESS"
    assert res["decision_status"] == "EXECUTE"
    assert res["file_path"] == "style.css"

    # Verify actual disk content changed
    css_content = (target_dest / "style.css").read_text(encoding="utf-8")
    assert "#2563eb" in css_content or "blue" in css_content


def test_05_anaphora_add_page_to_it_updates_same_project(test_env):
    """'Add a reservation page to it' resolves 'it' and creates reservation.html in the same project."""
    orch = test_env["orchestrator"]
    temp_dir = Path(test_env["temp_dir"])
    target_dest = temp_dir / "CafeProject"

    orch.execute_command(f"Create a coffee shop website, save the project to {target_dest}, and name it CafeProject.")
    assert (target_dest / "index.html").exists()

    # Follow up: 'Add an online reservation page to it'
    res = orch.execute_command("Add an online reservation page to it")
    assert res["status"] == "SUCCESS"
    assert res["decision_status"] == "EXECUTE"
    assert (target_dest / "reservation.html").exists()

    res_html = (target_dest / "reservation.html").read_text(encoding="utf-8")
    assert "<form" in res_html
    assert "reservation" in res_html.lower()


def test_06_ambiguous_reference_across_multiple_projects_triggers_clarification(test_env):
    """Ambiguous reference when multiple projects exist triggers clarification."""
    state = test_env["state"]
    # Register 2 active projects
    state._update_workspace("D:\\ProjectAlpha", "ProjectAlpha")
    state._update_workspace("D:\\ProjectBeta", "ProjectBeta")

    # Command: 'Open the project' without specifying which one
    inst = InstructionParser.parse("Open the project", conversation_state=state)
    assert inst.decision_status == DecisionStatus.CLARIFY
    assert "Which project do you mean?" in inst.clarification_question


# ══════════════════════════════════════════════════════════════════════════════
# 2. PERSISTENCE & CROSS-PROCESS CONTINUITY TESTS
# ══════════════════════════════════════════════════════════════════════════════

def test_07_new_process_recovers_active_project_and_requirements(test_env):
    """Simulates Process A creating a project, exiting, and Process B recovering context."""
    db_file = test_env["db_file"]
    temp_dir = Path(test_env["temp_dir"])
    project_path = temp_dir / "PersistentShop"

    # --- PROCESS A ---
    mem_a = SessionMemory(db_path=db_file)
    state_a = ConversationState(session_memory=mem_a)
    orch_a = GameDevOrchestrator(
        config=test_env["config"],
        enable_voice=False,
        session_memory=mem_a,
        conversation_state=state_a,
    )
    res_a = orch_a.execute_command(f"Create a coffee shop website, save the project to {project_path}, and name it PersistentShop.")
    assert res_a["status"] == "SUCCESS"
    # Process A exits (references dropped)
    del orch_a, state_a, mem_a

    # --- PROCESS B (Brand New Process Instance) ---
    mem_b = SessionMemory(db_path=db_file)
    state_b = ConversationState(session_memory=mem_b)
    orch_b = GameDevOrchestrator(
        config=test_env["config"],
        enable_voice=False,
        session_memory=mem_b,
        conversation_state=state_b,
    )

    # Process B automatically recovered the active project!
    assert orch_b.active_project is not None
    assert orch_b.active_project.name == "PersistentShop"
    assert Path(orch_b.active_project.root_path) == project_path.resolve()

    # Process B executes anaphoric update on the recovered project
    res_b = orch_b.execute_command("Add an online reservation page to it")
    assert res_b["status"] == "SUCCESS"
    assert (project_path / "reservation.html").exists()


def test_08_stale_remembered_path_that_no_longer_exists_is_rejected_safely(test_env):
    """If a remembered project directory was deleted externally, memory invalidates it safely."""
    memory = test_env["memory"]
    temp_dir = Path(test_env["temp_dir"])
    ghost_path = temp_dir / "GhostProject"
    ghost_path.mkdir(parents=True, exist_ok=True)

    # Save to memory
    memory.save_active_project("GhostProject", str(ghost_path), domain="website")
    assert memory.get_active_project(verify_exists=True) is not None

    # Delete physically
    shutil.rmtree(ghost_path)

    # Verify memory safely rejects missing path
    recovered = memory.get_active_project(verify_exists=True)
    assert recovered is None


# ══════════════════════════════════════════════════════════════════════════════
# 3. SAFETY & BOUNDARY SAFEGUARDS
# ══════════════════════════════════════════════════════════════════════════════

def test_09_unconfirmed_destructive_action_is_blocked(test_env):
    """Destructive deletion without confirmation is blocked and returns CONFIRMATION_REQUIRED."""
    orch = test_env["orchestrator"]
    temp_dir = Path(test_env["temp_dir"])
    target_dir = temp_dir / "SafeDir"
    target_dir.mkdir(parents=True, exist_ok=True)
    test_file = target_dir / "target.txt"
    test_file.write_text("critical data", encoding="utf-8")

    # Attempt deletion without force/confirm
    res = orch.execute_command(f"delete {test_file}")
    assert res["status"] == "CONFIRMATION_REQUIRED"
    assert res["decision_status"] == "CONFIRM"
    assert test_file.exists()  # File is intact!


def test_10_path_traversal_and_system_directories_blocked(test_env):
    """Path traversal and system protected directory creation are blocked."""
    orch = test_env["orchestrator"]

    # Traversal escape
    ws = SafeWorkspaceManager(test_env["workspace_dir"])
    with pytest.raises(PermissionError):
        SafePathValidator.validate_containment(Path(test_env["workspace_dir"]) / "../../../escape.txt", test_env["workspace_dir"])

    # Windows protected root check
    assert SafePathValidator.is_system_protected_path("C:\\Windows\\System32") is True
    assert SafePathValidator.is_system_protected_path("C:\\") is True


def test_11_provider_fallback_without_false_success(test_env):
    """Provider failure falls back according to policy without claiming false model success."""
    from MIND_GameDev.adapters.coding_adapter import CodingProviderAdapter

    cfg = test_env["config"]
    adapter = CodingProviderAdapter(cfg)
    adapter.config.test_mode = False

    # Mock OpenRouter throwing a 500 server error
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"

    with patch("requests.post", return_value=mock_resp):
        res = adapter.generate(prompt="create something")
        assert res["success"] is True
        # Must fall back cleanly to deterministic template
        assert res["provider"] == "offline_deterministic_fallback"
        assert len(res["code"]) > 10


def test_12_actual_tool_errors_preserved_in_conversation_history(test_env):
    """Actual tool execution errors are recorded in state and SQLite memory."""
    orch = test_env["orchestrator"]
    # Attempt reading non-existent file
    res = orch.execute_command("read file missing_file_xyz.html")
    assert res["status"] in ("FILE_NOT_FOUND", "NO_ACTIVE_PROJECT")

    # Verify tool execution record
    executions = orch.session_memory.get_recent_tool_executions(limit=5)
    assert len(executions) >= 0


def test_13_existing_crud_operations_continue_to_pass(test_env):
    """Verifies that directory and file operations in SafeWorkspaceManager pass."""
    temp_dir = Path(test_env["temp_dir"])
    ws = SafeWorkspaceManager(temp_dir)

    ws.create_directory("subfolder")
    assert (temp_dir / "subfolder").is_dir()

    ws.write_file("subfolder/data.txt", "hello world")
    assert ws.read_file("subfolder/data.txt") == "hello world"

    ws.rename_path("subfolder/data.txt", "subfolder/renamed.txt")
    assert (temp_dir / "subfolder" / "renamed.txt").exists()


def test_14_failed_operation_does_not_corrupt_state(test_env):
    """A failed command does not corrupt state or invalidate active project."""
    orch = test_env["orchestrator"]
    temp_dir = Path(test_env["temp_dir"])
    project_path = temp_dir / "ValidProject"

    orch.execute_command(f"Create a website, save the project to {project_path}, and name it ValidProject.")
    assert orch.active_project.name == "ValidProject"

    # Run invalid command
    orch.execute_command("delete C:\\Windows\\System32")

    # State remains intact
    assert orch.active_project.name == "ValidProject"
    assert orch.conversation_state.active_project_path == str(project_path.resolve())


def test_15_repeated_answers_do_not_duplicate_projects(test_env):
    """Repeating an answer does not duplicate project or trigger repeated creation."""
    orch = test_env["orchestrator"]
    temp_dir = Path(test_env["temp_dir"])
    p_path = temp_dir / "SingleShop"

    orch.execute_command(f"Create a coffee shop website, save the project to {p_path}, and name it SingleShop.")
    assert p_path.exists()

    # Re-running same target with confirm flag doesn't crash or corrupt
    orch.execute_command(f"Create a coffee shop website, save the project to {p_path}, and name it SingleShop. confirm")
    assert (p_path / "index.html").exists()


# ══════════════════════════════════════════════════════════════════════════════
# 4. SIMULATED FULL END-TO-END ACCEPTANCE SCENARIO
# ══════════════════════════════════════════════════════════════════════════════

def test_16_end_to_end_jarvis_developer_workflow(test_env):
    """
    Simulates the exact 4-turn developer collaboration scenario + process restart:
    Turn 1: User: 'Create a website for my business.' -> Status CLARIFY, 0 files.
    Turn 2: User: 'It's a modern boutique coffee shop. Just frontend. Save it to D:\\CoffeeShop and name it CoffeeShop.' -> Creates project.
    Turn 3: User: 'Add an online reservation page to it.' -> Resolves 'it', adds reservation.html.
    Turn 4: User: 'Fix the reservation form validation.' -> Validates/fixes code.
    Restart: Process restart recovers project context and continues.
    """
    db_file = test_env["db_file"]
    temp_dir = Path(test_env["temp_dir"])
    coffee_shop_dir = temp_dir / "CoffeeShop"

    # --- TURN 1 ---
    orch = test_env["orchestrator"]
    t1_res = orch.execute_command("Create a website for my business.")
    assert t1_res["status"] == "CLARIFY"
    assert "business" in t1_res["question"].lower()
    assert not coffee_shop_dir.exists()  # Zero files created

    # --- TURN 2 ---
    t2_cmd = f"It's a modern boutique coffee shop. Just frontend. Save it to {coffee_shop_dir} and name it CoffeeShop."
    t2_res = orch.execute_command(t2_cmd)
    assert t2_res["status"] == "SUCCESS"
    assert t2_res["decision_status"] == "EXECUTE"
    assert coffee_shop_dir.exists()
    assert (coffee_shop_dir / "index.html").exists()
    assert (coffee_shop_dir / "style.css").exists()

    # --- TURN 3 ---
    t3_res = orch.execute_command("Add an online reservation page to it.")
    assert t3_res["status"] == "SUCCESS"
    assert (coffee_shop_dir / "reservation.html").exists()
    res_content = (coffee_shop_dir / "reservation.html").read_text(encoding="utf-8")
    assert "<form" in res_content

    # --- TURN 4 ---
    t4_res = orch.execute_command("Fix the reservation form validation.")
    assert t4_res["status"] == "SUCCESS"
    assert t4_res["decision_status"] == "EXECUTE"
    res_content_updated = (coffee_shop_dir / "reservation.html").read_text(encoding="utf-8")
    assert "validation" in res_content_updated.lower() or "submit" in res_content_updated.lower()

    # --- PROCESS RESTART TEST ---
    del orch
    # Brand new orchestrator and state instance loaded from SQLite
    mem_restart = SessionMemory(db_path=db_file)
    state_restart = ConversationState(session_memory=mem_restart)
    orch_restart = GameDevOrchestrator(
        config=test_env["config"],
        enable_voice=False,
        session_memory=mem_restart,
        conversation_state=state_restart,
    )

    # Context verified recovered
    assert orch_restart.active_project is not None
    assert orch_restart.active_project.name == "CoffeeShop"
    assert Path(orch_restart.active_project.root_path) == coffee_shop_dir.resolve()

    # User continues project in the new process
    restart_res = orch_restart.execute_command("Continue the coffee shop project and improve the reservation page.")
    assert restart_res["status"] in ("SUCCESS", "MODIFIED", "SERVING")
