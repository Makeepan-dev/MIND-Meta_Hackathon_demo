"""
MIND Universal Development Studio — Conversational State and Context Resolution Layer.

Maintains multi-turn context, resolves pronouns (it, that, this, them),
deictic references (the other one, the same project), continuations,
clarification answers, user corrections, active workspace, and recent tool outcomes.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from .session_memory import SessionMemory, SessionRecord
from ..models import ProjectType

logger = logging.getLogger("MIND.GameDev.ConversationState")


@dataclass
class ConversationTurn:
    """Represents a single turn in a conversational dialogue."""
    turn_id: int
    role: str  # 'user' | 'assistant' | 'system'
    raw_text: str
    resolved_text: str = ""
    intent: str = ""
    target: Optional[str] = None
    workspace: Optional[str] = None
    entities: Dict[str, Any] = field(default_factory=dict)
    interrupted: bool = False
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "role": self.role,
            "raw_text": self.raw_text,
            "resolved_text": self.resolved_text,
            "intent": self.intent,
            "target": self.target,
            "workspace": self.workspace,
            "entities": self.entities,
            "interrupted": self.interrupted,
            "timestamp": self.timestamp,
        }


@dataclass
class PendingClarification:
    """Tracks an outstanding clarification question asked by MIND."""
    slot_name: str  # e.g., 'business_type_and_stack', 'destination_and_name', 'ambiguous_project'
    question: str
    original_intent: str
    partial_goal: str
    options: List[str] = field(default_factory=list)
    answers: Dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slot_name": self.slot_name,
            "question": self.question,
            "original_intent": self.original_intent,
            "partial_goal": self.partial_goal,
            "options": self.options,
            "answers": self.answers,
            "timestamp": self.timestamp,
        }


class ConversationState:
    """
    Stateful conversational memory tracking active dialogue state,
    recent entities, references, pending clarifications, and tool verification history.
    Backed by persistent SQLite session memory.
    """

    def __init__(self, session_memory: Optional[SessionMemory] = None) -> None:
        self.memory = session_memory or SessionMemory()
        self.turn_index: int = 0
        self.turns: List[ConversationTurn] = []

        # Active project and context
        self.active_project_path: Optional[str] = None
        self.active_project_name: Optional[str] = None
        self.active_project_domain: Optional[str] = None
        self.current_task: Optional[str] = None
        self.requirements: Dict[str, Any] = {}

        # Last dialogue elements
        self.last_user_request: str = ""
        self.last_user_intent: str = ""
        self.last_mind_action: str = ""
        self.last_result: str = ""
        self.last_finding: Optional[str] = None

        # Outstanding clarification
        self.pending_clarification: Optional[PendingClarification] = None

        # Pending design proposal awaiting explicit user approval
        self.pending_design_approval: Optional[Dict[str, Any]] = None
        # Approved Stitch design available for subsequent user-authorized tasks
        self.approved_stitch_design: Optional[Dict[str, Any]] = None
        # Per-session Stitch design bundles (session_id -> bundle_dict)
        self.design_sessions: Dict[str, Dict[str, Any]] = {}
        # Per-session Conversational Design Discovery state (session_id -> discovery_state)
        self.design_discovery_sessions: Dict[str, Dict[str, Any]] = {}
        # Latest synthesized StructuredDesignBrief
        self.active_design_brief: Optional[Dict[str, Any]] = None

        # Entity tracking & candidate slots for reference resolution
        self.active_references: Dict[str, Any] = {
            "workspaces": [],      # List of mentioned project paths
            "workspace_names": [], # List of project names
            "files": [],           # List of mentioned/modified files
            "targets": [],         # Specific targets (e.g. 'style.css', 'reservation')
            "issues": [],          # Reported problems or traceback errors
            "actions": [],         # Actions taken
            "current_target": None,
            "previous_target": None,
            "previous_workspace": None,
        }

        # Corrections stack
        self.user_corrections: List[Dict[str, Any]] = []

        # Known workspace aliases (name -> list of keywords)
        self.known_workspaces: Dict[str, List[str]] = {}

        # Restore from persistent memory
        self._restore_from_memory()

    def _restore_from_memory(self) -> None:
        """Restores active project session, past turns, and pending clarifications from SQLite."""
        active = self.memory.get_active_project(verify_exists=True)
        if active:
            self.active_project_name = active.project_name
            self.active_project_path = active.project_path
            self.active_project_domain = active.domain
            self.requirements = active.requirements
            if isinstance(active.metadata, dict) and active.metadata.get("approved_stitch_design"):
                self.approved_stitch_design = active.metadata["approved_stitch_design"]
            self._update_workspace(active.project_path, active.project_name)

        # Restore recent turns
        past_turns = self.memory.get_recent_turns(limit=20)
        for t in past_turns:
            self.turns.append(ConversationTurn(
                turn_id=t["turn_id"],
                role=t["role"],
                raw_text=t["raw_text"],
                resolved_text=t["resolved_text"],
                intent=t["intent"],
                target=t["target"],
                workspace=t["workspace"],
                entities=t["entities"],
                timestamp=t["timestamp"],
            ))
            if t["turn_id"] > self.turn_index:
                self.turn_index = t["turn_id"]

        # Restore pending clarification
        pc = self.memory.get_pending_clarification()
        if pc:
            self.pending_clarification = PendingClarification(
                slot_name=pc["slot_name"],
                question=pc["question"],
                original_intent=pc["original_intent"],
                partial_goal=pc["partial_goal"],
                options=pc["options"],
                answers=pc["answers"],
                timestamp=pc["timestamp"],
            )

        # Restore pending design proposal (persisting across turns & UI restarts)
        raw_pending = self.memory.get_pending_design()
        if raw_pending:
            plan_d = raw_pending.get("plan") if isinstance(raw_pending.get("plan"), dict) else {}
            if plan_d.get("provider") == "stitch" and isinstance(plan_d.get("stitch_bundle"), dict):
                sb = plan_d["stitch_bundle"]
                raw_pending.setdefault("provider", "stitch")
                raw_pending.setdefault("stitch_bundle", sb)
                raw_pending.setdefault("project_id", sb.get("project_id", ""))
                raw_pending.setdefault("session_id", sb.get("session_id", ""))
                raw_pending.setdefault("screen_ids", sb.get("screen_ids", []))
                raw_pending.setdefault("preview_file", sb.get("preview_file", ""))
                raw_pending.setdefault("preview_url", sb.get("preview_url"))
                raw_pending.setdefault("version_dir", sb.get("version_dir", ""))
                raw_pending.setdefault("screens", sb.get("screens", []))
                if sb.get("session_id"):
                    self.design_sessions[str(sb["session_id"])] = sb
        self.pending_design_approval = raw_pending

    def set_pending_design(
        self,
        spec: Any,
        plan: Dict[str, Any],
        version: int = 1,
        stitch_bundle: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Sets a pending design proposal awaiting explicit user approval."""
        spec_dict = spec.to_dict() if hasattr(spec, "to_dict") else dict(spec)
        proj_name = getattr(spec, "project_name", None) or spec_dict.get("project_name") or getattr(spec, "title", "project")
        title = getattr(spec, "title", None) or spec_dict.get("title") or "Project"
        plan_copy = dict(plan or {})
        record: Dict[str, Any] = {
            "spec": spec_dict,
            "plan": plan_copy,
            "version": version,
            "status": "awaiting_approval",
            "project_name": proj_name,
            "title": title,
            "timestamp": time.time(),
        }
        if stitch_bundle:
            plan_copy["provider"] = "stitch"
            plan_copy["stitch_bundle"] = stitch_bundle
            record["provider"] = "stitch"
            record["stitch_bundle"] = stitch_bundle
            record["project_id"] = stitch_bundle.get("project_id", "")
            record["session_id"] = stitch_bundle.get("session_id", "")
            record["screen_ids"] = stitch_bundle.get("screen_ids", [])
            record["preview_file"] = stitch_bundle.get("preview_file", "")
            record["preview_url"] = stitch_bundle.get("preview_url")
            record["version_dir"] = stitch_bundle.get("version_dir", "")
            record["screens"] = stitch_bundle.get("screens", [])
            sid = str(stitch_bundle.get("session_id") or proj_name)
            self.design_sessions[sid] = stitch_bundle
        self.pending_design_approval = record
        self.memory.save_pending_design(
            project_name=proj_name,
            title=title,
            spec_dict=spec_dict,
            plan_dict=plan_copy,
            version=version,
            status="awaiting_approval",
        )

    def update_pending_design(
        self,
        plan_updates: Dict[str, Any],
        stitch_bundle: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Applies a revision to the pending design plan and increments design version."""
        if not self.pending_design_approval:
            return 0
        self.pending_design_approval["plan"].update(plan_updates)
        if stitch_bundle:
            new_v = int(stitch_bundle.get("version") or (self.pending_design_approval["version"] + 1))
            self.pending_design_approval["version"] = new_v
            self.pending_design_approval["provider"] = "stitch"
            self.pending_design_approval["stitch_bundle"] = stitch_bundle
            self.pending_design_approval["project_id"] = stitch_bundle.get("project_id", "")
            self.pending_design_approval["session_id"] = stitch_bundle.get("session_id", "")
            self.pending_design_approval["screen_ids"] = stitch_bundle.get("screen_ids", [])
            self.pending_design_approval["preview_file"] = stitch_bundle.get("preview_file", "")
            self.pending_design_approval["preview_url"] = stitch_bundle.get("preview_url")
            self.pending_design_approval["version_dir"] = stitch_bundle.get("version_dir", "")
            self.pending_design_approval["screens"] = stitch_bundle.get("screens", [])
            self.pending_design_approval["plan"]["provider"] = "stitch"
            self.pending_design_approval["plan"]["stitch_bundle"] = stitch_bundle
            sid = str(stitch_bundle.get("session_id") or self.pending_design_approval["project_name"])
            self.design_sessions[sid] = stitch_bundle
        else:
            self.pending_design_approval["version"] += 1
        self.pending_design_approval["timestamp"] = time.time()
        self.memory.save_pending_design(
            project_name=self.pending_design_approval["project_name"],
            title=self.pending_design_approval["title"],
            spec_dict=self.pending_design_approval["spec"],
            plan_dict=self.pending_design_approval["plan"],
            version=self.pending_design_approval["version"],
            status="awaiting_approval",
        )
        return self.pending_design_approval["version"]

    def approve_stitch_design(self) -> Optional[Dict[str, Any]]:
        """Marks the pending Stitch design as approved and retains it without starting implementation."""
        if not self.pending_design_approval:
            return None
        approved = dict(self.pending_design_approval)
        approved["status"] = "approved"
        approved["approved_at"] = time.time()
        if isinstance(approved.get("stitch_bundle"), dict):
            approved["stitch_bundle"]["approval_state"] = "approved"
            sid = str(approved["stitch_bundle"].get("session_id") or approved.get("project_name", "stitch"))
            self.design_sessions[sid] = approved["stitch_bundle"]
        self.approved_stitch_design = approved
        self.pending_design_approval = None
        self.memory.clear_pending_design()
        return approved

    def cancel_pending_design(self) -> Optional[Dict[str, Any]]:
        """Cancels any pending design proposal."""
        prev = self.pending_design_approval
        self.pending_design_approval = None
        self.memory.clear_pending_design()
        return prev

    def clear_pending_design(self) -> None:
        """Clears pending design upon approval and execution."""
        self.pending_design_approval = None
        self.memory.clear_pending_design()

    # ─── Turn & State Management ────────────────────────────────────────────

    def set_active_project(
        self,
        name: str,
        path: Union[Path, str],
        domain: str = "website",
        requirements: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Sets and persists the active project context."""
        p_str = str(Path(path).resolve())
        self.active_project_name = name
        self.active_project_path = p_str
        self.active_project_domain = domain
        if requirements:
            self.requirements.update(requirements)

        self._update_workspace(p_str, name)
        self.memory.save_active_project(
            project_name=name,
            project_path=p_str,
            domain=domain,
            requirements=self.requirements,
            metadata=metadata,
        )

    def add_user_turn(
        self,
        raw_text: str,
        resolved_text: str,
        intent: str,
        entities: Dict[str, Any],
        workspace: Optional[str] = None,
        target: Optional[str] = None,
    ) -> ConversationTurn:
        """Records a user utterance turn, updates state, and persists to SQLite."""
        self.turn_index += 1
        ws = workspace or self.active_project_path
        turn = ConversationTurn(
            turn_id=self.turn_index,
            role="user",
            raw_text=raw_text,
            resolved_text=resolved_text,
            intent=intent,
            target=target,
            workspace=ws,
            entities=entities,
            timestamp=time.time(),
        )
        self.turns.append(turn)
        self.last_user_request = raw_text
        self.last_user_intent = intent

        if ws:
            self._update_workspace(ws)
        if target:
            self._update_target(target)

        self.memory.record_turn(
            turn_id=self.turn_index,
            role="user",
            raw_text=raw_text,
            resolved_text=resolved_text,
            intent=intent,
            target=target,
            workspace=ws,
            entities=entities,
            timestamp=turn.timestamp,
        )
        return turn

    def add_assistant_turn(
        self,
        text: str,
        action: str = "",
        result: str = "",
        interrupted: bool = False,
        finding: Optional[str] = None,
    ) -> ConversationTurn:
        """Records an assistant response turn and updates state."""
        self.turn_index += 1
        turn = ConversationTurn(
            turn_id=self.turn_index,
            role="assistant",
            raw_text=text,
            resolved_text=text,
            intent=action,
            interrupted=interrupted,
            timestamp=time.time(),
        )
        self.turns.append(turn)
        if action:
            self.last_mind_action = action
            self.active_references["actions"].append(action)
        if result:
            self.last_result = result
        if finding:
            self.last_finding = finding
            self.active_references["issues"].append(finding)

        self.memory.record_turn(
            turn_id=self.turn_index,
            role="assistant",
            raw_text=text,
            resolved_text=text,
            intent=action,
            target=self.active_references.get("current_target"),
            workspace=self.active_project_path,
            entities={"finding": finding, "result": result},
            timestamp=turn.timestamp,
        )
        return turn

    def set_pending_clarification(
        self,
        slot_name: str,
        question: str,
        original_intent: str,
        partial_goal: str,
        options: Optional[List[str]] = None,
        answers: Optional[Dict[str, str]] = None,
    ) -> None:
        """Stores a pending clarification request in RAM and SQLite."""
        self.pending_clarification = PendingClarification(
            slot_name=slot_name,
            question=question,
            original_intent=original_intent,
            partial_goal=partial_goal,
            options=options or [],
            answers=answers or {},
            timestamp=time.time(),
        )
        self.memory.save_pending_clarification(
            slot_name=slot_name,
            question=question,
            original_intent=original_intent,
            partial_goal=partial_goal,
            options=options or [],
            answers=answers or {},
        )

    def clear_pending_clarification(self) -> None:
        """Clears outstanding clarification in RAM and SQLite."""
        self.pending_clarification = None
        self.memory.clear_pending_clarification()

    def record_tool_result(
        self,
        action: str,
        status: str,
        target_path: Optional[str] = None,
        output: str = "",
        error: str = "",
        verified: bool = False,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Records tool execution evidence to conversation state and SQLite."""
        if target_path:
            p_name = Path(target_path).name
            if p_name not in self.active_references["files"]:
                self.active_references["files"].insert(0, p_name)
        if error:
            self.last_finding = error
            self.active_references["issues"].append(error)

        self.memory.record_tool_execution(
            action=action,
            target_path=target_path,
            status=status,
            output=output,
            error=error,
            verified=verified,
            data=data,
        )

    def _update_workspace(self, workspace_path: str, name: Optional[str] = None) -> None:
        """Updates the workspace references."""
        p_str = str(Path(workspace_path).resolve()) if workspace_path else ""
        if not p_str:
            return

        if self.active_project_path and self.active_project_path != p_str:
            self.active_references["previous_workspace"] = self.active_project_path

        self.active_project_path = p_str
        ws_list = self.active_references["workspaces"]
        if p_str in ws_list:
            ws_list.remove(p_str)
        ws_list.insert(0, p_str)

        if name:
            self.active_project_name = name
            name_list = self.active_references["workspace_names"]
            if name in name_list:
                name_list.remove(name)
            name_list.insert(0, name)

            clean_name = name.lower().strip()
            if clean_name not in self.known_workspaces:
                self.known_workspaces[clean_name] = [clean_name, clean_name.replace("_", " ")]

    def _update_target(self, target: str) -> None:
        """Updates target reference history."""
        prev = self.active_references.get("current_target")
        if prev and prev != target:
            self.active_references["previous_target"] = prev
        self.active_references["current_target"] = target
        tgt_list = self.active_references["targets"]
        if target in tgt_list:
            tgt_list.remove(target)
        tgt_list.insert(0, target)

    # ─── Contextual Reference Resolution Core ───────────────────────────────

    def resolve_references(self, utterance: str) -> Tuple[str, Dict[str, Any]]:
        """
        Resolves anaphora (it, that, this, them), deictic references (the other one,
        the same project), continuations, corrections, and answers to pending clarifications.

        Returns:
            Tuple of (resolved_utterance, extracted_entities)
        """
        text = utterance.strip()
        lower = text.lower()
        entities: Dict[str, Any] = {}

        # 1. Check for Pending Clarification Answers
        if self.pending_clarification:
            pc = self.pending_clarification

            # Handle one-click Retry after a Stitch timeout
            if pc.slot_name == "design_discovery_retry":
                if any(w in lower for w in ("retry", "try again", "regenerate", "retry stitch generation")):
                    entities["resolves_clarification"] = True
                    entities["slot_name"] = "design_discovery_retry"
                    entities["original_intent"] = pc.original_intent
                    entities["design_brief"] = pc.answers.get("design_brief") if isinstance(pc.answers, dict) else None
                    entities["clarification_answers"] = pc.answers if isinstance(pc.answers, dict) else {}
                    return pc.partial_goal, entities
                else:
                    # User typed a different command; clear the retry slot and parse normally
                    self.clear_pending_clarification()

        if self.pending_clarification:
            pc = self.pending_clarification

            # Handle Conversational Design Discovery slots
            if pc.slot_name in ("design_discovery_subtype", "design_discovery_details"):
                from .design_consultant import ConversationalDesignConsultant
                import json as _json
                disc_state = _json.loads(_json.dumps(pc.answers)) if isinstance(pc.answers, dict) else {}
                # If the user started a brand-new unrelated design session, clear old clarification
                if ConversationalDesignConsultant.is_new_unrelated_design_request(text, disc_state):
                    self.clear_pending_clarification()
                else:
                    entities["resolves_clarification"] = True
                    entities["slot_name"] = pc.slot_name
                    entities["original_intent"] = pc.original_intent
                    raw_turns = list(disc_state.get("raw_turns") or [pc.partial_goal])
                    raw_turns.append(text)
                    disc_state["raw_turns"] = raw_turns
                    ConversationalDesignConsultant.extract_and_merge_requirements(
                        text,
                        disc_state,
                        is_initial_turn=False,
                        expected_slot=pc.slot_name,
                    )
                    sid = str(disc_state.get("session_id") or "disc_session")
                    self.design_discovery_sessions[sid] = disc_state
                    entities["clarification_answers"] = disc_state
                    entities["discovery_state"] = disc_state
                    resolved = f"{pc.partial_goal}. Discovery state: {disc_state.get('subtype_label') or ''}"
                    return resolved, entities

        if self.pending_clarification:
            pc = self.pending_clarification
            entities["resolves_clarification"] = True
            entities["slot_name"] = pc.slot_name
            entities["original_intent"] = pc.original_intent

            # Preserve existing answers and merge new utterance
            answers = dict(pc.answers)
            if pc.slot_name == "business_type_and_stack":
                # Extract business type and stack
                if "coffee" in lower:
                    answers["business_type"] = "boutique coffee shop"
                elif "tech" in lower or "saas" in lower:
                    answers["business_type"] = "tech startup"
                else:
                    answers["business_type"] = text.split(".")[0].strip()

                if "frontend" in lower:
                    answers["stack"] = "frontend"
                elif "backend" in lower or "fullstack" in lower or "full stack" in lower:
                    answers["stack"] = "fullstack"

                # Check if user also provided destination/name in the same sentence
                dest_match = re.search(r"(?:save|destination|to|in)\s+([a-zA-Z]:\\[a-zA-Z0-9_\-\\]+|/[a-zA-Z0-9_\-/]+)", text, re.IGNORECASE)
                if dest_match:
                    answers["destination"] = dest_match.group(1).strip()
                name_match = re.search(r"(?:name|call)\s+(?:it\s+)?([a-zA-Z0-9_\-]+)", text, re.IGNORECASE)
                if name_match:
                    answers["project_name"] = name_match.group(1).strip()

                entities["clarification_answers"] = answers
                resolved = f"{pc.partial_goal}. Details: {answers}"
                return resolved, entities

            if pc.slot_name == "destination_and_name":
                dest_match = re.search(r"(?:save|destination|to|in)\s+([a-zA-Z]:\\[a-zA-Z0-9_\-\\]+|/[a-zA-Z0-9_\-/]+)", text, re.IGNORECASE)
                if dest_match:
                    answers["destination"] = dest_match.group(1).strip()
                elif re.match(r"^[a-zA-Z]:\\[a-zA-Z0-9_\-\\]+", text):
                    answers["destination"] = text.strip()

                name_match = re.search(r"(?:name|call)\s+(?:it\s+)?([a-zA-Z0-9_\-]+)", text, re.IGNORECASE)
                if name_match:
                    answers["project_name"] = name_match.group(1).strip()

                entities["clarification_answers"] = answers
                resolved = f"{pc.partial_goal}. Destination: {answers.get('destination', '')}, Name: {answers.get('project_name', '')}"
                return resolved, entities

            if pc.slot_name in ("ambiguous_project", "workspace", "project"):
                matched_p = self._match_workspace(lower)
                if matched_p:
                    entities["workspace"] = matched_p
                    self._update_workspace(matched_p)
                    resolved = f"{pc.partial_goal} in {matched_p}"
                    return resolved, entities

        # 2. Check for Ambiguous References across multiple projects
        # If user says "open the project" or "fix the project" and there are multiple known projects
        known_ws_count = len(self.active_references["workspaces"])
        if any(w in lower for w in ["open my project", "open the project", "switch project"]) and not self._match_workspace(lower):
            if known_ws_count > 1:
                entities["ambiguous"] = True
                entities["requires_clarification"] = True
                entities["question"] = f"Which project do you mean? (Known: {', '.join(self.active_references['workspace_names'][:3])})"
                return text, entities

        # 3. Check for Undo / Rollback requests ("undo that", "undo that last change", "revert that")
        if re.search(r"\b(undo\s+that(\s+last\s+change)?|revert\s+that(\s+last\s+change)?|go\s+back)\b", lower):
            entities["action"] = "UNDO"
            entities["rollback_available"] = False
            entities["message"] = (
                "Automatic atomic rollback checkpoints are not enabled. "
                "Would you like me to inspect recent file modifications and create a manual repair patch?"
            )
            resolved = f"Request rollback of recent changes in {self.active_project_name or 'project'}"
            return resolved, entities

        # 4. Check for "Fix the error you found earlier" / "Can you fix that?" / "Fix it" / "Fix the reservation form validation"
        if re.search(r"\b(fix|repair|patch|correct)\s+(?:the\s+)?([a-zA-Z0-9_\-\s]+?)\b", lower) and self.active_project_path:
            m_fix = re.search(r"\b(fix|repair|patch|correct)\s+(?:the\s+)?([a-zA-Z0-9_\-\s]+?)\b", lower)
            subject = m_fix.group(2).strip() if m_fix else ""
            target_issue = subject or self.last_finding
            target_file = "reservation.html" if "reservation" in subject else ("style.css" if ("style" in subject or "css" in subject) else "index.html")

            entities["action"] = "FIX"
            entities["workspace"] = self.active_project_path
            entities["target"] = target_file
            resolved = f"Fix identified issue ({subject or target_issue}) in {self.active_project_name or 'project'}: {target_file}"
            return resolved, entities

        # 5. Check for "Change it to blue" / "Make it blue" / "Update style"
        color_match = re.search(r"\b(?:change|make|set|turn)\s+it\s+(?:to\s+)?([a-zA-Z0-9_#\-]+)", lower)
        if color_match and any(c in lower for c in ["blue", "red", "green", "dark", "light", "purple", "orange", "gold", "black", "white", "cyan", "#"]):
            color_val = color_match.group(1).strip()
            entities["action"] = "UPDATE_STYLE"
            entities["color"] = color_val
            entities["target"] = "style.css"
            entities["workspace"] = self.active_project_path
            resolved = f"Update style in {self.active_project_path or 'active project'} (style.css): change theme/color to {color_val}"
            return resolved, entities

        # 6. Check for "Add authentication to that" / "Add auth to it"
        if re.search(r"\badd\s+([a-zA-Z0-9_\-\s]+?)\s+to\s+(?:that|it|the\s+project)\b", lower):
            feature_match = re.search(r"\badd\s+([a-zA-Z0-9_\-\s]+?)\s+to\s+(?:that|it|the\s+project)\b", lower)
            feature_name = feature_match.group(1).strip() if feature_match else "feature"
            entities["action"] = "ADD_FEATURE"
            entities["feature"] = feature_name
            entities["workspace"] = self.active_project_path
            resolved = f"Add feature '{feature_name}' to {self.active_project_name or 'project'}"
            return resolved, entities

        # 7. Check for "Add an online reservation page to it" / "Add a contact page to the same project"
        page_match = re.search(r"\badd\s+(?:an?\s+)?(?:online\s+|new\s+|another\s+)?([a-zA-Z0-9_\-]+)\s+page\s+to\s+(?:it|that|the\s+same\s+project|this)\b", lower)
        if page_match:
            page_name = page_match.group(1).strip()
            page_file = f"{page_name}.html"
            entities["action"] = "ADD_PAGE"
            entities["target_page"] = page_file
            entities["workspace"] = self.active_project_path
            resolved = f"Add new page '{page_file}' to {self.active_project_name or 'project'} at {self.active_project_path}"
            return resolved, entities

        # 8. Check for "Continue the coffee shop project and improve the reservation page"
        continue_match = re.search(r"\bcontinue\s+(?:the\s+)?([a-zA-Z0-9_\-\s]+?)\s+project\b", lower)
        if continue_match:
            p_ref = continue_match.group(1).strip()
            matched_p = self._match_workspace(p_ref)
            if matched_p:
                entities["workspace"] = matched_p
                self._update_workspace(matched_p)
            entities["action"] = "CONTINUE"
            resolved = f"Continue work on {entities.get('workspace') or self.active_project_path}: {text}"
            return resolved, entities

        # 9. General Pronoun Replacement: "it", "that", "the project", "the same project"
        resolved_text = text
        if self.active_project_path:
            p_label = self.active_project_name or Path(self.active_project_path).name
            if re.search(r"\b(it|that|this|the\s+same\s+project|the\s+project)\b", lower):
                # Ensure we provide workspace context
                entities["workspace"] = self.active_project_path
                entities["project_name"] = p_label

        return resolved_text, entities

    def _match_workspace(self, query: str) -> Optional[str]:
        """Matches a search query against active project or known workspace aliases."""
        q = query.lower().strip()
        # Direct check active project
        if self.active_project_name and self.active_project_name.lower() in q:
            return self.active_project_path

        # Check path matches
        for p_str in self.active_references["workspaces"]:
            p = Path(p_str)
            if p.name.lower() in q:
                return p_str

        # Check aliases
        for alias_key, aliases in self.known_workspaces.items():
            if any(a in q for a in aliases):
                for p_str in self.active_references["workspaces"]:
                    if alias_key in Path(p_str).name.lower():
                        return p_str

        return None
