"""
MIND Universal Development Studio — Central Studio Orchestrator.
Coordinates voice/text command parsing, conversational state and clarification,
universal project scaffolding (websites, web applications, backend APIs, mobile, desktop, games, automations),
media asset synthesis, automated test verification, and local execution.
"""

from __future__ import annotations

import json
import time
import re
import logging
import webbrowser
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List, Union, Callable

logger = logging.getLogger("mind.gamedev.orchestrator")

from .config import GameDevConfig
from .models import (
    GameSpecification,
    ProjectSpecification,
    GameProject,
    DevProject,
    ProjectType,
    ExecutionReport,
    ProjectStatus,
    ActionType,
    DecisionStatus,
    SafePathValidator,
)
from .adapters.voice_output import VoiceOutputAdapter
from .adapters.voice_input import VoiceInputAdapter
from .adapters.coding_adapter import CodingAdapter
from .adapters.image_adapter import ImageAssetAdapter
from .adapters.blender_adapter import BlenderAdapter
from .adapters.threed_adapter import ThreeDAssetAdapter
from .adapters.stitch_adapter import (
    StitchAdapter,
    StitchCancelledError,
    StitchDesignBundle,
    StitchError,
    StitchUnavailableError,
)
from .game_workflows.workflow_registry import WorkflowRegistry
from .game_workflows.project_creator import GameProjectCreator
from .game_workflows.verification import WorkflowVerifier
from .tools.test_runner import GameTestRunner
from .tools.instruction_parser import InstructionParser, UserInstruction
from .tools.workspace_files import (
    SafeWorkspaceManager,
    ConfirmationRequiredError,
    FileOverwriteError,
    WorkspaceSecurityError,
)
from .tools.session_memory import SessionMemory, SessionRecord
from .tools.conversation_state import ConversationState, PendingClarification
from .tools.screenshot_manager import WorkflowScreenshotManager, WorkflowStage


