"""
MIND Universal Development Studio — Natural Language Instruction Parser.
Interprets user requests to extract actions, project destinations, names,
file operations (CRUD), clarification requirements, and confirmation states
without hardcoded paths or values.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any, List

from ..models import ActionType, ProjectType, DecisionStatus
from ..game_workflows.workflow_registry import WorkflowRegistry
from .image_request_parser import parse_image_request, StructuredImageRequest


@dataclass
class UserInstruction:
    """Structured representation of a parsed user command."""
    action: ActionType
    raw_command: str
    decision_status: DecisionStatus = DecisionStatus.READY
    project_type: Optional[ProjectType] = None
    project_name: Optional[str] = None
    destination_dir: Optional[str] = None
    target_path: Optional[str] = None
    new_path: Optional[str] = None
    content: Optional[str] = None
    confirmed: bool = False
    requires_confirmation: bool = False
    clarification_question: Optional[str] = None
    clarification_slot: Optional[str] = None
    explanation: Optional[str] = None
    features: List[str] = field(default_factory=list)
    pages: List[str] = field(default_factory=list)
    entities: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action.value,
            "raw_command": self.raw_command,
            "decision_status": self.decision_status.value,
            "project_type": self.project_type.value if self.project_type else None,
            "project_name": self.project_name,
            "destination_dir": self.destination_dir,
            "target_path": self.target_path,
            "new_path": self.new_path,
            "confirmed": self.confirmed,
            "requires_confirmation": self.requires_confirmation,
            "clarification_question": self.clarification_question,
            "clarification_slot": self.clarification_slot,
            "explanation": self.explanation,
            "features": self.features,
            "pages": self.pages,
            "entities": self.entities,
        }


class InstructionParser:
    """Parses natural-language user commands into structured execution instructions."""

    @classmethod
    def parse(
        cls,
        command: str,
        active_project_path: Optional[str] = None,
        conversation_state: Optional[Any] = None,
    ) -> UserInstruction:
        raw = command.strip()
        cmd_lower = raw.lower()

        # Check explicit confirmation flags
        confirmed = bool(
            re.search(r'\b(confirm|force|--force|-f|yes|approve)\b', cmd_lower)
        )

        # ─── 0. Multi-Turn Context & Clarification Resolution ────────────────
        has_pending_clarification = bool(
            conversation_state is not None
            and getattr(conversation_state, "pending_clarification", None)
        )
        has_pending_design = bool(
            not has_pending_clarification
            and conversation_state is not None
            and getattr(conversation_state, "pending_design_approval", None)
        )

        # If a design proposal is currently awaiting approval (and not mid-clarification),
        # check explicit approval, rejection/cancellation, or natural-language design revision.
        if has_pending_design and (
            any(p in cmd_lower for p in [
                "approve design", "approve plan", "confirm design", "proceed with implementation",
                "design looks good", "lgtm", "looks good to build"
            ]) or cmd_lower in ["approve", "approved", "proceed"]
        ):
            return UserInstruction(
                action=ActionType.APPROVE_DESIGN,
                raw_command=raw,
                decision_status=DecisionStatus.READY,
                explanation="User explicitly approved the proposed design.",
            )

        if cmd_lower in [
            "cancel", "abort", "cancel operation", "cancel pending design", "stop",
            "reject", "reject design", "reject plan",
        ]:
            return UserInstruction(
                action=ActionType.CANCEL,
                raw_command=raw,
                decision_status=DecisionStatus.READY,
                explanation="User rejected or cancelled the pending design operation.",
                entities={"rejected": "reject" in cmd_lower},
            )

        if cmd_lower.startswith(("revise ", "update design", "change design", "modify design", "revise plan")) or (
            has_pending_design and cls._is_pending_design_revision_request(raw, cmd_lower)
        ):
            return UserInstruction(
                action=ActionType.REVISE_DESIGN,
                raw_command=raw,
                decision_status=DecisionStatus.READY,
                explanation="User requested revision of proposed design.",
            )

        if conversation_state is not None:
            resolved_text, entities = conversation_state.resolve_references(raw)

            # A. If answering an outstanding clarification
            if entities.get("resolves_clarification"):
                slot = entities.get("slot_name")
                answers = entities.get("clarification_answers", {})
                pc = getattr(conversation_state, "pending_clarification", None)
                prev_answers = pc.answers if pc else {}
                merged = {**prev_answers, **answers}

                if slot == "design_discovery_retry":
                    from .design_consultant import StructuredDesignBrief
                    brief_dict = entities.get("design_brief") or merged.get("design_brief")
                    if isinstance(brief_dict, dict):
                        brief = StructuredDesignBrief.from_dict(brief_dict)
                        return UserInstruction(
                            action=ActionType.CREATE_PROJECT,
                            raw_command=brief.title,
                            decision_status=DecisionStatus.READY,
                            project_type=ProjectType.WEBSITE,
                            project_name=brief.title,
                            pages=brief.required_pages_and_screens,
                            features=brief.important_content_sections,
                            explanation=f"Retrying Google Stitch design generation for '{brief.title}'.",
                            entities={
                                **entities,
                                "design_brief": brief.to_dict(),
                                "stitch_project_id": merged.get("stitch_project_id"),
                                "stitch_design_system": merged.get("stitch_design_system"),
                                "stitch_session_dir": merged.get("stitch_session_dir"),
                            },
                        )

                if slot in ("design_discovery_subtype", "design_discovery_details"):
                    from .design_consultant import ConversationalDesignConsultant
                    disc_state = entities.get("discovery_state") or merged
                    next_q = ConversationalDesignConsultant.get_next_clarification(disc_state)
                    if next_q is not None:
                        return UserInstruction(
                            action=ActionType.CREATE_PROJECT,
                            raw_command=disc_state.get("initial_prompt", raw),
                            project_type=ProjectType.WEBSITE,
                            decision_status=DecisionStatus.CLARIFY,
                            clarification_slot=next_q["slot_name"],
                            clarification_question=next_q["question"],
                            explanation=next_q["explanation"],
                            entities={
                                **entities,
                                "clarification_answers": disc_state,
                                "discovery_state": disc_state,
                                "options": next_q.get("options", []),
                                "archetypes": next_q.get("archetypes", []),
                                "stage": next_q.get("stage", "DESIGN_DISCOVERY"),
                                "missing_dimensions": next_q.get("missing_dimensions", []),
                            },
                        )

                    brief = ConversationalDesignConsultant.build_structured_brief(disc_state)
                    if hasattr(conversation_state, "active_design_brief"):
                        conversation_state.active_design_brief = brief.to_dict()
                    return UserInstruction(
                        action=ActionType.CREATE_PROJECT,
                        raw_command=disc_state.get("initial_prompt", raw),
                        decision_status=DecisionStatus.READY,
                        project_type=ProjectType.WEBSITE,
                        project_name=brief.title,
                        pages=brief.required_pages_and_screens,
                        features=brief.important_content_sections,
                        explanation=f"Conversational design discovery complete. Synthesized Structured Design Brief for '{brief.title}'.",
                        entities={
                            **entities,
                            "design_brief": brief.to_dict(),
                            "discovery_state": disc_state,
                        },
                    )

                if slot == "business_type_and_stack":
                    # Check if destination and name were also supplied
                    if "destination" in merged and "project_name" in merged:
                        return UserInstruction(
                            action=ActionType.CREATE_PROJECT,
                            raw_command=raw,
                            decision_status=DecisionStatus.READY,
                            project_type=ProjectType.WEBSITE,
                            project_name=merged["project_name"],
                            destination_dir=merged["destination"],
                            features=[merged.get("business_type", ""), merged.get("stack", "")],
                            explanation="All requirements clarified: domain, stack, destination, and name resolved.",
                            entities=entities,
                        )
                    else:
                        # Business type and stack known; ask for destination & name
                        return UserInstruction(
                            action=ActionType.CREATE_PROJECT,
                            raw_command=raw,
                            decision_status=DecisionStatus.CLARIFY,
                            clarification_slot="destination_and_name",
                            clarification_question="Where would you like to save the project (e.g., D:\\CoffeeShop), and what should we name it?",
                            features=[merged.get("business_type", ""), merged.get("stack", "")],
                            explanation="Clarified business type and stack; requesting destination and project name.",
                            entities=entities,
                        )

                elif slot == "destination_and_name":
                    dest = merged.get("destination")
                    name = merged.get("project_name") or (Path(dest).name if dest else "CoffeeShop")
                    b_type = merged.get("business_type", "boutique coffee shop")
                    stack = merged.get("stack", "frontend")
                    return UserInstruction(
                        action=ActionType.CREATE_PROJECT,
                        raw_command=raw,
                        decision_status=DecisionStatus.READY,
                        project_type=ProjectType.WEBSITE,
                        project_name=name,
                        destination_dir=dest,
                        features=[b_type, stack],
                        explanation="All requirements clarified: project ready to create.",
                        entities=entities,
                    )

            # B. If ambiguous reference across multiple projects
            if entities.get("ambiguous"):
                return UserInstruction(
                    action=ActionType.UNKNOWN,
                    raw_command=raw,
                    decision_status=DecisionStatus.CLARIFY,
                    clarification_slot="ambiguous_project",
                    clarification_question=entities.get("question"),
                    explanation="Ambiguous reference across multiple projects requires user clarification.",
                    entities=entities,
                )

            # C. If user requests undo/rollback
            if entities.get("action") == "UNDO":
                return UserInstruction(
                    action=ActionType.UNKNOWN,
                    raw_command=raw,
                    decision_status=DecisionStatus.CONFIRM,
                    explanation=entities.get("message"),
                    entities=entities,
                )

            # D. If resolved to styling update ("Change it to blue")
            if entities.get("action") == "UPDATE_STYLE":
                target_p = entities.get("workspace") or active_project_path
                return UserInstruction(
                    action=ActionType.UPDATE_FILE,
                    raw_command=raw,
                    target_path="style.css",
                    destination_dir=target_p,
                    decision_status=DecisionStatus.READY,
                    content=entities.get("color"),
                    explanation=f"Resolved 'it' to style.css in active project for theme color '{entities.get('color')}'.",
                    entities=entities,
                )

            # E. If resolved to adding a page ("Add an online reservation page to it")
            if entities.get("action") == "ADD_PAGE":
                target_p = entities.get("workspace") or active_project_path
                target_f = entities.get("target_page", "reservation.html")
                return UserInstruction(
                    action=ActionType.ADD_PAGE,
                    raw_command=raw,
                    target_path=target_f,
                    destination_dir=target_p,
                    decision_status=DecisionStatus.READY,
                    explanation=f"Resolved 'it' to active project for adding page '{target_f}'.",
                    entities=entities,
                )

            # F. If resolved to fixing an issue ("Fix the error you found earlier", "Fix the reservation form validation")
            if entities.get("action") == "FIX":
                target_p = entities.get("workspace") or active_project_path
                return UserInstruction(
                    action=ActionType.UPDATE_FILE,
                    raw_command=raw,
                    target_path=entities.get("target") or "index.html",
                    destination_dir=target_p,
                    decision_status=DecisionStatus.READY,
                    explanation="Resolved reference to identified issue for repair.",
                    entities=entities,
                )

        # ─── 0.48 Check 3D Asset Reconstruction (AI Image-to-3D) ──────────────
        # Example: "MIND, create a low-poly frost dragon for my fantasy survival game."
        if cls._is_3d_reconstruction_request(raw, cmd_lower):
            return cls._parse_3d_reconstruction_instruction(raw, cmd_lower, active_project_path)

        # ─── 0.5 Check Compound Concurrent Workflow ──────────────────────────
        # Example: "Build a fantasy game landing page and generate matching artwork at the same time."
        if cls._is_compound_workflow(raw, cmd_lower):
            return cls._parse_compound_workflow(raw, cmd_lower, active_project_path)

        # ─── 0.6 Check Standalone Image Generation ───────────────────────────
        # Example: "Generate a detailed cybernetic dragon and save it to E:\AI images using the filename Dragon."
        if cls._is_image_generation_request(raw, cmd_lower):
            return cls._parse_image_instruction(raw, cmd_lower, active_project_path)

        # ─── 0.7 Check Design Approval Action ────────────────────────────────
        if any(p in cmd_lower for p in [
            "approve design", "approve plan", "confirm design", "proceed with implementation",
            "design looks good", "lgtm", "looks good to build"
        ]) or cmd_lower in ["approve", "approved", "proceed"]:
            return UserInstruction(
                action=ActionType.APPROVE_DESIGN,
                raw_command=raw,
                decision_status=DecisionStatus.READY,
                explanation="User explicitly approved the proposed design.",
            )

        # ─── 0.8 Check Cancel Action ─────────────────────────────────────────
        if cmd_lower in ["cancel", "abort", "cancel operation", "cancel pending design", "stop"]:
            return UserInstruction(
                action=ActionType.CANCEL,
                raw_command=raw,
                decision_status=DecisionStatus.READY,
                explanation="User requested cancellation of pending operation.",
            )

        # ─── 0.9 Check Design Revision Action ────────────────────────────────
        if cmd_lower.startswith(("revise ", "update design", "change design", "modify design", "revise plan")):
            return UserInstruction(
                action=ActionType.REVISE_DESIGN,
                raw_command=raw,
                decision_status=DecisionStatus.READY,
                explanation="User requested revision of proposed design architecture.",
            )

        # ─── 1. Check Delete Action ──────────────────────────────────────────
        if re.search(r'\b(delete|remove|unlink|drop|erase)\b', cmd_lower):
            target = cls._extract_delete_target(raw, cmd_lower)
            return UserInstruction(
                action=ActionType.DELETE_PATH,
                raw_command=raw,
                target_path=target,
                destination_dir=active_project_path,
                confirmed=confirmed,
                requires_confirmation=not confirmed,
                decision_status=DecisionStatus.EXECUTE if confirmed else DecisionStatus.CONFIRM,
            )

        # ─── 2. Check Rename Action ──────────────────────────────────────────
        if re.search(r'\brename\b', cmd_lower):
            old_p, new_p = cls._extract_rename_targets(raw)
            return UserInstruction(
                action=ActionType.RENAME_PATH,
                raw_command=raw,
                target_path=old_p,
                new_path=new_p,
                destination_dir=active_project_path,
                confirmed=confirmed,
                decision_status=DecisionStatus.READY,
            )

        # ─── 3. Check Move Action ────────────────────────────────────────────
        if re.search(r'\b(move|relocate)\b', cmd_lower):
            src_p, dst_p = cls._extract_move_targets(raw)
            return UserInstruction(
                action=ActionType.MOVE_PATH,
                raw_command=raw,
                target_path=src_p,
                new_path=dst_p,
                destination_dir=active_project_path,
                confirmed=confirmed,
                decision_status=DecisionStatus.READY,
            )

        # ─── 4. Check List Files Action ──────────────────────────────────────
        if any(p in cmd_lower for p in [
            "list files", "list the files", "show files", "show all files",
            "dir in", "ls in", "list directory", "what files"
        ]) or cmd_lower in ["ls", "dir", "list"]:
            dest = cls._extract_explicit_destination(raw) or active_project_path
            return UserInstruction(
                action=ActionType.LIST_FILES,
                raw_command=raw,
                destination_dir=dest,
                decision_status=DecisionStatus.READY,
            )

        # ─── 5. Check Read File Action ───────────────────────────────────────
        if any(p in cmd_lower for p in ["read the ", "read file ", "read ", "view file ", "inspect file ", "show content of "]):
            target = cls._extract_read_target(raw, cmd_lower)
            if target:
                return UserInstruction(
                    action=ActionType.READ_FILE,
                    raw_command=raw,
                    target_path=target,
                    destination_dir=active_project_path,
                    decision_status=DecisionStatus.READY,
                )

        # ─── 6. Check Add Page / Module Action ───────────────────────────────
        if re.search(r'\badd\s+(a\s+|an\s+)?([a-z0-9_\-\s]+?)\s+(page|module|view|component|screen)\b', cmd_lower):
            target_page = cls._extract_add_page_target(raw, cmd_lower)
            return UserInstruction(
                action=ActionType.ADD_PAGE,
                raw_command=raw,
                target_path=target_page,
                destination_dir=active_project_path,
                decision_status=DecisionStatus.READY,
            )

        # ─── 7. Check Update File Action & CSS Improvement ───────────────────
        is_css_improve = bool(
            re.search(r'\b(improve|enhance|refactor|polish|upgrade|fix)\s+(the\s+)?(css|styling|styles|stylesheet|theme|design)\b', cmd_lower)
        )
        if is_css_improve or re.search(r'\b(update|modify|edit|change)\s+(the\s+)?([a-z0-9_\-\./\\]+)', cmd_lower):
            target = "style.css" if is_css_improve else cls._extract_update_target(raw, cmd_lower)
            if target and (is_css_improve or not any(k in cmd_lower for k in ["create", "build", "generate"])):
                return UserInstruction(
                    action=ActionType.UPDATE_FILE,
                    raw_command=raw,
                    target_path=target,
                    destination_dir=active_project_path,
                    decision_status=DecisionStatus.READY,
                    content="improve_css" if is_css_improve else None,
                    explanation="Improve CSS styling while preserving functionality" if is_css_improve else None,
                )

        # ─── 8. Check Serve / Run Action ─────────────────────────────────────
        if any(cmd_lower.startswith(w) for w in ["serve", "play", "run", "launch browser", "start server"]):
            dest = cls._extract_explicit_destination(raw) or active_project_path
            return UserInstruction(
                action=ActionType.SERVE_PROJECT,
                raw_command=raw,
                destination_dir=dest,
                decision_status=DecisionStatus.READY,
            )

        # ─── 9. Check Verify / Test Action ───────────────────────────────────
        if cmd_lower in ["test", "verify", "check", "inspect", "run tests"]:
            dest = cls._extract_explicit_destination(raw) or active_project_path
            return UserInstruction(
                action=ActionType.VERIFY_PROJECT,
                raw_command=raw,
                destination_dir=dest,
                decision_status=DecisionStatus.READY,
            )

        # ─── 10. Check Vague Request Eliciting Clarification ─────────────────
        dest = cls._extract_explicit_destination(raw)
        name = cls._extract_explicit_name(raw)

        # Intelligently combine destination and project name
        if dest and name:
            try:
                dest_p = Path(dest)
                # If destination is a drive root (e.g. D:\), parent dir, or ends with separator
                if len(dest_p.parts) <= 1 or dest_p == dest_p.parent or dest.endswith(("\\", "/")):
                    dest = str(dest_p / name)
                elif dest_p.name.lower() != name.lower():
                    dest = str(dest_p / name)
            except Exception:
                pass
        elif dest and not name:
            try:
                dest_p = Path(dest)
                if dest_p.name and len(dest_p.parts) > 1:
                    name = dest_p.name
            except Exception:
                pass

        if not dest and cls._is_vague_project_request(raw, cmd_lower):
            return UserInstruction(
                action=ActionType.CREATE_PROJECT,
                raw_command=raw,
                decision_status=DecisionStatus.CLARIFY,
                clarification_slot="business_type_and_stack",
                clarification_question="What kind of business is it, and do you want a frontend-only website or a website with a backend?",
                explanation="Underspecified project request requires clarification before creating files.",
            )

        # ─── 11. Multi-Page Extraction & Default Create Project ──────────────
        pages = cls._extract_connected_pages(raw, cmd_lower)

        p_type = WorkflowRegistry.infer_project_type(raw)

        return UserInstruction(
            action=ActionType.CREATE_PROJECT,
            raw_command=raw,
            project_type=p_type,
            project_name=name,
            destination_dir=dest,
            confirmed=confirmed,
            decision_status=DecisionStatus.READY,
            pages=pages,
        )

    # =========================================================================
    # EXTRACTION & AMBIGUITY HELPERS
    # =========================================================================

    @classmethod
    def _is_pending_design_revision_request(cls, raw: str, cmd_lower: str) -> bool:
        """
        Determines whether a natural-language chat message sent while a design is
        awaiting approval is a request to modify/revise that design rather than a
        filesystem command or a brand-new project creation request.
        """
        # Never treat destructive or inspection filesystem commands as design revisions
        if re.search(r"\b(delete|remove|unlink|drop|erase|rename|move|relocate)\b", cmd_lower):
            return False
        if any(p in cmd_lower for p in ["list files", "show files", "read file", "inspect file"]) or cmd_lower in ["ls", "dir", "list", "test", "verify"]:
            return False
        # Never treat a brand-new project creation command with a new destination or explicit create/build/design verb as a revision
        if re.match(r"^(create|build|generate|develop|design\s+(?:a|an|the))\b", cmd_lower):
            return False
        if cls._extract_explicit_destination(raw):
            return False

        revision_triggers = (
            "revise", "change", "make", "update", "modify", "adjust", "switch",
            "use ", "set ", "replace", "redesign", "improve", "enhance", "polish",
            "add a ", "add an ", "add the ", "add more", "add section", "add hero",
            "add pricing", "add footer", "add header", "add nav", "darker", "lighter",
            "color", "theme", "palette", "font", "layout", "header", "hero", "button",
            "background", "sidebar", "navbar", "footer", "section",
        )
        return any(t in cmd_lower for t in revision_triggers)

    @classmethod
    def _is_vague_project_request(cls, raw: str, cmd_lower: str) -> bool:
        """Determines if a creation request lacks material architectural definition."""
        vague_patterns = [
            r"\bcreate\s+(a\s+)?website\s+for\s+my\s+business\b",
            r"\bbuild\s+(a\s+)?website\s+for\s+my\s+business\b",
            r"\bmake\s+(a\s+)?website\s+for\s+my\s+business\b",
            r"^create\s+(a\s+)?website[\.!\s]*$",
            r"^build\s+(a\s+)?website[\.!\s]*$",
            r"^make\s+(a\s+)?website[\.!\s]*$",
            r"^create\s+(an?\s+)?app\s+for\s+me[\.!\s]*$",
            r"^build\s+(an?\s+)?app\s+for\s+me[\.!\s]*$",
        ]
        for pat in vague_patterns:
            if re.search(pat, cmd_lower):
                return True
        return False

    @classmethod
    def _extract_connected_pages(cls, raw: str, cmd_lower: str) -> List[str]:
        """Extracts requested multi-page views (e.g. 'with a menu and reservation page')."""
        pages = ["index.html"]
        if "menu" in cmd_lower:
            pages.append("menu.html")
        if "reservation" in cmd_lower or "booking" in cmd_lower:
            pages.append("reservation.html")
        if "about" in cmd_lower:
            pages.append("about.html")
        if "contact" in cmd_lower:
            pages.append("contact.html")
        if "services" in cmd_lower:
            pages.append("services.html")
        return list(dict.fromkeys(pages))

    @classmethod
    def _extract_explicit_destination(cls, text: str) -> Optional[str]:
        """Extracts absolute, user-designated, drive-relative, or system destination paths."""
        # 1. Windows drive paths with backslashes or forward slashes (e.g. D:\Projects\App or D:/Web)
        m_win = re.search(r'\b([A-Za-z]:\\[A-Za-z0-9_\-\.\\]+|[A-Za-z]:/[A-Za-z0-9_\-\./]+)', text)
        if m_win:
            return m_win.group(1).rstrip('.,;:')

        # 2. Drive references (e.g., 'in D drive', 'on D drive', 'save it in D drive', 'to D: drive', 'in D:\')
        m_drive = re.search(
            r'\b(?:save\s+(?:the\s+|this\s+|it\s+)?(?:project\s+)?(?:to|in|on|at|under)|in|on|to|at|under)\s+(?:the\s+)?([A-Za-z])(?::\\|:/|:|\s+(?:drive|disk))\b',
            text,
            re.IGNORECASE
        )
        if m_drive:
            drive_letter = m_drive.group(1).upper()
            return f"{drive_letter}:\\"

        # Standalone drive reference (e.g., 'D drive', 'D disk')
        m_standalone_drive = re.search(r'\b([A-Za-z])\s+(?:drive|disk)\b', text, re.IGNORECASE)
        if m_standalone_drive:
            drive_letter = m_standalone_drive.group(1).upper()
            return f"{drive_letter}:\\"

        # 3. Explicit quoted destination paths (e.g., save to "D:\Projects\Site", in 'D:/MyWeb')
        m_quoted = re.search(
            r'(?:save\s+(?:the\s+|this\s+|it\s+)?(?:project\s+)?(?:to|in|on|at|under|inside)|to|in|on|at|under|inside)\s+["\']([^"\']+)["\']',
            text,
            re.IGNORECASE
        )
        if m_quoted:
            cand = m_quoted.group(1).strip()
            # Verify candidate resembles a path or directory, not just a bare project name
            if any(sep in cand for sep in ["\\", "/", ":", "."]) or cand.lower().startswith((".", "~")):
                return cand

        # 4. Special user directory aliases
        m_docs = re.search(r'\b(?:in|to|on)\s+(?:my\s+)?documents(?:\s+folder)?\b', text, re.IGNORECASE)
        if m_docs:
            docs_dir = Path.home() / "Documents"
            name_cand = cls._extract_explicit_name(text)
            if name_cand:
                return str(docs_dir / name_cand)
            return str(docs_dir)

        m_desk = re.search(r'\b(?:in|to|on)\s+(?:my\s+)?desktop(?:\s+folder)?\b', text, re.IGNORECASE)
        if m_desk:
            desk_dir = Path.home() / "Desktop"
            name_cand = cls._extract_explicit_name(text)
            if name_cand:
                return str(desk_dir / name_cand)
            return str(desk_dir)

        # 5. Phrased destinations without quotes
        m_phrase = re.search(r'save\s+(?:the\s+|this\s+|it\s+)?(?:project\s+)?(?:to|in|on|at)\s+([A-Za-z0-9_\-\.\/\\]+)', text, re.IGNORECASE)
        if m_phrase:
            p = m_phrase.group(1).rstrip('.,;:')
            if p.lower() not in ["the", "a", "an", "disk", "folder", "drive"]:
                return p

        # 6. Prepositional path markers (e.g., 'in /var/www and')
        m_in = re.search(r'\b(?:in|at|to)\s+([A-Za-z0-9_\-\.\/\\]+)(?:\s+and\b|$)', text, re.IGNORECASE)
        if m_in:
            candidate = m_in.group(1).rstrip('.,;:')
            if candidate.lower() not in [
                "python", "javascript", "react", "html", "css", "vue", "dark",
                "light", "minutes", "seconds", "english", "space", "3d", "fastapi"
            ] and ("\\" in candidate or "/" in candidate or ":" in candidate):
                return candidate

        return None

    @classmethod
    def _extract_explicit_name(cls, text: str) -> Optional[str]:
        """Extracts explicit user-defined project names, supporting quoted strings with spaces."""
        # 1. Quoted names (allows spaces, punctuation, e.g. "Sports website", "My Online Bank")
        m_quoted = re.search(
            r'\b(?:with\s+the\s+name\s+(?:of\s+)?|with\s+name\s+(?:of\s+)?|(?:and\s+)?(?:name|call)\s+it\s+|(?:named|called|title|titled)\s+|(?:project|app|site)\s+name\s*(?:is|:|=)?\s*)["\']([^"\']+)["\']',
            text,
            re.IGNORECASE
        )
        if m_quoted:
            cand = m_quoted.group(1).strip()
            if cand and cand.lower() not in ["the", "a", "an", "project", "website", "app"]:
                return cand

        # Catch: name (of) "..."
        m_name_of = re.search(r'\bname\s+(?:of\s+)?["\']([^"\']+)["\']', text, re.IGNORECASE)
        if m_name_of:
            cand = m_name_of.group(1).strip()
            if cand and cand.lower() not in ["the", "a", "an", "project", "website", "app"]:
                return cand

        # 2. Unquoted names (single alphanumeric / snake-case words)
        m_unquoted = re.search(
            r'\b(?:with\s+the\s+name\s+(?:of\s+)?|with\s+name\s+(?:of\s+)?|(?:and\s+)?(?:name|call)\s+it\s+|(?:named|called)\s+)([A-Za-z0-9_\-]+)',
            text,
            re.IGNORECASE
        )
        if m_unquoted:
            cand = m_unquoted.group(1).strip()
            if cand.lower() not in ["the", "a", "an", "it", "project", "website", "app", "of", "and", "in", "to", "on"]:
                return cand

        return None

    @classmethod
    def _extract_delete_target(cls, raw: str, cmd_lower: str) -> str:
        """Extracts the file or directory target for deletion."""
        if "temporary" in cmd_lower or "temp file" in cmd_lower or "temp.txt" in cmd_lower:
            return "temp.txt"

        m = re.search(r'\b(?:delete|remove|unlink|drop|erase)\s+(?:the\s+)?(?:file\s+|folder\s+|directory\s+)?["\']?([A-Za-z0-9_\-\./\\]+)["\']?', raw, re.IGNORECASE)
        if m:
            target = m.group(1).rstrip('.,;:')
            if target.lower() not in ["temporary", "temp", "it", "this", "file", "folder", "directory"]:
                return target

        return raw.split()[-1].rstrip('.,;:')

    @classmethod
    def _extract_rename_targets(cls, text: str) -> tuple[str, str]:
        """Extracts old_path and new_path for rename operations."""
        m = re.search(r'\brename\s+(?:the\s+)?(?:file\s+|folder\s+)?["\']?([A-Za-z0-9_\-\./\\]+)["\']?\s+to\s+["\']?([A-Za-z0-9_\-\./\\]+)["\']?', text, re.IGNORECASE)
        if m:
            return m.group(1).rstrip('.,;:'), m.group(2).rstrip('.,;:')
        return "file.txt", "file_renamed.txt"

    @classmethod
    def _extract_move_targets(cls, text: str) -> tuple[str, str]:
        """Extracts src_path and dst_path for move operations."""
        m = re.search(r'\bmove\s+(?:the\s+)?(?:file\s+|folder\s+|directory\s+)?["\']?([A-Za-z0-9_\-\./\\]+)["\']?\s+(?:into|to|in)\s+(?:the\s+)?["\']?([A-Za-z0-9_\-\./\\]+)["\']?', text, re.IGNORECASE)
        if m:
            return m.group(1).rstrip('.,;:'), m.group(2).rstrip('.,;:')
        return "assets", "public/assets"

    @classmethod
    def _extract_read_target(cls, text: str, cmd_lower: str) -> str:
        """Extracts filename target to read."""
        if "auth" in cmd_lower or "login" in cmd_lower:
            return "js/app.js"
        if "css" in cmd_lower or "style" in cmd_lower:
            return "style.css"
        if "html" in cmd_lower or "index" in cmd_lower:
            return "index.html"

        m = re.search(r'\b(?:read|view|inspect|show\s+content\s+of)\s+(?:the\s+)?(?:file\s+)?["\']?([A-Za-z0-9_\-\./\\]+)["\']?', text, re.IGNORECASE)
        if m:
            target = m.group(1).rstrip('.,;:')
            if target.lower() not in ["and", "to", "this", "file", "module"]:
                return target

        return "index.html"

    @classmethod
    def _extract_update_target(cls, text: str, cmd_lower: str) -> str:
        """Extracts filename target to update."""
        if "css" in cmd_lower or "style" in cmd_lower:
            return "style.css"
        if "js" in cmd_lower or "script" in cmd_lower or "javascript" in cmd_lower:
            return "js/app.js"
        if "html" in cmd_lower or "index" in cmd_lower:
            return "index.html"

        m = re.search(r'\b(?:update|modify|edit|change)\s+(?:the\s+)?["\']?([A-Za-z0-9_\-\./\\]+)["\']?', text, re.IGNORECASE)
        if m:
            return m.group(1).rstrip('.,;:')

        return "style.css"

    @classmethod
    def _extract_add_page_target(cls, text: str, cmd_lower: str) -> str:
        """Extracts page name for add_page operations."""
        m = re.search(r'\badd\s+(?:a\s+|an\s+)?(?:online\s+|new\s+|another\s+)?([a-z0-9_\-]+)\s+page\b', cmd_lower)
        if m:
            page_name = m.group(1).strip()
            return f"{page_name}.html"
        return "contact.html"

    # =========================================================================
    # IMAGE & COMPOUND WORKFLOW RECOGNITION
    # =========================================================================

    @classmethod
    def _is_compound_workflow(cls, raw: str, cmd_lower: str) -> bool:
        """Detects requests that combine website generation and image generation."""
        has_web = bool(re.search(r'\b(website|landing page|webpage|web page|portfolio|web app|web site|site)\b', cmd_lower))
        has_img = bool(re.search(r'\b(image|artwork|illustration|concept art|picture|avatar|photo|hero illustration)\b', cmd_lower))
        has_concurrent_cue = bool(re.search(
            r'\b(at the same time|concurrently|simultaneously|matching\s+(artwork|illustration|image|concept art)|and generate|and create (an?\s+)?image|while generating)\b',
            cmd_lower
        ))
        return has_web and has_img and has_concurrent_cue

    @classmethod
    def _parse_compound_workflow(
        cls,
        raw: str,
        cmd_lower: str,
        active_project_path: Optional[str] = None
    ) -> UserInstruction:
        """Parses a compound command into distinct website and image tasks."""
        # Find transition between website and image instructions.
        # Prefer an explicit conjunction ("... and generate ..."); otherwise use the
        # second creation verb in the sentence (the first one belongs to the website).
        m_img = re.search(r'\b(?:and|while|also)\s+(?:also\s+)?(?:generate|create|draw|synthesize|make|render)\b', raw, re.IGNORECASE)
        if not m_img:
            verbs = list(re.finditer(r'\b(?:generate|create|draw|synthesize|make|render)\b', raw, re.IGNORECASE))
            m_img = verbs[1] if len(verbs) > 1 else None

        if m_img:
            web_clause = raw[:m_img.start()].strip().rstrip(',;')
            img_clause = raw[m_img.start():].strip()
        else:
            web_clause = raw
            img_clause = raw

        # The visual description ends where storage instructions begin (". Save ...").
        # Storage instructions are parsed separately from the full sentence below so
        # that filesystem wording never leaks into the diffusion prompt.
        img_visual_clause = re.split(r'(?:\.\s*|,\s*|\s+and\s+)(?:please\s+)?(?:save|store|put|export)\b', img_clause, maxsplit=1, flags=re.IGNORECASE)[0]
        img_req = parse_image_request(img_visual_clause)

        # Generic or "matching" requests inherit the website's subject for visual coherence.
        web_subject = re.sub(
            r'^(?:please\s+)?(?:build|create|make|generate|design|develop)\s+(?:me\s+)?(?:an?\s+|the\s+)?',
            '', web_clause, flags=re.IGNORECASE
        ).strip().rstrip('.')
        generic = re.fullmatch(r'(?:matching\s+)?(?:artwork|image|illustration|concept art|picture|art)s?', img_req.image_prompt.strip(), re.IGNORECASE)
        if generic or re.search(r'\bmatching\b', img_visual_clause, re.IGNORECASE):
            base = "Concept artwork" if generic else img_req.image_prompt
            base = re.sub(r'^matching\s+', '', base, flags=re.IGNORECASE)
            base = base[0].upper() + base[1:] if base else "Concept artwork"
            if web_subject:
                img_req.image_prompt = f"{base} matching the theme of {web_subject}"

        # In case storage instructions for the image appear at the end of the full sentence:
        # e.g. "Save the website to ... and the image to E:\AI images as MIND_Hero"
        if not img_req.destination_path or not img_req.filename:
            full_img_req = parse_image_request(raw)
            if full_img_req.destination_path and not img_req.destination_path:
                img_req.destination_path = full_img_req.destination_path
            if full_img_req.filename and not img_req.filename:
                img_req.filename = full_img_req.filename

        # Parse website side
        web_dest = cls._extract_explicit_destination(web_clause)
        # Check if website destination was specified in combined storage instruction
        m_web_dest = re.search(
            r'(?:save\s+(?:the\s+)?website\s+to\s+)([A-Za-z]:\\[^"\'<>|\n\r]+|[A-Za-z]:/[^"\'<>|\n\r]+|"[^"]+"|\'[^\']+\')',
            raw,
            re.IGNORECASE
        )
        if m_web_dest:
            cand = m_web_dest.group(1).strip('"\'').rstrip('.,;:')
            if not cand.lower().startswith("the selected"):
                web_dest = cand

        web_name = cls._extract_explicit_name(web_clause)
        if not web_name:
            if "mind" in web_clause.lower():
                web_name = "MIND Landing Website"
            elif "fantasy" in web_clause.lower():
                web_name = "Fantasy Game Portal"
            else:
                web_name = "Dynamic Web Platform"

        return UserInstruction(
            action=ActionType.COMPOUND_WORKFLOW,
            raw_command=raw,
            project_type=ProjectType.WEBSITE,
            project_name=web_name,
            destination_dir=web_dest or active_project_path,
            decision_status=DecisionStatus.READY,
            explanation=f"Compound concurrent workflow: Website '{web_name}' + Image '{img_req.image_prompt}'",
            entities={
                "is_compound": True,
                "web_spec": {
                    "title": web_name,
                    "prompt": web_clause,
                    "destination": web_dest,
                    "theme": "modern responsive",
                },
                "image_spec": {
                    "prompt": img_req.image_prompt,
                    "destination": img_req.destination_path,
                    "filename": img_req.filename,
                    "width": 512,
                    "height": 512,
                    "style": "stylized modern",
                },
                "image_request": img_req,
            }
        )

    @classmethod
    def _is_image_generation_request(cls, raw: str, cmd_lower: str) -> bool:
        """Determines if the command is exclusively an image/artwork generation request."""
        # Reject commands that are actually websites or code projects
        if re.search(r'\b(website|webpage|web page|web app|portfolio site|full-stack|html|css)\b', cmd_lower):
            return False

        img_patterns = [
            r'^(?:/image\b|image:)',
            r'^(?:generate|create|draw|synthesize|make|render)\s+(?:an?\s+)?(?:detailed\s+|futuristic\s+|stylized\s+|digital\s+|concept\s+)?(?:image|picture|artwork|illustration|concept art|avatar|sketch|photo|drawing|banner)\b',
            r'\bgenerate\s+(?:an?\s+)?(?:detailed\s+)?[a-z0-9_\-\s]+?\s+and\s+save\s+it\s+to\s+[A-Za-z]:',
            r'\bsave\s+(?:the\s+)?(?:image|picture|artwork|file)\s+to\s+[A-Za-z]:',
        ]
        return any(re.search(p, cmd_lower) for p in img_patterns)

    @classmethod
    def _parse_image_instruction(
        cls,
        raw: str,
        cmd_lower: str,
        active_project_path: Optional[str] = None
    ) -> UserInstruction:
        """Parses standalone image generation command with isolated visual prompt and filesystem path."""
        req = parse_image_request(raw)
        return UserInstruction(
            action=ActionType.GENERATE_IMAGE,
            raw_command=raw,
            project_type=ProjectType.IMAGE,
            project_name=req.filename or "concept_image",
            destination_dir=req.destination_path,
            decision_status=DecisionStatus.READY,
            explanation=f"Image generation: '{req.image_prompt}' to '{req.destination_path or 'default workspace'}' as '{req.filename or 'default'}'",
            entities={
                "image_request": req,
                "visual_prompt": req.image_prompt,
                "destination_path": req.destination_path,
                "filename": req.filename,
                "drive_letter": req.drive_letter,
                "folder_name": req.folder_name,
            }
        )

    @classmethod
    def _is_3d_reconstruction_request(cls, raw: str, cmd_lower: str) -> bool:
        """Detects whether a command is requesting a 3D asset/model generation rather than an entire game or website."""
        # Exclusion keywords (web, app, landing page, dashboard, full project)
        if any(w in cmd_lower for w in ["website", "web page", "webpage", "landing page", "dashboard", "fastapi", "html5", "css3", "portfolio", "blog"]):
            return False

        # Explicit 3D pipeline commands
        if any(p in cmd_lower for p in ["image to 3d", "image-to-3d", "reconstruct 3d", "reconstruct a 3d", "3d model of", "3d asset of", "3d asset for", "3d mesh of"]):
            return True

        has_3d_keyword = bool(re.search(r'\b(3d|three-d|3-d|mesh|blender|low-poly|low poly|stylized model|glb|gltf)\b', cmd_lower))
        has_asset_target = bool(re.search(r'\b(dragon|character|creature|monster|boss|hero|warrior|animal|beast|sword|weapon|shield|armor|tree|rock|crystal|golem|robot|vehicle|spaceship|ship|chest|item|asset|prop)\b', cmd_lower))
        has_create_verb = bool(re.search(r'\b(create|generate|make|build|forge|synthesize|reconstruct)\b', cmd_lower))

        if has_3d_keyword and has_asset_target and has_create_verb:
            # If user explicitly asks for "game" but in the context of "for my game" or "game asset"
            if "game" in cmd_lower:
                if re.search(r'\bfor\s+(?:my|the|a)\s+(?:[a-z0-9_\-\s]+\s+)?game\b', cmd_lower) or "game asset" in cmd_lower:
                    return True
                # But if they say "create a 3d game" without asset target, that's CREATE_PROJECT
                if re.search(r'\b(create|build|make)\s+(?:a\s+)?(?:new\s+)?3d\s+game\b', cmd_lower) and not re.search(r'\b(dragon|character|creature|prop|asset|monster|warrior|item)\b', cmd_lower):
                    return False
            return True

        return False

    @classmethod
    def _parse_3d_reconstruction_instruction(
        cls,
        raw: str,
        cmd_lower: str,
        active_project_path: Optional[str] = None
    ) -> UserInstruction:
        """Parses natural-language 3D asset reconstruction command into structured UserInstruction."""
        clean_text = re.sub(r'^(?:mind|hey mind|computer)[,\s:]+', '', raw, flags=re.IGNORECASE).strip()

        dest_match = re.search(r'\b(?:save\s+(?:it\s+)?to|destination|into|output\s+dir(?:ectory)?)\s+([A-Za-z]:[\\/][^\s]+|\/[^\s]+)', clean_text, re.IGNORECASE)
        explicit_dest = dest_match.group(1).rstrip('.,;:"\'') if dest_match else None

        file_match = re.search(r'\b(?:filename|as|named)\s+([A-Za-z0-9_\-]+(?:\.glb)?)', clean_text, re.IGNORECASE)
        explicit_filename = file_match.group(1) if file_match else None
        if explicit_filename and not explicit_filename.lower().endswith(".glb"):
            explicit_filename += ".glb"

        asset_name = "asset_3d"
        for candidate in ["frost_dragon", "dragon", "warrior", "character", "crystal", "sword", "creature", "monster", "robot", "golem", "tree", "chest"]:
            if candidate.replace("_", " ") in cmd_lower or candidate.replace("_", "-") in cmd_lower or candidate in cmd_lower:
                asset_name = candidate
                break

        if "frost dragon" in cmd_lower or "frost-dragon" in cmd_lower or ("frost" in cmd_lower and "dragon" in cmd_lower):
            asset_name = "frost_dragon"

        return UserInstruction(
            action=ActionType.RECONSTRUCT_3D,
            raw_command=raw,
            project_type=ProjectType.GAME,
            project_name=asset_name,
            destination_dir=explicit_dest or active_project_path,
            decision_status=DecisionStatus.READY,
            explanation=f"AI Image-to-3D Reconstruction: '{clean_text}' -> asset '{asset_name}'",
            entities={
                "clean_prompt": clean_text,
                "asset_name": asset_name,
                "filename": explicit_filename or f"{asset_name}.glb",
                "destination_dir": explicit_dest,
                "is_low_poly": "low-poly" in cmd_lower or "low poly" in cmd_lower,
            }
        )