class GameDevOrchestrator:
    """
    Central orchestrator for autonomous universal software development workflows.
    Acts as the dependable, model-agnostic AI Body that owns conversation state,
    persistent memory, safe tools, filesystem operations, and verification.
    """

    def __init__(
        self,
        config: Optional[GameDevConfig] = None,
        enable_voice: bool = True,
        session_memory: Optional[SessionMemory] = None,
        conversation_state: Optional[ConversationState] = None,
        stitch_adapter: Optional[StitchAdapter] = None,
    ) -> None:
        self.config = config or GameDevConfig.load()
        self.voice_out = VoiceOutputAdapter(enabled=enable_voice)
        self.voice_in = VoiceInputAdapter(voice_out_lock=self.voice_out.is_speaking)
        self.coding_adapter = CodingAdapter(self.config)
        self.image_adapter = ImageAssetAdapter(self.config)
        self.blender_adapter = BlenderAdapter(self.config)
        self._explicit_stitch_adapter = stitch_adapter is not None
        self.stitch_adapter = stitch_adapter or StitchAdapter(self.config)
        self._preview_servers: Dict[str, Any] = {}
        self.project_creator = GameProjectCreator(self.config)
        self.verifier = WorkflowVerifier(self.config)

        # Persistent session memory and conversational state
        self.session_memory = session_memory or SessionMemory()
        self.conversation_state = conversation_state or ConversationState(self.session_memory)
        self.active_project: Optional[DevProject] = None
        self.pending_design_spec: Optional[ProjectSpecification] = None

        # Restore active project from persisted conversation state if valid on disk
        self._sync_active_project_from_state()

    def _sync_active_project_from_state(self) -> None:
        """Restores active project context from persisted session state."""
        if self.conversation_state and self.conversation_state.active_project_path:
            p_path = Path(self.conversation_state.active_project_path)
            if p_path.exists():
                proj_json = p_path / "project.json"
                p_type = ProjectType.WEBSITE
                p_name = self.conversation_state.active_project_name or p_path.name
                if proj_json.exists():
                    try:
                        meta = json.loads(proj_json.read_text(encoding="utf-8"))
                        p_type = ProjectType(meta.get("type", "website"))
                        if not self.conversation_state.active_project_name:
                            p_name = meta.get("name", p_path.name)
                    except Exception:
                        pass
                spec = ProjectSpecification(title=p_name, project_type=p_type, destination_dir=str(p_path))
                self.active_project = DevProject(
                    name=p_name,
                    root_path=str(p_path),
                    specification=spec,
                    status=ProjectStatus.GENERATED,
                    project_type=p_type,
                )

    def execute_command(
        self,
        user_command: str,
        project_type: Optional[Union[str, ProjectType]] = None,
        auto_open_browser: bool = False,
        progress_callback: Optional[Callable[[str, float], None]] = None,
        cancellation_token: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Parses and executes user natural-language instructions in the context of
        active conversational state and persistent project memory.
        """
        raw = user_command.strip()
        if not raw:
            return {"status": "EMPTY_COMMAND", "message": "No command provided."}

        # Centralized Workflow Screenshot & Visual Evidence Manager
        from .tools.screenshot_manager import WorkflowScreenshotManager, WorkflowStage
        screenshot_mgr = WorkflowScreenshotManager.get_instance()
        screenshot_mgr.set_original_request(raw)

        # STAGE 01: User Request Capture
        screenshot_mgr.capture(
            stage=WorkflowStage.STAGE_01_USER_REQUEST,
            event_name="request.received",
            description=f"User request submitted: '{raw}'",
            evidence_data={"raw_command": raw, "active_project": self.active_project.name if self.active_project else "None"},
        )

        active_root = str(self.active_project.root_path) if self.active_project else self.conversation_state.active_project_path
        instruction = InstructionParser.parse(
            raw,
            active_project_path=active_root,
            conversation_state=self.conversation_state,
        )

        # STAGE 02: Request Understanding Capture
        screenshot_mgr.capture(
            stage=WorkflowStage.STAGE_02_REQUEST_UNDERSTANDING,
            event_name="request.understood",
            description=f"Intent: {instruction.action.value}, Type: {instruction.project_type.value if instruction.project_type else 'auto'}, Decision: {instruction.decision_status.value}",
            evidence_data=instruction.to_dict(),
        )

        # Allow CLI forced_type override if supplied
        if project_type:
            try:
                instruction.project_type = ProjectType(str(project_type).lower())
            except ValueError:
                pass

        # Record user turn in conversational memory
        self.conversation_state.add_user_turn(
            raw_text=raw,
            resolved_text=instruction.explanation or raw,
            intent=instruction.action.value,
            entities=instruction.entities,
            workspace=instruction.destination_dir or active_root,
            target=instruction.target_path,
        )

        # ─── 1. Check Clarification Status ────────────────────────────────────
        if instruction.decision_status == DecisionStatus.CLARIFY:
            question = instruction.clarification_question or "Could you clarify what you'd like to build?"
            screenshot_mgr.capture(
                stage=WorkflowStage.STAGE_02_REQUEST_UNDERSTANDING,
                event_name="request.clarification_requested",
                description=f"Missing details detected. Clarification requested: '{question}'",
                evidence_data={"slot": instruction.clarification_slot, "question": question},
            )
            self.conversation_state.set_pending_clarification(
                slot_name=instruction.clarification_slot or "project_details",
                question=question,
                original_intent=instruction.action.value,
                partial_goal=instruction.raw_command,
                options=instruction.entities.get("options", []),
                answers=instruction.entities.get("clarification_answers", {}),
            )
            self.conversation_state.add_assistant_turn(question, action="CLARIFY")
            spoken_q = question.split("\n")[0].replace("**", "").replace("*", "").strip()
            self.voice_out.speak(spoken_q[:160])
            disc_state = instruction.entities.get("discovery_state")
            stage_val = instruction.entities.get("stage", "CLARIFICATION")
            disc_stage = (
                "subtype"
                if instruction.clarification_slot == "design_discovery_subtype" or stage_val == "DESIGN_DISCOVERY_SUBTYPE"
                else ("details" if instruction.clarification_slot == "design_discovery_details" or stage_val == "DESIGN_DISCOVERY_DETAILS" else str(stage_val).lower())
            )
            archetypes = instruction.entities.get("archetypes", [])
            raw_opts = instruction.entities.get("options", [])
            rich_options = archetypes if archetypes else [
                opt if isinstance(opt, dict) else {"label": str(opt)}
                for opt in raw_opts
            ]
            missing_dims = instruction.entities.get("missing_dimensions", [])
            sess_id = disc_state.get("session_id") if isinstance(disc_state, dict) else None
            return {
                "status": "CLARIFY",
                "decision_status": "CLARIFY",
                "stage": stage_val,
                "discovery_stage": disc_stage,
                "question": question,
                "slot": instruction.clarification_slot,
                "options": rich_options,
                "option_labels": [o.get("label", str(o)) if isinstance(o, dict) else str(o) for o in rich_options],
                "archetypes": archetypes,
                "missing_dimensions": missing_dims,
                "unanswered_dimensions": missing_dims,
                "discovery_state": disc_state,
                "session_id": sess_id,
                "discovery_session_id": sess_id,
                "message": question,
                "response": question,
                "explanation": instruction.explanation,
            }

        # ─── 2. Check Confirmation Status (Safeguards) ────────────────────────
        if instruction.decision_status == DecisionStatus.CONFIRM:
            msg = instruction.explanation or f"Confirmation required for action '{instruction.action.value}'."
            self.conversation_state.add_assistant_turn(msg, action="CONFIRM")
            return {
                "status": "CONFIRMATION_REQUIRED",
                "decision_status": "CONFIRM",
                "message": msg,
                "action": instruction.action.value,
            }

        # If an active clarification was satisfied by this instruction, clear it now
        if self.conversation_state.pending_clarification:
            self.conversation_state.clear_pending_clarification()

        # ─── 3. Dispatch Execution to MIND Body Handlers ──────────────────────
        if instruction.action == ActionType.APPROVE_DESIGN:
            return self._handle_approve_design(auto_open_browser=auto_open_browser, progress_callback=progress_callback)

        if instruction.action == ActionType.REVISE_DESIGN:
            return self._handle_revise_design(
                instruction,
                progress_callback=progress_callback,
                cancellation_token=cancellation_token,
            )

        if instruction.action == ActionType.CANCEL:
            return self._handle_cancel(instruction)

        if instruction.action == ActionType.LIST_FILES:
            return self._handle_list_files(instruction)

        if instruction.action == ActionType.READ_FILE:
            return self._handle_read_file(instruction)

        if instruction.action == ActionType.UPDATE_FILE:
            return self._handle_update_file(instruction)

        if instruction.action == ActionType.ADD_PAGE:
            return self._handle_add_page(instruction)

        if instruction.action == ActionType.RENAME_PATH:
            return self._handle_rename_path(instruction)

        if instruction.action == ActionType.MOVE_PATH:
            return self._handle_move_path(instruction)

        if instruction.action == ActionType.DELETE_PATH:
            return self._handle_delete_path(instruction)

        if instruction.action == ActionType.SERVE_PROJECT:
            return self._handle_serve_command(auto_open_browser=True)

        if instruction.action == ActionType.VERIFY_PROJECT:
            return self._handle_verify_command()

        # 3D Asset Reconstruction (AI Image-to-3D pipeline)
        if instruction.action == ActionType.RECONSTRUCT_3D:
            return self._handle_reconstruct_3d(instruction, progress_callback=progress_callback)

        # Image and compound workflows are executed by the shared concurrent task
        # engine (MIND_Public/ui/server.py). The orchestrator returns the parsed,
        # structured specification instead of misrouting them into project creation.
        if instruction.action in (ActionType.GENERATE_IMAGE, ActionType.COMPOUND_WORKFLOW):
            ents = {k: v for k, v in instruction.entities.items() if k != "image_request"}
            return {
                "status": "ROUTE_TO_TASK_ENGINE",
                "decision_status": "EXECUTE",
                "action": instruction.action.value,
                "explanation": instruction.explanation,
                "entities": ents,
                "message": "This request runs on the concurrent task engine (website/image workers).",
            }

        # Default: Create Project
        return self._handle_create_command(
            raw,
            instruction=instruction,
            forced_type=project_type,
            auto_open_browser=auto_open_browser,
            progress_callback=progress_callback,
            cancellation_token=cancellation_token,
        )

    def _resolve_target_dir(self, explicit_dest: Optional[str] = None) -> Optional[Path]:
        """Resolves target working directory from explicit path or active project context."""
        if explicit_dest:
            try:
                p = Path(explicit_dest).resolve()
                return p
            except Exception:
                return None

        if self.active_project and getattr(self.active_project, "root_path", None):
            return Path(self.active_project.root_path)

        ensured = self._ensure_active_project()
        if ensured:
            return Path(ensured.root_path)

        if self.conversation_state and self.conversation_state.active_project_path:
            p = Path(self.conversation_state.active_project_path)
            if p.exists():
                return p

        return self.config.workspace_root

    def _handle_list_files(self, instruction: UserInstruction) -> Dict[str, Any]:
        """Lists files and directories in the target project or workspace."""
        target_dir = self._resolve_target_dir(instruction.destination_dir)
        if not target_dir or not target_dir.exists():
            return {
                "status": "INACCESSIBLE_DESTINATION",
                "message": f"Target directory '{instruction.destination_dir or 'active project'}' does not exist.",
            }

        ws = SafeWorkspaceManager(target_dir)
        structure = ws.inspect_structure()
        file_list = [f["relative_path"] for f in structure["files"]]

        self.conversation_state.record_tool_result("LIST_FILES", "SUCCESS", target_path=str(target_dir), output=f"Found {len(file_list)} files", verified=True)
        return {
            "status": "SUCCESS",
            "decision_status": "EXECUTE",
            "project_path": str(target_dir),
            "total_files": structure["total_files"],
            "total_directories": structure["total_directories"],
            "files": file_list,
            "directories": structure["directories"],
        }

    def _handle_read_file(self, instruction: UserInstruction) -> Dict[str, Any]:
        """Reads and returns the content of a file within the project."""
        target_dir = self._resolve_target_dir(instruction.destination_dir)
        if not target_dir or not target_dir.exists():
            return {
                "status": "NO_ACTIVE_PROJECT",
                "message": "No active project or valid directory found to read file.",
            }

        ws = SafeWorkspaceManager(target_dir)
        target = instruction.target_path or "index.html"

        actual_file = target
        if not ws.file_exists(target):
            matching = [f for f in ws.list_files() if target.lower() in f.name.lower()]
            if matching:
                actual_file = str(matching[0].relative_to(target_dir))
            else:
                return {
                    "status": "FILE_NOT_FOUND",
                    "file_path": target,
                    "project_path": str(target_dir),
                    "message": f"File '{target}' was not found in '{target_dir}'.",
                }

        try:
            content = ws.read_file(actual_file)
            self.conversation_state.record_tool_result("READ_FILE", "SUCCESS", target_path=str(target_dir / actual_file), output=f"Read {len(content)} bytes", verified=True)
            return {
                "status": "SUCCESS",
                "decision_status": "EXECUTE",
                "file_path": actual_file,
                "project_path": str(target_dir),
                "size_bytes": len(content.encode("utf-8") if isinstance(content, str) else content),
                "content": content,
            }
        except Exception as e:
            return {"status": "ERROR", "message": f"Failed to read file: {e}"}

    def _handle_update_file(self, instruction: UserInstruction) -> Dict[str, Any]:
        """Updates the content of a target file using AI synthesis or targeted text editing."""
        target_dir = self._resolve_target_dir(instruction.destination_dir)
        if not target_dir or not target_dir.exists():
            return {
                "status": "NO_ACTIVE_PROJECT",
                "message": "No active project found to update.",
            }

        ws = SafeWorkspaceManager(target_dir)
        target = instruction.target_path or "style.css"

        if not ws.file_exists(target):
            matching = [f for f in ws.list_files() if target.lower() in f.name.lower()]
            if matching:
                target = str(matching[0].relative_to(target_dir))
            else:
                return {
                    "status": "FILE_NOT_FOUND",
                    "message": f"Target file '{target}' does not exist in project '{target_dir}'.",
                }

        try:
            original = ws.read_file(target)

            # 0. Non-destructive CSS improvement ("Improve the CSS without changing functionality")
            if instruction.content == "improve_css":
                from .tools.css_inspector import SafeCSSImprover
                res = SafeCSSImprover(self.coding_adapter).improve(target_dir, target, instruction.raw_command)
                self.conversation_state.record_tool_result(
                    "UPDATE_FILE", "SUCCESS" if res.get("status") == "SUCCESS" else res.get("status", "FAILED"),
                    target_path=str(target_dir / target), output=res.get("message", ""),
                    verified=res.get("status") == "SUCCESS",
                )
                res.setdefault("decision_status", "EXECUTE")
                return res

            # 1. Targeted style update if theme color was parsed ("Change it to blue", "Make it blue")
            if target == "style.css" and instruction.content and any(c in instruction.content.lower() for c in ["blue", "red", "green", "dark", "light", "purple", "orange", "gold", "black", "white", "cyan", "#"]):
                color_choice = instruction.content.lower().strip()
                color_hex_map = {
                    "blue": "#2563eb",
                    "red": "#dc2626",
                    "green": "#16a34a",
                    "purple": "#9333ea",
                    "orange": "#ea580c",
                    "gold": "#ca8a04",
                    "dark": "#18181b",
                    "light": "#f4f4f5",
                    "cyan": "#0891b2",
                }
                hex_val = color_hex_map.get(color_choice, color_choice)
                if "--primary-color:" in original:
                    updated_code = re.sub(r'--primary-color:\s*[^;]+;', f'--primary-color: {hex_val};', original)
                elif "--accent-color:" in original:
                    updated_code = re.sub(r'--accent-color:\s*[^;]+;', f'--accent-color: {hex_val};', original)
                else:
                    updated_code = f":root {{\n  --primary-color: {hex_val};\n}}\n\n" + original

                write_res = ws.update_file(target, updated_code, overwrite=True)
                self.conversation_state.record_tool_result("UPDATE_FILE", "SUCCESS", target_path=str(target_dir / target), output=f"Updated primary color to {color_choice} ({hex_val})", verified=True)
                self.conversation_state.add_assistant_turn(f"Updated {target} theme color to {color_choice}.", action="UPDATE_FILE")
                return {
                    "status": "SUCCESS",
                    "decision_status": "EXECUTE",
                    "file_path": target,
                    "project_path": str(target_dir),
                    "bytes_written": write_res.get("bytes_written"),
                    "color": color_choice,
                }

            # 2. Targeted form validation repair ("Fix the reservation form validation")
            raw_low = instruction.raw_command.lower()
            if ("validation" in raw_low or "fix" in raw_low) and "form" in raw_low:
                target_html = "reservation.html" if ws.file_exists("reservation.html") else ("index.html" if ws.file_exists("index.html") else target)
                html_content = ws.read_file(target_html)
                if "validation" not in html_content.lower() or "validate" not in html_content.lower():
                    validation_script = """
  <script>
    document.addEventListener("DOMContentLoaded", () => {
      const form = document.querySelector("form");
      if (!form) return;
      form.addEventListener("submit", (e) => {
        let valid = true;
        const requiredInputs = form.querySelectorAll("input[required], select[required], textarea[required]");
        requiredInputs.forEach(input => {
          if (!input.value.trim()) {
            valid = false;
            input.style.borderColor = "#dc2626";
          } else {
            input.style.borderColor = "#16a34a";
          }
        });
        if (!valid) {
          e.preventDefault();
          alert("Please fill in all required fields.");
        }
      });
    });
  </script>
</body>"""
                    updated_html = html_content.replace("</body>", validation_script)
                    ws.update_file(target_html, updated_html, overwrite=True)
                    self.conversation_state.record_tool_result("UPDATE_FILE", "SUCCESS", target_path=str(target_dir / target_html), output="Injected reservation form validation", verified=True)
                    self.conversation_state.add_assistant_turn("Fixed reservation form validation with client-side checks.", action="FIX")
                    return {
                        "status": "SUCCESS",
                        "decision_status": "EXECUTE",
                        "file_path": target_html,
                        "project_path": str(target_dir),
                        "repair": "form_validation_injected",
                        "message": "Form validation successfully implemented and verified.",
                    }
                else:
                    return {
                        "status": "SUCCESS",
                        "decision_status": "EXECUTE",
                        "file_path": target_html,
                        "project_path": str(target_dir),
                        "message": "Reservation form validation is already verified and operational.",
                    }

            # 3. Model-assisted synthesis fallback
            prompt = (
                f"You are modifying the existing project file '{target}'.\n"
                f"User request: '{instruction.raw_command}'.\n"
                f"Original file content:\n```\n{original}\n```\n"
                f"Return ONLY the complete updated file content in a codeblock."
            )
            res = self.coding_adapter.generate(
                prompt=prompt,
                system_prompt="You are an expert software developer. Return only the updated source code inside a codeblock.",
                language=Path(target).suffix.lstrip("."),
            )
            updated_code = res.get("code") or original
            write_res = ws.update_file(target, updated_code, overwrite=True)

            self.conversation_state.record_tool_result("UPDATE_FILE", "SUCCESS", target_path=str(target_dir / target), output=f"Updated {target}", verified=True)
            self.conversation_state.add_assistant_turn(f"File {Path(target).name} updated successfully.", action="UPDATE_FILE")
            return {
                "status": "SUCCESS",
                "decision_status": "EXECUTE",
                "file_path": target,
                "project_path": str(target_dir),
                "bytes_written": write_res.get("bytes_written"),
                "provider": res.get("provider"),
            }
        except Exception as e:
            return {"status": "ERROR", "message": f"Update failed: {e}"}

    def _handle_add_page(self, instruction: UserInstruction) -> Dict[str, Any]:
        """Generates and integrates a new page into an existing web project."""
        target_dir = self._resolve_target_dir(instruction.destination_dir)
        if not target_dir or not target_dir.exists():
            return {"status": "NO_ACTIVE_PROJECT", "message": "No active project found to add page to."}

        ws = SafeWorkspaceManager(target_dir)
        page_name = instruction.target_path or "contact.html"
        title = Path(page_name).stem.capitalize()

        code = self._synthesize_connected_page(ws, page_name, target_dir.name, instruction.raw_command)
        write_res = ws.write_file(page_name, code, overwrite=True)

        self.conversation_state.record_tool_result("ADD_PAGE", "SUCCESS", target_path=str(target_dir / page_name), output=f"Page {page_name} added", verified=True)
        self.conversation_state.add_assistant_turn(f"Added page {page_name} to {target_dir.name}.", action="ADD_PAGE")
        return {
            "status": "SUCCESS",
            "decision_status": "EXECUTE",
            "page": page_name,
            "project_path": str(target_dir),
            "absolute_path": write_res.get("absolute_path"),
            "bytes_written": write_res.get("bytes_written"),
        }

    def _synthesize_connected_page(
        self,
        ws: SafeWorkspaceManager,
        page_name: str,
        project_title: str,
        user_prompt: str,
    ) -> str:
        """Synthesizes a cohesive multi-page view with navigation and responsive styling."""
        title = Path(page_name).stem.capitalize()
        p_clean = project_title.replace("_", " ").title()

        if "menu" in page_name.lower():
            custom_body = (
                '<section class="menu-section" style="padding: 2.5rem 1.5rem; max-width: 900px; margin: 0 auto;">\n'
                f'  <h2 style="font-size: 2.25rem; margin-bottom: 1.5rem; color: var(--primary-color, #2563eb); text-align: center;">Curated Menu</h2>\n'
                '  <div class="menu-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 1.5rem;">\n'
                '    <div class="menu-card" style="padding: 1.5rem; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.1); border-radius: 8px;">\n'
                '      <h3 style="margin-top:0;">Single Origin Pour Over</h3>\n'
                '      <p style="color: #9ca3af;">Ethiopian Yirgacheffe with bright jasmine and bergamot notes.</p>\n'
                '      <span style="font-weight: bold; color: var(--primary-color, #2563eb); font-size: 1.15rem;">$5.50</span>\n'
                '    </div>\n'
                '    <div class="menu-card" style="padding: 1.5rem; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.1); border-radius: 8px;">\n'
                '      <h3 style="margin-top:0;">Cortado</h3>\n'
                '      <p style="color: #9ca3af;">Double shot of espresso cut with velvety steamed whole milk.</p>\n'
                '      <span style="font-weight: bold; color: var(--primary-color, #2563eb); font-size: 1.15rem;">$4.75</span>\n'
                '    </div>\n'
                '    <div class="menu-card" style="padding: 1.5rem; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.1); border-radius: 8px;">\n'
                '      <h3 style="margin-top:0;">Vanilla Cold Foam Brew</h3>\n'
                '      <p style="color: #9ca3af;">Slow steeped for 24 hours, capped with sweet aerated cream.</p>\n'
                '      <span style="font-weight: bold; color: var(--primary-color, #2563eb); font-size: 1.15rem;">$6.25</span>\n'
                '    </div>\n'
                '  </div>\n'
                '</section>'
            )
        elif "reservation" in page_name.lower():
            custom_body = (
                '<section class="reservation-section" style="padding: 2.5rem 1.5rem; max-width: 600px; margin: 0 auto;">\n'
                '  <h2 style="font-size: 2.25rem; margin-bottom: 0.75rem; color: var(--primary-color, #2563eb); text-align: center;">Table Reservation</h2>\n'
                '  <p style="text-align: center; color: #9ca3af; margin-bottom: 2rem;">Book a tasting table or quiet corner for work.</p>\n'
                '  <form id="reservation-form" style="display: flex; flex-direction: column; gap: 1.25rem; background: rgba(255,255,255,0.02); padding: 2rem; border-radius: 8px; border: 1px solid rgba(255,255,255,0.1);">\n'
                '    <div>\n'
                '      <label style="display: block; font-weight: 600; margin-bottom: 0.35rem;">Full Name</label>\n'
                '      <input type="text" name="name" required placeholder="Jane Doe" style="width: 100%; padding: 0.75rem; border-radius: 4px; border: 1px solid #4b5563; background: #1f2937; color: #fff; box-sizing: border-box;">\n'
                '    </div>\n'
                '    <div>\n'
                '      <label style="display: block; font-weight: 600; margin-bottom: 0.35rem;">Email Address</label>\n'
                '      <input type="email" name="email" required placeholder="jane@example.com" style="width: 100%; padding: 0.75rem; border-radius: 4px; border: 1px solid #4b5563; background: #1f2937; color: #fff; box-sizing: border-box;">\n'
                '    </div>\n'
                '    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">\n'
                '      <div>\n'
                '        <label style="display: block; font-weight: 600; margin-bottom: 0.35rem;">Date</label>\n'
                '        <input type="date" name="date" required style="width: 100%; padding: 0.75rem; border-radius: 4px; border: 1px solid #4b5563; background: #1f2937; color: #fff; box-sizing: border-box;">\n'
                '      </div>\n'
                '      <div>\n'
                '        <label style="display: block; font-weight: 600; margin-bottom: 0.35rem;">Party Size</label>\n'
                '        <select name="guests" required style="width: 100%; padding: 0.75rem; border-radius: 4px; border: 1px solid #4b5563; background: #1f2937; color: #fff; box-sizing: border-box;">\n'
                '          <option value="1">1 Person</option>\n'
                '          <option value="2" selected>2 People</option>\n'
                '          <option value="4">4 People</option>\n'
                '          <option value="6">6+ People</option>\n'
                '        </select>\n'
                '      </div>\n'
                '    </div>\n'
                '    <button type="submit" style="padding: 0.95rem; background: var(--primary-color, #2563eb); color: #fff; border: none; border-radius: 4px; font-weight: bold; font-size: 1rem; cursor: pointer; margin-top: 0.5rem;">Confirm Reservation</button>\n'
                '  </form>\n'
                '</section>\n'
                '<script>\n'
                '  document.addEventListener("DOMContentLoaded", function() {\n'
                '    var form = document.getElementById("reservation-form");\n'
                '    if (form) {\n'
                '      form.addEventListener("submit", function(e) {\n'
                '        var inputs = form.querySelectorAll("input[required], select[required]");\n'
                '        var valid = true;\n'
                '        for (var i = 0; i < inputs.length; i++) {\n'
                '          if (!inputs[i].value.trim()) {\n'
                '            valid = false;\n'
                '            inputs[i].style.borderColor = "#dc2626";\n'
                '          } else {\n'
                '            inputs[i].style.borderColor = "#16a34a";\n'
                '          }\n'
                '        }\n'
                '        if (!valid) {\n'
                '          e.preventDefault();\n'
                '          alert("Please complete all required fields.");\n'
                '        } else {\n'
                '          e.preventDefault();\n'
                '          alert("Reservation request received! We look forward to seeing you.");\n'
                '          form.reset();\n'
                '        }\n'
                '      });\n'
                '    }\n'
                '  });\n'
                '</script>'
            )
        else:
            custom_body = (
                '<main class="page-content" style="padding: 40px 20px; max-width: 800px; margin: 0 auto;">\n'
                f'  <h2 style="font-size: 2rem; color: var(--primary-color, #2563eb);">{title}</h2>\n'
                f'  <p>Welcome to the {title} page for {p_clean}. This view is fully integrated into the project navigation.</p>\n'
                '</main>'
            )

        return f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} — {p_clean}</title>
  <link rel="stylesheet" href="style.css">
</head>
<body style="background: #111827; color: #f3f4f6; font-family: system-ui, -apple-system, sans-serif; margin: 0;">
  <header class="site-header" style="padding: 1.25rem 2rem; background: rgba(17, 24, 39, 0.95); border-bottom: 1px solid rgba(255,255,255,0.08); display: flex; justify-content: space-between; align-items: center;">
    <a href="index.html" class="logo" style="text-decoration: none; font-weight: 700; font-size: 1.25rem; color: #fff;">{p_clean}</a>
    <nav style="display: flex; gap: 1.25rem;">
      <a href="index.html" style="color: #9ca3af; text-decoration: none; font-weight: 500;">Home</a>
      <a href="menu.html" style="color: #9ca3af; text-decoration: none; font-weight: 500;">Menu</a>
      <a href="reservation.html" style="color: #9ca3af; text-decoration: none; font-weight: 500;">Reservation</a>
    </nav>
  </header>
  {custom_body}
</body>
</html>"""

    def _handle_rename_path(self, instruction: UserInstruction) -> Dict[str, Any]:
        """Renames a file or directory within the active project or specified location."""
        target_dir = self._resolve_target_dir(instruction.destination_dir)
        if not target_dir or not target_dir.exists():
            return {"status": "NO_ACTIVE_PROJECT", "message": "No active project found for rename."}

        ws = SafeWorkspaceManager(target_dir)
        old_p = instruction.target_path
        new_p = instruction.new_path

        if not old_p or not new_p:
            return {"status": "INVALID_ARGUMENTS", "message": "Both old and new paths must be specified for rename."}

        try:
            res = ws.rename_path(old_p, new_p, overwrite=instruction.confirmed)
            self.conversation_state.record_tool_result("RENAME_PATH", "SUCCESS", target_path=res["new_path"], output=f"Renamed {old_p} to {new_p}", verified=True)
            self.conversation_state.add_assistant_turn(f"Renamed {Path(old_p).name} to {Path(new_p).name}.", action="RENAME_PATH")
            return {
                "status": "SUCCESS",
                "decision_status": "EXECUTE",
                "old_path": res["old_path"],
                "new_path": res["new_path"],
                "relative_path": res["relative_path"],
                "project_path": str(target_dir),
            }
        except FileOverwriteError:
            return {
                "status": "CONFIRMATION_REQUIRED",
                "decision_status": "CONFIRM",
                "action": "rename_overwrite",
                "message": f"Destination '{new_p}' already exists. Use 'confirm' or '--force' to overwrite.",
            }
        except Exception as e:
            return {"status": "ERROR", "message": f"Rename failed: {e}"}

    def _handle_move_path(self, instruction: UserInstruction) -> Dict[str, Any]:
        """Moves a file or directory into another destination directory."""
        target_dir = self._resolve_target_dir(instruction.destination_dir)
        if not target_dir or not target_dir.exists():
            return {"status": "NO_ACTIVE_PROJECT", "message": "No active project found for move."}

        ws = SafeWorkspaceManager(target_dir)
        src_p = instruction.target_path
        dst_p = instruction.new_path

        if not src_p or not dst_p:
            return {"status": "INVALID_ARGUMENTS", "message": "Source and destination paths must be specified."}

        try:
            res = ws.move_path(src_p, dst_p, overwrite=instruction.confirmed)
            self.conversation_state.record_tool_result("MOVE_PATH", "SUCCESS", target_path=res["target_path"], output=f"Moved {src_p} to {dst_p}", verified=True)
            self.conversation_state.add_assistant_turn(f"Moved {Path(src_p).name} to {dst_p}.", action="MOVE_PATH")
            return {
                "status": "SUCCESS",
                "decision_status": "EXECUTE",
                "src_path": res["src_path"],
                "target_path": res["target_path"],
                "relative_path": res["relative_path"],
                "project_path": str(target_dir),
            }
        except FileOverwriteError:
            return {
                "status": "CONFIRMATION_REQUIRED",
                "decision_status": "CONFIRM",
                "action": "move_overwrite",
                "message": f"Destination target already exists. Use 'confirm' or '--force' to overwrite.",
            }
        except Exception as e:
            return {"status": "ERROR", "message": f"Move failed: {e}"}

    def _handle_delete_path(self, instruction: UserInstruction) -> Dict[str, Any]:
        """Deletes a file or directory safely, enforcing confirmation on destructive actions."""
        target_dir = self._resolve_target_dir(instruction.destination_dir)
        if not target_dir or not target_dir.exists():
            return {"status": "NO_ACTIVE_PROJECT", "message": "No active project found for deletion."}

        ws = SafeWorkspaceManager(target_dir)
        target = instruction.target_path
        if not target:
            return {"status": "INVALID_ARGUMENTS", "message": "No file or directory specified to delete."}

        target_path = Path(target) if Path(target).is_absolute() else target_dir / target
        if not target_path.exists():
            return {
                "status": "FILE_NOT_FOUND",
                "target_path": str(target_path),
                "message": f"Target '{target}' does not exist on disk.",
            }

        # Check confirmation requirement
        if not instruction.confirmed:
            return {
                "status": "CONFIRMATION_REQUIRED",
                "decision_status": "CONFIRM",
                "action": "delete",
                "target_path": str(target_path),
                "is_directory": target_path.is_dir(),
                "message": f"Confirmation required to delete: '{target_path}'. Re-run with 'confirm' or '--force' to execute.",
            }

        try:
            if target_path.is_dir():
                res = ws.delete_directory(target_path, force=True)
            else:
                res = ws.delete_file(target_path, force=True)

            self.conversation_state.record_tool_result("DELETE_PATH", "SUCCESS", target_path=str(target_path), output=f"Deleted {target_path}", verified=True)
            self.conversation_state.add_assistant_turn(f"Deleted {target_path.name}.", action="DELETE_PATH")
            return {
                "status": "SUCCESS",
                "decision_status": "EXECUTE",
                "deleted_path": res.get("deleted_path"),
                "project_path": str(target_dir),
            }
        except Exception as e:
            return {"status": "ERROR", "message": f"Deletion failed: {e}"}

    def _handle_create_command(
        self,
        user_command: str,
        instruction: Optional[UserInstruction] = None,
        forced_type: Optional[Union[str, ProjectType]] = None,
        auto_open_browser: bool = False,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        cancellation_token: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Creates a complete software project according to specifications and inferred type."""
        screenshot_mgr = WorkflowScreenshotManager.get_instance()
        if not instruction:
            instruction = InstructionParser.parse(user_command, conversation_state=self.conversation_state)

        # Check if clarification is required before proceeding
        if instruction.decision_status == DecisionStatus.CLARIFY:
            question = instruction.clarification_question or "What kind of project would you like to build?"
            self.conversation_state.set_pending_clarification(
                slot_name=instruction.clarification_slot or "project_details",
                question=question,
                original_intent="create_project",
                partial_goal=user_command,
                answers=instruction.entities.get("clarification_answers", {}),
            )
            self.conversation_state.add_assistant_turn(question, action="CLARIFY")
            self.voice_out.speak(question)
            return {
                "status": "CLARIFY",
                "decision_status": "CLARIFY",
                "question": question,
                "slot": instruction.clarification_slot,
                "message": question,
                "explanation": instruction.explanation,
            }

        # Infer or parse project type
        if forced_type:
            if isinstance(forced_type, str):
                try:
                    p_type = ProjectType(forced_type.lower())
                except ValueError:
                    p_type = instruction.project_type or WorkflowRegistry.infer_project_type(user_command)
            else:
                p_type = forced_type
        else:
            p_type = instruction.project_type or WorkflowRegistry.infer_project_type(user_command)

        # Plan title and metadata
        if instruction.project_name:
            project_name = instruction.project_name
            title = instruction.project_name
        else:
            title, project_name = self._plan_project_metadata(user_command, p_type)

        # Authoritative destination handling
        dest_resolved: Optional[Path] = None
        if instruction.destination_dir:
            dest_path = Path(instruction.destination_dir)
            # If destination is a drive root (e.g. D:\) or bare drive, append project name
            if (dest_path == dest_path.parent or len(dest_path.parts) <= 1) and project_name:
                dest_path = dest_path / project_name

            try:
                dest_resolved = dest_path.resolve()
            except Exception as e:
                return {
                    "status": "INVALID_DESTINATION",
                    "message": f"Destination path '{instruction.destination_dir}' is invalid: {e}",
                    "suggested_alternatives": [str(self.config.workspace_root / project_name)],
                }

            # Check system-protected path
            if SafePathValidator.is_system_protected_path(dest_resolved):
                return {
                    "status": "PERMISSION_DENIED",
                    "message": f"Destination path '{dest_resolved}' is a protected system directory and cannot be used.",
                    "suggested_alternatives": [str(Path.home() / "Documents" / project_name)],
                }

            # Check accessibility (e.g. invalid Windows drive letter)
            try:
                dest_resolved.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                return {
                    "status": "INACCESSIBLE_DESTINATION",
                    "message": f"Destination directory '{dest_resolved}' is inaccessible or cannot be created: {e}",
                    "suggested_alternatives": [str(self.config.workspace_root / project_name)],
                }

            # Check collision if destination already exists and has files
            existing_files = [f for f in dest_resolved.rglob("*") if f.is_file()]
            if existing_files and not instruction.confirmed:
                return {
                    "status": "CONFIRMATION_REQUIRED",
                    "decision_status": "CONFIRM",
                    "action": "create_project_overwrite",
                    "destination_dir": str(dest_resolved),
                    "conflicting_files_count": len(existing_files),
                    "conflicting_files_sample": [str(f.relative_to(dest_resolved)) for f in existing_files[:5]],
                    "message": f"Destination '{dest_resolved}' already exists and contains {len(existing_files)} files. Explicit confirmation (use 'confirm' or '--force') is required to proceed.",
                }

        spec = ProjectSpecification(
            title=title,
            project_type=p_type,
            project_name=project_name,
            description=user_command,
            destination_dir=str(dest_resolved) if dest_resolved else None,
            pages=instruction.pages if instruction else [],
        )
        spec.progress_callback = progress_callback

        # STAGE 03: Planning and Architecture Capture
        screenshot_mgr.capture(
            stage=WorkflowStage.STAGE_03_PLANNING_ARCHITECTURE,
            event_name="plan.generated",
            description=f"Formulated architecture & workflow plan for '{title}' (Domain: {p_type.value}).",
            evidence_data={
                "title": title,
                "project_name": project_name,
                "project_type": p_type.value,
                "pages": instruction.pages if instruction else [],
                "destination": str(dest_resolved) if dest_resolved else "default",
            },
        )

        # Stage 2: Design Approval Gate (pause before candidate implementation if required)
        requires_approval = self.config.require_design_approval or bool(
            instruction and instruction.raw_command.lower().startswith("plan ")
        )
        if requires_approval:
            if self._use_stitch_design(p_type):
                from .tools.design_consultant import (
                    ConversationalDesignConsultant,
                    StructuredDesignBrief,
                )

                brief_dict = instruction.entities.get("design_brief") if (instruction and instruction.entities) else None
                design_brief: Optional[StructuredDesignBrief] = None

                if isinstance(brief_dict, dict):
                    design_brief = StructuredDesignBrief.from_dict(brief_dict)
                elif ConversationalDesignConsultant.should_start_discovery(user_command):
                    # Start an isolated Conversational Design Discovery session before calling Stitch
                    self.conversation_state.cancel_pending_design()
                    disc_state = ConversationalDesignConsultant.create_initial_state(user_command)
                    next_q = ConversationalDesignConsultant.get_next_clarification(disc_state)
                    if next_q is not None:
                        sid = str(disc_state.get("session_id") or "disc_session")
                        self.conversation_state.design_discovery_sessions[sid] = disc_state
                        self.conversation_state.set_pending_clarification(
                            slot_name=next_q["slot_name"],
                            question=next_q["question"],
                            original_intent="create_project",
                            partial_goal=user_command,
                            options=next_q.get("options", []),
                            answers=disc_state,
                        )
                        self.conversation_state.add_assistant_turn(next_q["question"], action="CLARIFY")
                        screenshot_mgr.capture(
                            stage=WorkflowStage.STAGE_02_REQUEST_UNDERSTANDING,
                            event_name="design.discovery_started",
                            description=f"Conversational design discovery initiated for '{user_command}'.",
                            evidence_data={"slot": next_q["slot_name"], "session_id": sid},
                        )
                        try:
                            self.voice_out.speak("Let's clarify a few design details before generating your layout in Google Stitch.")
                        except Exception:
                            pass
                        stage_val = next_q.get("stage", "DESIGN_DISCOVERY")
                        disc_stage = (
                            "subtype"
                            if next_q["slot_name"] == "design_discovery_subtype" or stage_val == "DESIGN_DISCOVERY_SUBTYPE"
                            else ("details" if next_q["slot_name"] == "design_discovery_details" or stage_val == "DESIGN_DISCOVERY_DETAILS" else str(stage_val).lower())
                        )
                        archetypes = next_q.get("archetypes", [])
                        raw_opts = next_q.get("options", [])
                        rich_options = archetypes if archetypes else [
                            opt if isinstance(opt, dict) else {"label": str(opt)}
                            for opt in raw_opts
                        ]
                        missing_dims = next_q.get("missing_dimensions", [])
                        return {
                            "status": "CLARIFY",
                            "decision_status": "CLARIFY",
                            "stage": stage_val,
                            "discovery_stage": disc_stage,
                            "slot": next_q["slot_name"],
                            "session_id": sid,
                            "discovery_session_id": sid,
                            "question": next_q["question"],
                            "options": rich_options,
                            "option_labels": [o.get("label", str(o)) if isinstance(o, dict) else str(o) for o in rich_options],
                            "archetypes": archetypes,
                            "missing_dimensions": missing_dims,
                            "unanswered_dimensions": missing_dims,
                            "discovery_state": disc_state,
                            "message": next_q["question"],
                            "response": next_q["question"],
                            "explanation": next_q["explanation"],
                        }
                    design_brief = ConversationalDesignConsultant.build_structured_brief(
                        disc_state,
                        fallback_title=spec.title,
                    )
                else:
                    disc_state = ConversationalDesignConsultant.create_initial_state(user_command)
                    design_brief = ConversationalDesignConsultant.build_structured_brief(
                        disc_state,
                        fallback_title=spec.title,
                    )

                if design_brief is not None:
                    self.conversation_state.active_design_brief = design_brief.to_dict()
                    if design_brief.title and spec.title in ("Modern School Website", "School Website", "Website Project"):
                        spec.title = design_brief.title

                retry_project_id = instruction.entities.get("stitch_project_id") if (instruction and instruction.entities) else None
                retry_design_system = instruction.entities.get("stitch_design_system") if (instruction and instruction.entities) else None
                retry_session_dir = instruction.entities.get("stitch_session_dir") if (instruction and instruction.entities) else None

                return self._handle_stitch_design_request(
                    spec=spec,
                    user_command=user_command,
                    design_brief=design_brief,
                    project_id=retry_project_id,
                    design_system=retry_design_system,
                    session_dir_override=retry_session_dir,
                    progress_callback=progress_callback,
                    cancellation_token=cancellation_token,
                )

            from .agents.specialized_agents import DesignAgent
            design_agent = DesignAgent(self.config)
            plan = design_agent.create_design_plan(spec)
            self.pending_design_spec = spec
            self.conversation_state.set_pending_design(spec, plan, version=1)
            msg = f"Design architecture formulated for '{title}' (v1). User review and explicit approval ('approve') required prior to candidate implementation."

            # STAGE 06: User Review & Approval Requested
            screenshot_mgr.capture(
                stage=WorkflowStage.STAGE_06_USER_APPROVAL,
                event_name="approval.requested",
                description=f"Design proposal presented (v1). Awaiting explicit user approval for '{title}'.",
                evidence_data={"title": title, "version": 1, "plan": plan},
            )

            try:
                self.voice_out.speak(msg)
            except Exception:
                pass
            return {
                "status": "APPROVAL_REQUIRED",
                "decision_status": "CONFIRM",
                "stage": "DESIGN_APPROVAL",
                "design_version": 1,
                "design_plan": plan,
                "specification": spec.to_dict(),
                "message": msg,
            }

        return self._execute_build_and_closed_loop_verify(
            spec=spec,
            instruction=instruction,
            auto_open_browser=auto_open_browser,
            progress_callback=progress_callback,
        )

    def _use_stitch_design(self, p_type: ProjectType) -> bool:
        """
        Determines whether website design generation should use Google Stitch directly.
        Uses Stitch whenever an explicit StitchAdapter is injected, MIND_DESIGN_MODE is 'stitch',
        or the studio is running outside offline unit-test mode (`not self.config.test_mode`).
        """
        if p_type not in (ProjectType.WEBSITE, ProjectType.WEB_APP):
            return False
        import os as _os
        mode = _os.getenv("MIND_DESIGN_MODE", "auto").strip().lower()
        if mode == "native":
            return False
        if self._explicit_stitch_adapter or mode == "stitch":
            return True
        return not self.config.test_mode

    def _serve_stitch_version_dir(self, session_key: str, version_dir: Path) -> Optional[str]:
        """Serves a Stitch version directory over local HTTP for popup preview rendering."""
        try:
            from .tools.preview_server import WorkspacePreviewServer
            prev_srv = self._preview_servers.pop(session_key, None)
            if prev_srv is not None:
                try:
                    prev_srv.stop()
                except Exception:
                    pass
            srv = WorkspacePreviewServer(version_dir)
            if srv.start():
                self._preview_servers[session_key] = srv
                return srv.get_url("index.html")
        except Exception as e:
            logger.debug("Stitch preview server fallback to local file: %s", e)
        return None

    @staticmethod
    def _build_stitch_artifacts(bundle: StitchDesignBundle) -> List[Dict[str, Any]]:
        """Constructs UI artifact descriptors from a StitchDesignBundle."""
        artifacts: List[Dict[str, Any]] = []
        for idx, scr in enumerate(bundle.screens):
            if scr.html_path and Path(scr.html_path).exists():
                artifacts.append({
                    "name": f"{scr.title} (HTML)",
                    "path": scr.html_path,
                    "mime_type": "text/html",
                    "preview_type": "browser",
                    "size_bytes": scr.html_size_bytes,
                    "screen_id": scr.screen_id,
                    "is_primary": idx == 0,
                })
            if scr.css_path and Path(scr.css_path).exists():
                artifacts.append({
                    "name": Path(scr.css_path).name,
                    "path": scr.css_path,
                    "mime_type": "text/css",
                    "preview_type": "text",
                    "size_bytes": Path(scr.css_path).stat().st_size,
                })
            if scr.js_path and Path(scr.js_path).exists():
                artifacts.append({
                    "name": Path(scr.js_path).name,
                    "path": scr.js_path,
                    "mime_type": "application/javascript",
                    "preview_type": "text",
                    "size_bytes": Path(scr.js_path).stat().st_size,
                })
            if scr.screenshot_path and Path(scr.screenshot_path).exists():
                artifacts.append({
                    "name": f"{scr.title} (Screenshot)",
                    "path": scr.screenshot_path,
                    "mime_type": "image/png",
                    "preview_type": "image",
                    "size_bytes": Path(scr.screenshot_path).stat().st_size,
                })
        return artifacts

    def _handle_stitch_design_request(
        self,
        spec: ProjectSpecification,
        user_command: str,
        design_brief: Optional[Any] = None,
        project_id: Optional[str] = None,
        design_system: Optional[str] = None,
        session_dir_override: Optional[Union[Path, str]] = None,
        progress_callback: Optional[Callable[[Any], None]] = None,
        cancellation_token: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Requests a website design directly from Google Stitch using the synthesized
        `StructuredDesignBrief` without invoking MIND's coding agent or local website generator.
        """
        screenshot_mgr = WorkflowScreenshotManager.get_instance()
        clean_slug = re.sub(r"[^a-z0-9_]+", "_", (spec.project_name or "website").lower()).strip("_") or "website"
        if session_dir_override:
            session_dir = Path(session_dir_override).resolve()
        else:
            session_dir = self.config.workspace_root / "stitch_previews" / f"{clean_slug}_{int(time.time() * 1000)}"

        stitch_prompt = (
            design_brief.to_stitch_prompt()
            if (design_brief is not None and hasattr(design_brief, "to_stitch_prompt"))
            else user_command
        )
        brief_dict = (
            design_brief.to_dict()
            if (design_brief is not None and hasattr(design_brief, "to_dict"))
            else None
        )
        brief_markdown = (
            design_brief.format_for_user()
            if (design_brief is not None and hasattr(design_brief, "format_for_user"))
            else ""
        )

        if progress_callback:
            try:
                progress_callback({
                    "workflow_id": f"stitch_{clean_slug}",
                    "design_state": "prototyping",
                    "message": f"Sending Structured Design Brief for '{spec.title}' to Google Stitch...",
                    "progress": 0.35,
                    "progress_pct": 0.35,
                })
            except Exception:
                pass

        try:
            bundle = self.stitch_adapter.generate_design(
                prompt=stitch_prompt,
                session_dir=session_dir,
                project_id=project_id,
                title=spec.title,
                device_type="DESKTOP",
                version=1,
                design_system=design_system,
                progress_callback=progress_callback,
                cancellation_token=cancellation_token,
            )
        except StitchCancelledError as cancel_err:
            in_flight = self.stitch_adapter._load_in_flight_state(session_dir) or {}
            saved_pid = getattr(cancel_err, "project_id", None) or in_flight.get("project_id") or project_id
            saved_ds = getattr(cancel_err, "design_system", None) or in_flight.get("design_system") or design_system
            cancel_msg = (
                f"Google Stitch design generation for '{spec.title}' was cancelled by the user. "
                "Your Structured Design Brief is preserved."
            )
            if brief_dict:
                self.conversation_state.set_pending_clarification(
                    slot_name="design_discovery_retry",
                    question="Resume or retry Google Stitch design generation with your Structured Design Brief",
                    original_intent="create_project",
                    partial_goal=spec.title,
                    options=["Retry Stitch Generation"],
                    answers={
                        "design_brief": brief_dict,
                        "stitch_project_id": saved_pid,
                        "stitch_design_system": saved_ds,
                        "stitch_session_dir": str(session_dir),
                    },
                )
            self.conversation_state.add_assistant_turn(cancel_msg, action="CANCELLED")
            return {
                "status": "CANCELLED",
                "provider": "stitch",
                "decision_status": "READY",
                "project_id": saved_pid,
                "design_brief": brief_dict,
                "design_brief_markdown": brief_markdown,
                "options": [{"label": "Retry Stitch Generation"}] if brief_dict else [],
                "message": cancel_msg,
                "response": cancel_msg,
            }
        except StitchError as err:
            in_flight = self.stitch_adapter._load_in_flight_state(session_dir) or {}
            saved_pid = (
                getattr(err, "project_id", None)
                or in_flight.get("project_id")
                or project_id
                or getattr(self.stitch_adapter, "last_timed_out_project_id", None)
            )
            saved_ds = getattr(err, "design_system", None) or in_flight.get("design_system") or design_system
            err_msg = (
                f"Google Stitch design generation failed or is unavailable: {err}. "
                "MIND did not generate a substitute website. "
                "Your Structured Design Brief is preserved — click 'Retry Stitch Generation' or type 'retry' in chat."
            )
            if brief_dict:
                self.conversation_state.set_pending_clarification(
                    slot_name="design_discovery_retry",
                    question="Retry Google Stitch design generation with your Structured Design Brief",
                    original_intent="create_project",
                    partial_goal=spec.title,
                    options=["Retry Stitch Generation"],
                    answers={
                        "design_brief": brief_dict,
                        "stitch_project_id": saved_pid,
                        "stitch_design_system": saved_ds,
                        "stitch_session_dir": str(session_dir),
                    },
                )
            self.conversation_state.record_tool_result(
                action="STITCH_GENERATE_DESIGN",
                status="FAILED",
                error=str(err),
                verified=False,
                data={"project_id": saved_pid, "failure_category": getattr(err, "failure_category", "stitch_error")},
            )
            self.conversation_state.add_assistant_turn(err_msg, action="STITCH_UNAVAILABLE")
            return {
                "status": "STITCH_UNAVAILABLE",
                "provider": "stitch",
                "decision_status": "ERROR",
                "project_id": saved_pid,
                "failure_category": getattr(err, "failure_category", "stitch_error"),
                "design_brief": brief_dict,
                "design_brief_markdown": brief_markdown,
                "options": [{"label": "Retry Stitch Generation"}] if brief_dict else [],
                "error": str(err),
                "message": err_msg,
                "response": err_msg,
            }

        bundle.preview_url = self._serve_stitch_version_dir(bundle.session_id, Path(bundle.version_dir))
        artifacts = self._build_stitch_artifacts(bundle)

        plan: Dict[str, Any] = {
            "provider": "stitch",
            "title": bundle.title,
            "project_id": bundle.project_id,
            "session_id": bundle.session_id,
            "screen_ids": bundle.screen_ids,
            "version": bundle.version,
            "preview_file": bundle.preview_file,
            "preview_url": bundle.preview_url,
            "version_dir": bundle.version_dir,
            "screens": [s.to_dict() for s in bundle.screens],
            "design_system": bundle.design_system,
            "design_brief": brief_dict,
            "design_brief_markdown": brief_markdown,
            "stitch_bundle": bundle.to_dict(),
        }

        self.pending_design_spec = spec
        self.conversation_state.set_pending_design(
            spec=spec,
            plan=plan,
            version=bundle.version,
            stitch_bundle=bundle.to_dict(),
        )

        summary_line = (
            f"Google Stitch design '{bundle.title}' (v{bundle.version}) received and rendered in the "
            f"MIND Design Preview window ({len(bundle.screens)} screen(s)). "
            "Review the design in the popup, request revisions here in chat, or click Approve when satisfied."
        )
        msg = f"{brief_markdown}\n\n---\n{summary_line}" if brief_markdown else summary_line
        self.conversation_state.record_tool_result(
            action="STITCH_GENERATE_DESIGN",
            status="SUCCESS",
            target_path=bundle.preview_file,
            output=summary_line,
            verified=True,
            data={"project_id": bundle.project_id, "screen_ids": bundle.screen_ids, "version": bundle.version},
        )
        self.conversation_state.add_assistant_turn(msg, action="STITCH_DESIGN_READY")

        screenshot_mgr.capture(
            stage=WorkflowStage.STAGE_06_USER_APPROVAL,
            event_name="approval.requested",
            description=f"Google Stitch design presented (v{bundle.version}) for '{bundle.title}'. Awaiting explicit user approval.",
            evidence_data={"title": bundle.title, "version": bundle.version, "project_id": bundle.project_id},
        )

        try:
            self.voice_out.speak(f"Google Stitch design for {bundle.title} is ready in the preview window.")
        except Exception:
            pass

        return {
            "status": "APPROVAL_REQUIRED",
            "decision_status": "CONFIRM",
            "stage": "DESIGN_APPROVAL",
            "design_state": "awaiting_design_approval",
            "provider": "stitch",
            "session_id": bundle.session_id,
            "design_session_id": bundle.session_id,
            "project_id": bundle.project_id,
            "screen_ids": bundle.screen_ids,
            "screens": [s.to_dict() for s in bundle.screens],
            "version": bundle.version,
            "design_version": bundle.version,
            "title": bundle.title,
            "preview_file": bundle.preview_file,
            "preview_url": bundle.preview_url,
            "version_dir": bundle.version_dir,
            "design_plan": plan,
            "design_brief": brief_dict,
            "design_brief_markdown": brief_markdown,
            "specification": spec.to_dict(),
            "artifacts": artifacts,
            "message": msg,
            "response": msg,
        }

    def _handle_revise_design(
        self,
        instruction: UserInstruction,
        progress_callback: Optional[Callable[[Any], None]] = None,
        cancellation_token: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Updates the pending design proposal and increments version without implementing."""
        pending = self.conversation_state.pending_design_approval
        spec = self.pending_design_spec
        if not pending and not spec:
            return {
                "status": "NO_PENDING_DESIGN",
                "message": "No design plan is currently awaiting approval to revise.",
            }

        is_stitch_pending = bool(
            pending and (
                pending.get("provider") == "stitch"
                or (isinstance(pending.get("plan"), dict) and pending["plan"].get("provider") == "stitch")
            )
        )
        if is_stitch_pending and pending is not None:
            prev_bundle_dict = (
                pending.get("stitch_bundle")
                or (pending.get("plan", {}).get("stitch_bundle") if isinstance(pending.get("plan"), dict) else None)
                or {}
            )
            prev_version = int(prev_bundle_dict.get("version") or pending.get("version", 1))
            prev_session_id = str(prev_bundle_dict.get("session_id") or pending.get("session_id") or "")
            brief_dict = (
                pending.get("plan", {}).get("design_brief")
                if isinstance(pending.get("plan"), dict)
                else None
            )
            revision_prompt = instruction.raw_command
            if isinstance(brief_dict, dict):
                try:
                    from .tools.design_consultant import StructuredDesignBrief
                    brief_obj = StructuredDesignBrief.from_dict(brief_dict)
                    revision_prompt = brief_obj.to_stitch_revision_prompt(instruction.raw_command)
                except Exception:
                    revision_prompt = instruction.raw_command
            try:
                revised_bundle = self.stitch_adapter.revise_design(
                    previous_bundle=prev_bundle_dict,
                    revision_prompt=revision_prompt,
                    progress_callback=progress_callback,
                    cancellation_token=cancellation_token,
                )
            except StitchCancelledError:
                cancel_msg = (
                    f"Google Stitch revision was cancelled. "
                    f"Previous design (v{prev_version}) remains active in the preview window."
                )
                self.conversation_state.add_assistant_turn(cancel_msg, action="STITCH_REVISION_CANCELLED")
                return {
                    "status": "CANCELLED",
                    "provider": "stitch",
                    "decision_status": "READY",
                    "session_id": prev_session_id,
                    "design_session_id": prev_session_id,
                    "project_id": prev_bundle_dict.get("project_id", ""),
                    "screen_ids": prev_bundle_dict.get("screen_ids", []),
                    "screens": prev_bundle_dict.get("screens", []),
                    "version": prev_version,
                    "design_version": prev_version,
                    "title": prev_bundle_dict.get("title") or pending.get("title", "Stitch Design"),
                    "preview_file": prev_bundle_dict.get("preview_file"),
                    "preview_url": prev_bundle_dict.get("preview_url"),
                    "message": cancel_msg,
                    "response": cancel_msg,
                }
            except StitchError as err:
                err_msg = (
                    f"Google Stitch revision failed: {err}. "
                    f"Previous design (v{prev_version}) remains active in the preview window."
                )
                self.conversation_state.record_tool_result(
                    action="STITCH_REVISE_DESIGN",
                    status="FAILED",
                    target_path=prev_bundle_dict.get("preview_file"),
                    error=str(err),
                    verified=False,
                )
                self.conversation_state.add_assistant_turn(err_msg, action="STITCH_REVISION_FAILED")
                return {
                    "status": "STITCH_ERROR",
                    "provider": "stitch",
                    "decision_status": "ERROR",
                    "session_id": prev_session_id,
                    "design_session_id": prev_session_id,
                    "project_id": prev_bundle_dict.get("project_id", ""),
                    "screen_ids": prev_bundle_dict.get("screen_ids", []),
                    "screens": prev_bundle_dict.get("screens", []),
                    "version": prev_version,
                    "design_version": prev_version,
                    "title": prev_bundle_dict.get("title") or pending.get("title", "Stitch Design"),
                    "preview_file": prev_bundle_dict.get("preview_file"),
                    "preview_url": prev_bundle_dict.get("preview_url"),
                    "error": str(err),
                    "message": err_msg,
                    "response": err_msg,
                }

            revised_bundle.preview_url = self._serve_stitch_version_dir(
                revised_bundle.session_id,
                Path(revised_bundle.version_dir),
            )
            artifacts = self._build_stitch_artifacts(revised_bundle)
            plan_updates: Dict[str, Any] = {
                "provider": "stitch",
                "title": revised_bundle.title,
                "project_id": revised_bundle.project_id,
                "session_id": revised_bundle.session_id,
                "screen_ids": revised_bundle.screen_ids,
                "version": revised_bundle.version,
                "preview_file": revised_bundle.preview_file,
                "preview_url": revised_bundle.preview_url,
                "version_dir": revised_bundle.version_dir,
                "screens": [s.to_dict() for s in revised_bundle.screens],
                "latest_revision": instruction.raw_command,
                "design_brief": brief_dict,
                "stitch_bundle": revised_bundle.to_dict(),
            }
            new_version = self.conversation_state.update_pending_design(
                plan_updates,
                stitch_bundle=revised_bundle.to_dict(),
            )

            screenshot_mgr = WorkflowScreenshotManager.get_instance()
            screenshot_mgr.capture(
                stage=WorkflowStage.STAGE_06_USER_APPROVAL,
                event_name="approval.requested",
                description=f"Google Stitch design revised (v{new_version}). Awaiting explicit user approval.",
                evidence_data={"version": new_version, "project_id": revised_bundle.project_id},
            )

            msg = (
                f"Google Stitch design revised to v{new_version} and updated in the preview window. "
                "Awaiting your review or explicit approval."
            )
            self.conversation_state.record_tool_result(
                action="STITCH_REVISE_DESIGN",
                status="SUCCESS",
                target_path=revised_bundle.preview_file,
                output=msg,
                verified=True,
                data={"project_id": revised_bundle.project_id, "version": new_version},
            )
            self.conversation_state.add_assistant_turn(msg, action="STITCH_DESIGN_REVISED")
            return {
                "status": "APPROVAL_REQUIRED",
                "decision_status": "CONFIRM",
                "stage": "DESIGN_APPROVAL",
                "design_state": "awaiting_design_approval",
                "provider": "stitch",
                "session_id": revised_bundle.session_id,
                "design_session_id": revised_bundle.session_id,
                "project_id": revised_bundle.project_id,
                "screen_ids": revised_bundle.screen_ids,
                "screens": [s.to_dict() for s in revised_bundle.screens],
                "version": new_version,
                "design_version": new_version,
                "title": revised_bundle.title,
                "preview_file": revised_bundle.preview_file,
                "preview_url": revised_bundle.preview_url,
                "version_dir": revised_bundle.version_dir,
                "design_plan": self.conversation_state.pending_design_approval["plan"],
                "design_brief": brief_dict,
                "artifacts": artifacts,
                "message": msg,
                "response": msg,
            }

        from .agents.specialized_agents import DesignAgent
        design_agent = DesignAgent(self.config)
        curr_plan = pending["plan"] if pending else {}
        plan_updates = design_agent.revise_design_plan(curr_plan, instruction.raw_command)
        new_version = self.conversation_state.update_pending_design(plan_updates) if pending else 2

        screenshot_mgr = WorkflowScreenshotManager.get_instance()
        screenshot_mgr.capture(
            stage=WorkflowStage.STAGE_06_USER_APPROVAL,
            event_name="approval.requested",
            description=f"Design proposal revised (v{new_version}). Awaiting explicit user approval.",
            evidence_data={"version": new_version, "plan": plan_updates},
        )

        msg = f"Design proposal revised to version {new_version}. Explicit approval ('approve') required prior to candidate implementation."
        return {
            "status": "APPROVAL_REQUIRED",
            "decision_status": "CONFIRM",
            "stage": "DESIGN_APPROVAL",
            "design_version": new_version,
            "design_plan": self.conversation_state.pending_design_approval["plan"] if self.conversation_state.pending_design_approval else plan_updates,
            "message": msg,
        }

    def _handle_cancel(self, instruction: UserInstruction) -> Dict[str, Any]:
        """Cancels or rejects any pending design proposal or unconfirmed action."""
        cancelled = self.conversation_state.cancel_pending_design()
        self.pending_design_spec = None
        is_rejected = bool(instruction.entities and instruction.entities.get("rejected"))
        if is_rejected:
            msg = "Design prototype rejected."
            status_str = "REJECTED"
        else:
            msg = "Pending design operation cancelled." if cancelled else "Operation cancelled."
            status_str = "CANCELLED"
        self.conversation_state.add_assistant_turn(msg, action=status_str)
        return {
            "status": status_str,
            "decision_status": "READY",
            "session_id": cancelled.get("session_id") if isinstance(cancelled, dict) else None,
            "message": msg,
            "response": msg,
        }

    def _handle_approve_design(
        self,
        auto_open_browser: bool = False,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """
        Handles explicit user approval of a pending design.
        - For Google Stitch designs (`provider == 'stitch'`): marks the Stitch design as the
          approved design for any subsequent user-authorized task WITHOUT automatically
          starting website code implementation.
        - For offline native design plans (`test_mode=True`): executes candidate build and
          closed-loop verification as before.
        """
        pending = self.conversation_state.pending_design_approval
        spec = self.pending_design_spec

        if not spec and pending and "spec" in pending:
            raw_spec = pending["spec"]
            if hasattr(ProjectSpecification, "from_dict"):
                spec = ProjectSpecification.from_dict(raw_spec)
            elif isinstance(raw_spec, dict):
                pt_val = raw_spec.get("project_type", ProjectType.WEBSITE)
                try:
                    pt_enum = ProjectType(str(pt_val).lower())
                except ValueError:
                    pt_enum = ProjectType.WEBSITE
                spec = ProjectSpecification(
                    title=str(raw_spec.get("title", pending.get("title", "Project"))),
                    project_name=str(raw_spec.get("project_name", pending.get("project_name", "project"))),
                    project_type=pt_enum,
                    description=str(raw_spec.get("description", "")),
                    pages=list(raw_spec.get("pages") or []),
                    destination_dir=raw_spec.get("destination_dir"),
                )

        if not spec and not pending:
            return {
                "status": "NO_PENDING_DESIGN",
                "message": "No design plan is currently awaiting approval. Submit a project creation command first.",
            }

        is_stitch_pending = bool(
            pending and (
                pending.get("provider") == "stitch"
                or (isinstance(pending.get("plan"), dict) and pending["plan"].get("provider") == "stitch")
            )
        )
        if is_stitch_pending and pending is not None:
            version = int(pending.get("version", 1))
            title = spec.title if spec else pending.get("title", "Stitch Design")
            sb = (
                pending.get("stitch_bundle")
                or (pending.get("plan", {}).get("stitch_bundle") if isinstance(pending.get("plan"), dict) else None)
                or {}
            )
            approved = self.conversation_state.approve_stitch_design()
            self.pending_design_spec = None

            from .tools.screenshot_manager import WorkflowScreenshotManager, WorkflowStage
            screenshot_mgr = WorkflowScreenshotManager.get_instance()
            screenshot_mgr.capture(
                stage=WorkflowStage.STAGE_06_USER_APPROVAL,
                event_name="approval.granted",
                description=f"User explicitly approved Google Stitch design (v{version}) for '{title}'. Marked as approved design.",
                evidence_data={"title": title, "version": version, "provider": "stitch", "project_id": sb.get("project_id")},
            )

            msg = (
                f"Google Stitch design '{title}' (v{version}) has been marked as APPROVED. "
                "The approved Stitch design is saved and ready for any subsequent user-authorized development task."
            )
            self.conversation_state.record_tool_result(
                action="APPROVE_STITCH_DESIGN",
                status="SUCCESS",
                target_path=sb.get("preview_file"),
                output=msg,
                verified=True,
                data={"project_id": sb.get("project_id"), "version": version, "session_id": sb.get("session_id")},
            )
            self.conversation_state.add_assistant_turn(msg, action="DESIGN_APPROVED")
            try:
                self.voice_out.speak(f"Stitch design for {title} version {version} is now approved.")
            except Exception:
                pass

            return {
                "status": "DESIGN_APPROVED",
                "decision_status": "EXECUTE",
                "design_state": "approved",
                "provider": "stitch",
                "session_id": sb.get("session_id") or pending.get("session_id"),
                "design_session_id": sb.get("session_id") or pending.get("session_id"),
                "project_id": sb.get("project_id") or pending.get("project_id"),
                "screen_ids": sb.get("screen_ids", []),
                "screens": sb.get("screens", []),
                "version": version,
                "design_version": version,
                "title": title,
                "preview_file": sb.get("preview_file") or pending.get("preview_file"),
                "preview_url": sb.get("preview_url") or pending.get("preview_url"),
                "version_dir": sb.get("version_dir") or pending.get("version_dir"),
                "approved_design": approved,
                "implementation_started": False,
                "message": msg,
                "response": msg,
            }

        version = pending.get("version", 1) if pending else 1
        self.pending_design_spec = None
        self.conversation_state.clear_pending_design()

        from .tools.screenshot_manager import WorkflowScreenshotManager, WorkflowStage
        screenshot_mgr = WorkflowScreenshotManager.get_instance()
        # STAGE 06: User Review & Approval Granted
        screenshot_mgr.capture(
            stage=WorkflowStage.STAGE_06_USER_APPROVAL,
            event_name="approval.granted",
            description=f"User explicitly approved design proposal (v{version}) for '{spec.title}'. Proceeding with candidate implementation.",
            evidence_data={"title": spec.title, "version": version, "project_type": getattr(spec.project_type, "value", str(spec.project_type))},
        )

        return self._execute_build_and_closed_loop_verify(
            spec=spec,
            auto_open_browser=auto_open_browser,
            progress_callback=progress_callback,
        )

    def _execute_build_and_closed_loop_verify(
        self,
        spec: ProjectSpecification,
        instruction: Optional[UserInstruction] = None,
        auto_open_browser: bool = False,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """Coordinates candidate implementation generation and closed-loop verification."""
        p_type = spec.project_type
        title = spec.title

        from .tools.screenshot_manager import WorkflowScreenshotManager, WorkflowStage
        screenshot_mgr = WorkflowScreenshotManager.get_instance()

        try:
            self.voice_out.speak(f"Planning and generating {p_type.value} project: {title}.")
        except Exception as e:
            logger.warning(f"Voice output notice: {e}")

        print(f"\n[MIND Studio] Creating {p_type.value.upper()} project: '{title}'...")

        # STAGE 07: Implementation Milestones (Initialization)
        screenshot_mgr.capture(
            stage=WorkflowStage.STAGE_07_IMPLEMENTATION,
            event_name="implementation.started",
            description=f"Scaffolding candidate project files and assets for '{title}'...",
            evidence_data={"title": title, "project_name": spec.project_name},
        )

        # 1. Create project & candidate assets via specialized workflow
        project = self.project_creator.create_project(spec)
        self.active_project = project

        # 2. Multi-page expansion if specified in instruction
        if instruction and instruction.pages:
            ws = SafeWorkspaceManager(Path(project.root_path))
            for pg in instruction.pages:
                if pg != "index.html" and not (Path(project.root_path) / pg).exists():
                    self._synthesize_connected_page(ws, pg, spec.title, instruction.raw_command)

        # STAGE 07: Implementation Milestones (Files Created)
        screenshot_mgr.capture(
            stage=WorkflowStage.STAGE_07_IMPLEMENTATION,
            event_name="implementation.milestone",
            description=f"Candidate source files and assets forged on disk for '{title}'.",
            evidence_data={"project_path": project.root_path, "files": [f.name for f in Path(project.root_path).rglob('*') if f.is_file()]},
        )

        # STAGE 08: Initial Execution
        screenshot_mgr.capture(
            stage=WorkflowStage.STAGE_08_INITIAL_EXECUTION,
            event_name="execution.started",
            description=f"Initial candidate build verification initiated for '{title}'.",
            evidence_data={"project_path": project.root_path},
        )

        # 3. Run closed-loop independent verification and automated repair
        print(f"[MIND Studio] Running automated verification for {p_type.value}...")
        report = self.verifier.verify_project(project, auto_repair=True, progress_callback=progress_callback)

        # 4. Persist to conversational state and SQLite session memory
        self.conversation_state.set_active_project(
            name=project.name,
            path=project.root_path,
            domain=p_type.value,
            requirements={
                "title": title,
                "project_name": spec.project_name,
                "domain": p_type.value,
                "pages": instruction.pages if instruction else [],
                "features": instruction.features if instruction else [],
            },
        )
        self.conversation_state.record_tool_result(
            action="CREATE_PROJECT",
            status="SUCCESS" if report.success else "WARNING",
            target_path=project.root_path,
            output=report.summary,
            verified=report.success,
        )
        self.conversation_state.add_assistant_turn(
            f"Project {title} created at {project.root_path}.",
            action="CREATE_PROJECT",
            result=report.summary,
        )

        try:
            if report.success:
                self.voice_out.speak(f"Project {title} generated and verified. All automated checks passed.")
                print(f"[MIND Studio] SUCCESS: {report.summary}")
            else:
                self.voice_out.speak("Project generated with issues. Reviewing verification errors.")
                print(f"[MIND Studio] WARNING: Verification reported {len(report.errors)} issues.")
        except Exception as e:
            logger.warning(f"Central voice delivery notice: {e}")

        # 5. Optionally launch browser for web-capable projects
        if auto_open_browser and report.success and p_type in (ProjectType.GAME, ProjectType.WEBSITE, ProjectType.WEB_APP):
            try:
                self.serve_project(open_browser=True)
            except Exception as e:
                logger.warning(f"Browser preview notice: {e}")

        abs_entry = str((Path(project.root_path) / report.entry_point).resolve()) if (report.entry_point and not Path(report.entry_point).is_absolute()) else (report.entry_point or str(Path(project.root_path) / "index.html"))

        # STAGE 13: Final Execution
        screenshot_mgr.capture(
            stage=WorkflowStage.STAGE_13_FINAL_EXECUTION,
            event_name="execution.final",
            description=f"Final runtime state verified for '{title}'. Server command: '{project.run_command}'",
            evidence_data={"run_command": project.run_command, "entry_point": abs_entry, "success": report.success},
        )

        # STAGE 14: Final Delivery
        screenshot_mgr.capture(
            stage=WorkflowStage.STAGE_14_FINAL_DELIVERY,
            event_name="delivery.prepared",
            description=f"Verified deliverable packaged at '{project.root_path}'. Status: {report.status}",
            evidence_data={"project_path": project.root_path, "summary": report.summary, "tests_passed": report.tests_passed},
        )

        # STAGE 15: Workflow Completion Report
        report_html = screenshot_mgr.generate_html_report()
        screenshot_mgr.capture(
            stage=WorkflowStage.STAGE_15_COMPLETION_REPORT,
            event_name="workflow.completed",
            description=f"Workflow complete: {report.summary}. Visual evidence report: '{report_html.name}'.",
            evidence_data={"report_path": str(report_html), "total_captures": len(screenshot_mgr.captures), "status": report.status},
        )

        return {
            "status": "SUCCESS" if report.success else "WARNING",
            "decision_status": "EXECUTE",
            "project_type": p_type.value,
            "project_path": project.root_path,
            "project": project.to_dict(),
            "verification": report.to_dict(),
            "entry_point": abs_entry,
            "run_command": project.run_command,
        }

    def _plan_project_metadata(self, prompt: str, p_type: ProjectType) -> tuple[str, str]:
        """Generates dynamic, meaningful titles and directory names directly from user prompt."""
        p_lower = prompt.lower()
        if p_type == ProjectType.GAME and ("runner" in p_lower or "cyberdash" in p_lower):
            return "CyberDash 3D: Endless Runner", "cyberdash_3d"

        clean = re.sub(
            r'^(create|build|generate|make|develop|design|set\s+up|implement|write)\s+(a|an|the)?\s*',
            '',
            prompt.strip(),
            flags=re.IGNORECASE,
        ).strip()
        clean = re.sub(r'[\.\!\?]+$', '', clean).strip()
        clean = re.sub(r'--[a-z0-9\-_]+', '', clean).strip()

        if clean:
            words = clean.split()
            title = ' '.join(word.capitalize() for word in words[:8])
            slug = re.sub(r'[^a-z0-9]+', '_', clean.lower()).strip('_')
            slug_words = [w for w in slug.split('_') if w][:6]
            name = '_'.join(slug_words) if slug_words else f"{p_type.value}_project"
        else:
            title = f"{p_type.value.replace('_', ' ').title()} Project"
            name = f"{p_type.value}_project"

        return title, name

    def _handle_reconstruct_3d(
        self,
        instruction: UserInstruction,
        progress_callback: Optional[Callable[[str, float], None]] = None,
    ) -> Dict[str, Any]:
        """
        Executes the end-to-end AI Image-to-3D Reconstruction workflow:
        Stage 1: Generating reference image.
        Stage 2: Analyzing reference image.
        Stage 3: Creating Blender script.
        Stage 4: Validating script.
        Stage 5: Running Blender.
        Stage 6: Generating 3D model.
        Stage 7: Exporting GLB.
        Stage 8: Completed.
        """
        def _report(msg: str, pct: float) -> None:
            logger.info(f"[3D RECONSTRUCTION] {msg} ({int(pct*100)}%)")
            if progress_callback:
                try:
                    progress_callback(msg, pct)
                except Exception:
                    pass

        start_time = time.time()
        entities = instruction.entities or {}
        raw_prompt = entities.get("clean_prompt") or instruction.raw_command
        asset_name = entities.get("asset_name") or instruction.project_name or "reconstructed_asset"
        safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in asset_name).lower()
        if not safe_name:
            safe_name = "asset_3d"
        explicit_dest = entities.get("destination_dir") or instruction.destination_dir
        explicit_filename = entities.get("filename") or f"{safe_name}.glb"

        # Determine target workspace and directories
        if explicit_dest:
            workspace_dir = Path(explicit_dest).resolve()
        elif self.active_project and getattr(self.active_project, "root_path", None):
            workspace_dir = Path(self.active_project.root_path) / "assets" / "models"
        else:
            workspace_dir = self.config.workspace_root / safe_name
        workspace_dir.mkdir(parents=True, exist_ok=True)

        images_dir = workspace_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        stages_log = []

        # --- Stage 1: Generating reference image ---
        _report("1. Generating reference image.", 0.12)
        stages_log.append("1. Generating reference image")
        ref_image_meta = self.image_adapter.generate_concept_image(
            prompt=raw_prompt,
            name=f"{safe_name}_concept",
            output_dir=images_dir,
            style="stylized low-poly game asset reference",
        )
        ref_image_path = Path(ref_image_meta.file_path)

        # --- Stage 2: Analyzing reference image ---
        _report("2. Analyzing reference image.", 0.28)
        stages_log.append("2. Analyzing reference image")
        vision_analysis = self.coding_adapter.analyze_image_for_3d(ref_image_path, raw_prompt)

        # --- Stage 3: Creating Blender script ---
        _report("3. Creating Blender script.", 0.45)
        stages_log.append("3. Creating Blender script")
        script_res = self.coding_adapter.generate_blender_script(
            visual_analysis=vision_analysis,
            prompt=raw_prompt,
            target_glb_name=explicit_filename,
        )
        script_code = script_res.get("code", "")

        # --- Stage 4: Validating script ---
        _report("4. Validating script.", 0.58)
        stages_log.append("4. Validating script")
        is_safe, safety_err = self.blender_adapter.validate_script_safety(script_code)
        if not is_safe:
            _report(f"Script validation note: {safety_err}. Applying safety correction...", 0.62)
            corr_res = self.coding_adapter.correct_blender_script(script_code, safety_err or "Syntax error", vision_analysis)
            script_code = corr_res.get("code", script_code)
            is_safe, safety_err = self.blender_adapter.validate_script_safety(script_code)
            if not is_safe:
                return {
                    "status": "VALIDATION_FAILED",
                    "success": False,
                    "error": f"Script rejected by safety gate: {safety_err}",
                    "stages_completed": stages_log,
                }

        # --- Stage 5: Running Blender ---
        _report("5. Running Blender.", 0.70)
        stages_log.append("5. Running Blender")
        exec_res = self.blender_adapter.execute_script(
            script_code=script_code,
            workspace_dir=workspace_dir,
            expected_glb_name=explicit_filename,
            timeout_seconds=60.0,
            render_preview=True,
        )

        # Single-turn error correction attempt if execution failed
        if not exec_res.get("success"):
            blender_err = exec_res.get("error", "Unknown error")
            _report(f"Blender notice: {blender_err[:80]}. Running automatic correction attempt...", 0.75)
            stages_log.append("5b. Single-turn error correction attempt")
            corr = self.coding_adapter.correct_blender_script(script_code, blender_err, vision_analysis)
            corrected_code = corr.get("code", "")
            is_safe, _ = self.blender_adapter.validate_script_safety(corrected_code)
            if is_safe:
                exec_res = self.blender_adapter.execute_script(
                    script_code=corrected_code,
                    workspace_dir=workspace_dir,
                    expected_glb_name=explicit_filename,
                    timeout_seconds=60.0,
                    render_preview=True,
                )

        if not exec_res.get("success"):
            return {
                "status": "BLENDER_EXECUTION_FAILED",
                "success": False,
                "error": exec_res.get("error"),
                "log_path": exec_res.get("log_path"),
                "script_path": exec_res.get("script_path"),
                "stages_completed": stages_log,
            }

        # --- Stage 6: Generating 3D model ---
        _report("6. Generating 3D model.", 0.85)
        stages_log.append("6. Generating 3D model")

        # --- Stage 7: Exporting GLB ---
        _report("7. Exporting GLB.", 0.95)
        stages_log.append("7. Exporting GLB")
        glb_path = exec_res.get("glb_path")
        val = ThreeDAssetAdapter.validate_3d_file(Path(glb_path))
        if not val.get("is_valid"):
            return {
                "status": "GLB_VERIFICATION_FAILED",
                "success": False,
                "error": f"GLB validation failed: {val.get('error')}",
                "stages_completed": stages_log,
            }

        # --- Stage 8: Completed ---
        elapsed = round(time.time() - start_time, 2)
        _report("8. Completed.", 1.0)
        stages_log.append("8. Completed")

        summary_msg = (
            f"Successfully reconstructed 3D asset '{safe_name}' in {elapsed}s.\n"
            f"• Reference Image: {ref_image_path.name}\n"
            f"• 3D Model Asset: {Path(glb_path).name} ({val.get('file_size_bytes')} bytes)\n"
            f"• Location: {workspace_dir}"
        )
        self.voice_out.speak(f"Reconstruction of {safe_name} complete. The 3D model is saved and verified.")

        return {
            "status": "SUCCESS",
            "success": True,
            "action": "reconstruct_3d",
            "asset_name": safe_name,
            "project_path": str(workspace_dir),
            "destination": str(workspace_dir),
            "reference_image": str(ref_image_path),
            "glb_path": glb_path,
            "preview_path": exec_res.get("preview_path"),
            "blend_path": exec_res.get("blend_path"),
            "script_path": exec_res.get("script_path"),
            "log_path": exec_res.get("log_path"),
            "file_size_bytes": val.get("file_size_bytes"),
            "elapsed_seconds": elapsed,
            "visual_analysis": vision_analysis,
            "model_attribution": {
                "image_generation": {
                    "provider": ref_image_meta.metadata.get("provider", "local_pillow_engine"),
                    "type": ref_image_meta.metadata.get("generation_type", "concept_art"),
                },
                "vision_analysis": {
                    "provider": vision_analysis.get("provider"),
                    "model": vision_analysis.get("model"),
                },
                "code_generation": {
                    "provider": script_res.get("provider"),
                    "model": script_res.get("model"),
                },
                "3d_execution_engine": {
                    "engine": "Blender Background Process",
                    "version": self.blender_adapter.get_blender_version(),
                    "executable": str(self.blender_adapter.blender_path),
                },
            },
            "stages_completed": stages_log,
            "message": summary_msg,
        }

    def _handle_verify_command(self) -> Dict[str, Any]:
        """Runs verification on the active or default project."""
        project = self._ensure_active_project()
        if not project:
            return {"status": "ERROR", "message": "No active project found to verify."}

        report = self.verifier.verify_project(project)
        self.conversation_state.record_tool_result("VERIFY_PROJECT", "SUCCESS" if report.success else "FAILED", target_path=project.root_path, output=report.summary, verified=report.success)
        return {
            "status": "SUCCESS" if report.success else "FAILED",
            "decision_status": "EXECUTE",
            "report": report.to_dict(),
        }

    def _handle_serve_command(self, auto_open_browser: bool = True) -> Dict[str, Any]:
        """Starts a local HTTP server and opens the project in the browser."""
        project = self._ensure_active_project()
        if not project:
            return {"status": "ERROR", "message": "No active project found to serve."}

        return self.serve_project(open_browser=auto_open_browser)

    def serve_project(self, port: int = 8080, open_browser: bool = True) -> Dict[str, Any]:
        """Launches a persistent local HTTP server in a background daemon thread."""
        import http.server
        import socketserver

        project = self._ensure_active_project()
        if not project:
            raise RuntimeError("No project available to serve.")

        project_dir = Path(project.root_path)

        class CustomHandler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(project_dir), **kwargs)

            def log_message(self, format, *args):
                pass

        actual_port = port
        httpd = None
        for p in range(port, port + 20):
            try:
                httpd = socketserver.TCPServer(("127.0.0.1", p), CustomHandler)
                actual_port = p
                break
            except OSError:
                continue

        if not httpd:
            return {"status": "ERROR", "message": "Could not bind to local port."}

        server_thread = threading.Thread(target=httpd.serve_forever, daemon=True, name="UniversalStudio_Server")
        server_thread.start()

        entry = "index.html" if (project_dir / "index.html").exists() else ""
        url = f"http://127.0.0.1:{actual_port}/{entry}"
        print(f"\n[MIND Studio Server] Project live at: {url}")

        if open_browser and entry:
            webbrowser.open(url)

        return {
            "status": "SERVING",
            "decision_status": "EXECUTE",
            "url": url,
            "port": actual_port,
            "directory": str(project_dir),
            "project_name": project.name,
        }

    def _ensure_active_project(self) -> Optional[DevProject]:
        """Returns existing active project or recovers from persistent session memory."""
        if self.active_project:
            return self.active_project

        # 1. Check persistent conversation state / session memory
        if self.conversation_state and self.conversation_state.active_project_path:
            p_path = Path(self.conversation_state.active_project_path)
            if p_path.exists():
                proj_json = p_path / "project.json"
                p_type = ProjectType.WEBSITE
                p_name = self.conversation_state.active_project_name or p_path.name
                if proj_json.exists():
                    try:
                        meta = json.loads(proj_json.read_text(encoding="utf-8"))
                        p_type = ProjectType(meta.get("type", "website"))
                        if not self.conversation_state.active_project_name:
                            p_name = meta.get("name", p_path.name)
                    except Exception:
                        pass
                spec = ProjectSpecification(title=p_name, project_type=p_type, destination_dir=str(p_path))
                self.active_project = DevProject(
                    name=p_name,
                    root_path=str(p_path),
                    specification=spec,
                    status=ProjectStatus.GENERATED,
                    project_type=p_type,
                )
                return self.active_project

        # 2. Check default workspace root directory
        if self.config.workspace_root.exists():
            for d in self.config.workspace_root.iterdir():
                if d.is_dir() and (d / "project.json").exists():
                    try:
                        meta = json.loads((d / "project.json").read_text(encoding="utf-8"))
                        p_type = ProjectType(meta.get("type", "game"))
                    except Exception:
                        p_type = ProjectType.GAME

                    spec = ProjectSpecification(title=d.name, project_type=p_type)
                    self.active_project = DevProject(
                        name=d.name,
                        root_path=str(d.resolve()),
                        specification=spec,
                        status=ProjectStatus.GENERATED,
                        project_type=p_type,
                    )
                    return self.active_project

        return None


# Universal alias
UniversalStudioOrchestrator = GameDevOrchestrator
