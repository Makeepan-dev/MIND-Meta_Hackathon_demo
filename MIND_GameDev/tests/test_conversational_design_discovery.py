"""
Automated & End-to-End Desktop Validation Suite for:
MIND Hackathon Edition — Conversational Design Discovery and End-to-End Stitch Workflow Validation.

Covers:
1. Conversational Design Discovery on ambiguous requests ("Design a modern school website."):
   - Recognizes missing requirements before calling Stitch.
   - Presents all 6 contextual school options:
     * K–12 academy / private school
     * University / higher education
     * Elementary school
     * Language academy
     * Coding or technical school
     * Other
   - Includes design direction and intended audience for each option.
   - Allows selecting an option or describing a custom ("Other") direction.
2. Adaptive Clarification:
   - Never uses a fixed questionnaire when details are already supplied.
   - Asks only the remaining material questions (primary audience, required pages, visual style, main features, informational website vs. portal) when unanswered.
   - Never repeats questions already answered in earlier turns.
   - Accumulates requirements across multiple turns.
3. Structured Design Brief:
   - Synthesizes all 10 required fields:
     1. Project type
     2. Target audience
     3. Website purpose
     4. Required pages/screens
     5. Navigation structure
     6. Important content sections
     7. Visual direction
     8. Branding requirements
     9. Responsive requirements
     10. Special functionality
   - Displays the structured design brief to the user in the desktop UI.
   - Passes the structured design brief to `StitchAdapter.generate_design` and retains it across `StitchAdapter.revise_design`.
4. Session Isolation:
   - Starting a new unrelated design session isolates requirements and never leaks answers from a previous session.
5. Complete 14-Step End-to-End Desktop Validation:
   - Drives the actual MIND desktop interface (`UnifiedAssistantView` + `DesignPreviewWindow` + `GameDevOrchestrator`) through all 14 required steps, plus live Google Stitch MCP verification.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from MIND_GameDev.adapters.stitch_adapter import StitchAdapter
from MIND_GameDev.config import GameDevConfig
from MIND_GameDev.orchestrator import GameDevOrchestrator
from MIND_GameDev.tools.conversation_state import ConversationState
from MIND_GameDev.tools.design_consultant import (
    ConversationalDesignConsultant,
    SCHOOL_ARCHETYPES,
    StructuredDesignBrief,
)
from MIND_GameDev.tools.session_memory import SessionMemory
from MIND_GameDev.ui.views.chat_view import UnifiedAssistantView, WorkflowArtifactBubble
from MIND_GameDev.ui.widgets.design_preview_window import (
    DesignPreviewWindow,
    STATE_APPROVED,
    STATE_AWAITING,
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _pump(ms: int = 60) -> None:
    end = time.time() + ms / 1000.0
    while time.time() < end:
        QApplication.processEvents()
        time.sleep(0.01)


@pytest.fixture
def view(qapp):
    v = UnifiedAssistantView()
    v.resize(1280, 820)
    v.show()
    sent: List[str] = []
    v.prompt_sent.connect(lambda text, _choice: sent.append(text))
    v._sent = sent
    yield v
    v.shutdown_previews()
    v.close()
    v.deleteLater()
    _pump()


class SchoolStitchMCPTransport:
    """
    Deterministic Stitch MCP JSON-RPC 2.0 transport capturing exact prompts sent
    to `generate_screen_from_text` and `edit_screens` for school website validation.
    """

    def __init__(self) -> None:
        self.requests: List[Dict[str, Any]] = []
        self.generate_prompts: List[str] = []
        self.edit_prompts: List[str] = []

    def __call__(
        self,
        url: str,
        headers: Dict[str, str],
        payload: Dict[str, Any],
        timeout: float,
    ) -> Dict[str, Any]:
        self.requests.append({
            "url": url,
            "headers": dict(headers),
            "payload": json.loads(json.dumps(payload)),
            "timeout": timeout,
        })
        params = payload.get("params") or {}
        tool = params.get("name")
        args = params.get("arguments") or {}
        rpc_id = payload.get("id", 1)

        if tool == "create_project":
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {
                    "structuredContent": {
                        "name": "projects/888111222",
                        "title": args.get("title", "K-12 Academy Design"),
                    }
                },
            }

        if tool == "generate_screen_from_text":
            self.generate_prompts.append(args.get("prompt", ""))
            pid = args.get("projectId", "888111222")
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {
                    "structuredContent": {
                        "outputComponents": [
                            {
                                "design": {
                                    "screens": [
                                        {
                                            "name": f"projects/{pid}/screens/scr_k12_v1",
                                            "title": "K–12 Academy Homepage — V1",
                                            "deviceType": "DESKTOP",
                                            "width": "1440",
                                            "height": "1024",
                                            "htmlCode": {
                                                "name": f"projects/{pid}/files/file_k12_html_v1",
                                                "mimeType": "text/html",
                                            },
                                        }
                                    ]
                                }
                            },
                            {"text": "Generated K–12 Academy website design v1."},
                        ],
                        "projectId": pid,
                        "sessionId": f"stitch_sess_{pid}",
                    }
                },
            }

        if tool == "edit_screens":
            self.edit_prompts.append(args.get("prompt", ""))
            pid = args.get("projectId", "888111222")
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {
                    "structuredContent": {
                        "outputComponents": [
                            {
                                "design": {
                                    "screens": [
                                        {
                                            "name": f"projects/{pid}/screens/scr_k12_v2",
                                            "title": "K–12 Academy Homepage — V2 Revised",
                                            "deviceType": "DESKTOP",
                                            "width": "1440",
                                            "height": "1200",
                                            "htmlCode": {
                                                "name": f"projects/{pid}/files/file_k12_html_v2",
                                                "mimeType": "text/html",
                                            },
                                        }
                                    ]
                                }
                            },
                            {"text": "Updated K–12 Academy website design to v2."},
                        ],
                        "projectId": pid,
                        "sessionId": f"stitch_sess_{pid}",
                    }
                },
            }

        if tool == "download_file":
            fname = args.get("name", "")
            if "file_k12_html_v1" in fname:
                html = (
                    "<!DOCTYPE html><html lang='en'><head><meta charset='UTF-8'>"
                    "<title>Oakridge K-12 Academy — V1</title>"
                    "<style>body { background: #f8fafc; color: #0f172a; }</style></head>"
                    "<body><header><h1>STITCH-K12-ACADEMY-V1-HERO</h1>"
                    "<nav>Home | Admissions | Academics | Campus Life | Parent Portal</nav></header>"
                    "<main><section id='admissions'>Schedule a Campus Tour</section></main></body></html>"
                )
                return {"jsonrpc": "2.0", "id": rpc_id, "result": {"structuredContent": {"html": html}}}
            if "file_k12_html_v2" in fname:
                html = (
                    "<!DOCTYPE html><html lang='en'><head><meta charset='UTF-8'>"
                    "<title>Oakridge K-12 Academy — V2 STEM & Scholarships</title>"
                    "<style>body { background: #0f172a; color: #f8fafc; }</style></head>"
                    "<body><header><h1>STITCH-K12-ACADEMY-V2-STEM-SCHOLARSHIP-SHOWCASE</h1></header>"
                    "<main><section id='stem-lab'>Interactive Robotics & STEM Innovation Lab</section>"
                    "<section id='tuition'>Tuition Calculator & Merit Scholarships</section></main></body></html>"
                )
                return {"jsonrpc": "2.0", "id": rpc_id, "result": {"structuredContent": {"html": html}}}

        return {"jsonrpc": "2.0", "id": rpc_id, "result": {"structuredContent": {}}}


# =============================================================================
# 1. Conversational Design Discovery & School Archetype Options
# =============================================================================

def test_school_request_triggers_discovery_with_all_six_options_and_explanations(tmp_path):
    """
    Verifies that "Design a modern school website." does NOT immediately call Stitch,
    and instead presents the 6 contextual school options with design direction and
    intended audience explanations, plus support for selecting an option or custom direction.
    """
    transport = SchoolStitchMCPTransport()
    stitch_adapter = StitchAdapter(api_key="AQ.TestKey", transport=transport)

    cfg = GameDevConfig.load()
    cfg.test_mode = False
    cfg.require_design_approval = True
    cfg.workspace_root = tmp_path / "ws_discovery"
    cfg.workspace_root.mkdir(parents=True, exist_ok=True)

    mem = SessionMemory(db_path=tmp_path / "disc.db")
    state = ConversationState(mem)
    orch = GameDevOrchestrator(
        config=cfg,
        enable_voice=False,
        session_memory=mem,
        conversation_state=state,
        stitch_adapter=stitch_adapter,
    )

    res = orch.execute_command("Design a modern school website.")
    assert res["status"] == "CLARIFY"
    assert res["discovery_stage"] == "subtype"
    assert len(transport.requests) == 0, "Stitch must NOT be called before discovery completes"

    options = res.get("options") or []
    assert len(options) == 6
    labels = [o["label"].lower() for o in options]
    assert any("k–12" in l or "k-12" in l for l in labels)
    assert any("university" in l for l in labels)
    assert any("elementary" in l for l in labels)
    assert any("language academy" in l for l in labels)
    assert any("coding or technical" in l for l in labels)
    assert any("other" in l for l in labels)

    # Every option must include both design_direction and intended_audience explanations
    for opt in options:
        assert opt.get("design_direction"), f"Missing design_direction on {opt}"
        assert opt.get("intended_audience"), f"Missing intended_audience on {opt}"
        assert opt["design_direction"] in res["question"]
        assert opt["intended_audience"] in res["question"]


def test_custom_other_direction_supported_in_discovery(tmp_path):
    """
    Verifies that the user can describe a custom ('Other') school direction instead
    of picking one of the predefined 5 archetypes, and MIND adapts accordingly.
    """
    consultant = ConversationalDesignConsultant()
    state = consultant.create_initial_state("Design a modern school website.")
    q1 = consultant.get_next_clarification(state)
    assert q1 is not None and q1["slot_name"] == "design_discovery_subtype"

    # User describes a custom school direction ("Montessori music conservatory for gifted teens")
    consultant.extract_and_merge_requirements(
        "Other: It's a residential conservatory and performing arts academy for gifted teen musicians, "
        "targeting auditioning students and parents, with pages for Home, Auditions, Faculty, and Events, "
        "featuring performing arts studio showcases and scholarships, and an informational website with an "
        "audition portal in an elegant dark mode gold classical style.",
        state,
        expected_slot="design_discovery_subtype",
    )
    assert bool(state["subtype_label"]) is True
    assert "residential conservatory" in state["subtype_label"].lower()

    # Since the user also answered audience, pages, style, features, and website_purpose in one turn,
    # adaptive clarification should require zero follow-up questions!
    q2 = consultant.get_next_clarification(state)
    assert q2 is None

    brief = consultant.build_structured_brief(state)
    assert "residential conservatory" in brief.project_type.lower() or "performing arts" in brief.project_type.lower()


# =============================================================================
# 2. Adaptive Clarification (Never Repeating Already Answered Questions)
# =============================================================================

def test_adaptive_clarification_asks_only_unanswered_questions():
    """
    Verifies that:
    - If the user already specifies the subtype and pages in Turn 1, MIND does NOT
      ask for the school subtype or required pages again.
    - When selecting K–12 in Turn 2 without specifying pages/style/portal mode,
      MIND asks only the remaining unanswered material questions.
    """
    consultant = ConversationalDesignConsultant()

    # Case A: User specifies K-12 + pages + audience in Turn 1, leaving only visual style, features, & website_purpose
    s_partial = consultant.create_initial_state(
        "Design a K-12 private school website for parents and prospective students with Home, Admissions, and Academics pages"
    )
    assert bool(s_partial["subtype_label"]) is True
    assert s_partial["target_audience"] is not None
    assert len(s_partial["required_pages"]) >= 3
    assert s_partial["visual_direction"] is None
    assert s_partial["website_purpose"] is None

    next_q = consultant.get_next_clarification(s_partial)
    assert next_q is not None
    assert next_q["slot_name"] == "design_discovery_details"
    # Must NOT ask about target_audience or required_pages (already answered!)
    assert "target_audience" not in next_q["missing_dimensions"]
    assert "required_pages" not in next_q["missing_dimensions"]
    assert "Who is the primary audience" not in next_q["question"]
    assert "Which pages are needed" not in next_q["question"]
    # Must ask about the unanswered dimensions (visual_direction, main_features, website_purpose)
    assert "visual_direction" in next_q["missing_dimensions"]
    assert "website_purpose" in next_q["missing_dimensions"]

    # Case B: "Create a website for a school" -> must NOT extract "a school" or "school" as target_audience
    s_for_school = consultant.create_initial_state("Create a website for a school")
    assert s_for_school["target_audience"] is None

    # Also verify GameSpecification.from_dict roundtrip for stateless AIWorker approval across turns
    from MIND_GameDev.models import ProjectSpecification, ProjectType
    spec_orig = ProjectSpecification(
        title="University / Higher Education Website",
        project_type=ProjectType.WEBSITE,
        project_name="university_higher_education",
        pages=["Home", "Admissions", "Academics"],
    )
    spec_restored = ProjectSpecification.from_dict(spec_orig.to_dict())
    assert spec_restored.title == "University / Higher Education Website"
    assert spec_restored.project_type == ProjectType.WEBSITE
    assert spec_restored.pages == ["Home", "Admissions", "Academics"]


# =============================================================================
# 3. Session Isolation Across Unrelated Design Requests
# =============================================================================

def test_discovery_session_isolation_when_switching_projects(tmp_path):
    """
    Verifies that starting a new unrelated design request while a previous discovery
    session is active cleanly isolates the new session without leaking requirements.
    """
    transport = SchoolStitchMCPTransport()
    stitch_adapter = StitchAdapter(api_key="AQ.TestKey", transport=transport)

    cfg = GameDevConfig.load()
    cfg.test_mode = False
    cfg.require_design_approval = True
    cfg.workspace_root = tmp_path / "ws_iso"
    cfg.workspace_root.mkdir(parents=True, exist_ok=True)

    mem = SessionMemory(db_path=tmp_path / "iso.db")
    state = ConversationState(mem)
    orch = GameDevOrchestrator(
        config=cfg,
        enable_voice=False,
        session_memory=mem,
        conversation_state=state,
        stitch_adapter=stitch_adapter,
    )

    # Start school discovery and select K-12
    r1 = orch.execute_command("Design a modern school website.")
    assert r1["status"] == "CLARIFY"
    s1_id = r1["discovery_session_id"]

    r2 = orch.execute_command("K–12 academy / private school")
    assert r2["status"] == "CLARIFY"
    assert r2["discovery_stage"] == "details"

    # Now user abandons school request and starts an unrelated restaurant website request
    r_new = orch.execute_command("Design a modern restaurant website.")
    assert r_new["status"] == "CLARIFY"
    assert r_new["discovery_stage"] == "subtype"
    s2_id = r_new["discovery_session_id"]
    assert s2_id != s1_id
    # Options presented must be for Restaurant, not School
    opt_labels = [o["label"].lower() for o in r_new["options"]]
    assert any("bistro" in l or "fine dining" in l or "cafe" in l for l in opt_labels)
    assert not any("k–12" in l or "university" in l for l in opt_labels)


# =============================================================================
# 4. Complete 14-Step End-to-End Desktop Validation Scenario
# =============================================================================

def test_complete_14_step_end_to_end_desktop_validation(view, tmp_path):
    """
    Validates the complete 14-step user-facing scenario through the actual MIND
    desktop interface (`UnifiedAssistantView` + `WorkflowArtifactBubble` +
    `DesignPreviewWindow` + `GameDevOrchestrator` + `StitchAdapter`):

      1. User requests a school website ("Design a modern school website.").
      2. MIND asks whether it is a K–12 school, university, or another type.
      3. User selects K–12 (via desktop UI option button).
      4. MIND asks only the remaining important questions.
      5. User provides answers through chat.
      6. MIND prepares the 10-field StructuredDesignBrief and shows it in the UI.
      7. MIND invokes the Stitch API with the structured brief.
      8. Stitch returns its generated design.
      9. MIND displays the design in the dedicated DesignPreviewWindow popup.
      10. User requests a revision through chat.
      11. MIND sends the revision to Stitch (preserving structured brief context).
      12. The existing popup updates in-place to v2.
      13. User explicitly approves the design.
      14. MIND records approval (DESIGN_APPROVED) without automatically starting website implementation.
    """
    transport = SchoolStitchMCPTransport()
    stitch_adapter = StitchAdapter(api_key="AQ.SchoolKey998877", transport=transport)

    cfg = GameDevConfig.load()
    cfg.test_mode = False
    cfg.require_design_approval = True
    cfg.workspace_root = tmp_path / "ws_e2e_school"
    cfg.workspace_root.mkdir(parents=True, exist_ok=True)

    mem = SessionMemory(db_path=tmp_path / "e2e_school.db")
    state = ConversationState(mem)
    orch = GameDevOrchestrator(
        config=cfg,
        enable_voice=False,
        session_memory=mem,
        conversation_state=state,
        stitch_adapter=stitch_adapter,
    )

    last_result: Dict[str, Any] = {}

    def _on_desktop_prompt(text: str, _choice: str) -> None:
        nonlocal last_result
        res = orch.execute_command(
            text,
            progress_callback=lambda data, _pct=0.5: (
                view.update_workflow_progress(data) if isinstance(data, dict) else None
            ),
        )
        last_result = res
        view.complete_workflow(res)

    view.prompt_sent.connect(_on_desktop_prompt)

    # Guard against any internal website code implementation during the entire 14-step flow
    with patch.object(
        orch.project_creator,
        "create_project",
        side_effect=AssertionError("Website code implementation must NOT start automatically!"),
    ) as mock_creator:

        # ------------------------------------------------------------------
        # Step 1: User requests a school website in the desktop chat UI
        # ------------------------------------------------------------------
        view.input_edit.setPlainText("Design a modern school website.")
        view.btn_send.click()
        _pump(100)

        # ------------------------------------------------------------------
        # Step 2: MIND asks whether it is a K–12 school, university, or another type
        # ------------------------------------------------------------------
        assert last_result["status"] == "CLARIFY"
        assert last_result["discovery_stage"] == "subtype"
        assert len(transport.requests) == 0, "Stitch must not be called during discovery"

        # Find the active consultation bubble in the desktop chat thread
        bubbles = [
             view.messages_layout.itemAt(i).widget()
            for i in range(view.messages_layout.count())
            if isinstance(view.messages_layout.itemAt(i).widget(), WorkflowArtifactBubble)
        ]
        assert len(bubbles) == 1
        b_step2 = bubbles[-1]
        assert b_step2.lbl_status_pill.text() == "DESIGN CONSULTATION"
        assert b_step2.options_box.isVisible()
        assert len(b_step2._option_buttons) == 6
        assert "K–12 Academy / Private School" in b_step2._option_buttons[0].text()

        # ------------------------------------------------------------------
        # Step 3: User selects K–12 by clicking the option button in the desktop UI
        # ------------------------------------------------------------------
        b_step2._option_buttons[0].click()
        _pump(100)

        # ------------------------------------------------------------------
        # Step 4: MIND asks only the remaining important questions
        # ------------------------------------------------------------------
        assert last_result["status"] == "CLARIFY"
        assert last_result["discovery_stage"] == "details"
        assert "K–12 Academy / Private School" in last_result["question"]
        # Subtype was already answered, so only remaining questions are asked
        unanswered = last_result["unanswered_dimensions"]
        assert set(unanswered) == {
            "target_audience",
            "website_purpose",
            "required_pages",
            "main_features",
            "visual_direction",
        }
        assert len(transport.requests) == 0, "Stitch still must not be called until brief is ready"

        # ------------------------------------------------------------------
        # Step 5: User provides answers through the desktop chat UI
        # ------------------------------------------------------------------
        user_details = (
            "Primary audience is prospective families, parents, and Upper School students. "
            "Required pages: Home, Admissions, Academics, Athletics & Arts, and a Parent/Student Portal. "
            "Visual style: prestigious navy blue, warm gold, and ivory editorial layout. "
            "Main features: interactive campus tour booking, tuition & scholarship calculator, and STEM lab showcase. "
            "Include both a public informational website and a student/parent portal login."
        )
        view.input_edit.setPlainText(user_details)
        view.btn_send.click()
        _pump(200)

        # ------------------------------------------------------------------
        # Step 6: MIND prepares the 10-field StructuredDesignBrief & displays it
        # ------------------------------------------------------------------
        assert last_result["status"] == "APPROVAL_REQUIRED"
        assert last_result["provider"] == "stitch"
        brief_dict = last_result.get("design_brief")
        assert isinstance(brief_dict, dict)

        required_10_fields = [
            "project_type",
            "target_audience",
            "website_purpose",
            "required_pages_and_screens",
            "navigation_structure",
            "important_content_sections",
            "visual_direction",
            "branding_requirements",
            "responsive_requirements",
            "special_functionality",
        ]
        for field_name in required_10_fields:
            assert brief_dict.get(field_name), f"StructuredDesignBrief missing field: {field_name}"

        assert "K–12" in brief_dict["project_type"]
        assert "navy" in brief_dict["visual_direction"].lower()

        # Verify the desktop UI bubble renders the Structured Design Brief box
        bubbles_after_gen = [
            view.messages_layout.itemAt(i).widget()
            for i in range(view.messages_layout.count())
            if isinstance(view.messages_layout.itemAt(i).widget(), WorkflowArtifactBubble)
        ]
        b_design = bubbles_after_gen[-1]
        assert b_design.brief_box.isVisible()
        assert "K–12 Academy / Private School" in b_design.lbl_brief_content.text()

        # ------------------------------------------------------------------
        # Step 7 & 8: MIND invokes Stitch with the structured brief & Stitch returns design
        # ------------------------------------------------------------------
        assert len(transport.generate_prompts) == 1
        sent_stitch_prompt = transport.generate_prompts[0]
        assert "K–12 Academy / Private School" in sent_stitch_prompt
        assert "Target Audience:" in sent_stitch_prompt
        assert "Required Pages & Screens:" in sent_stitch_prompt
        assert "Navigation Structure:" in sent_stitch_prompt
        assert "Visual Direction:" in sent_stitch_prompt
        assert "Special Functionality" in sent_stitch_prompt

        # ------------------------------------------------------------------
        # Step 9: MIND displays the generated design in the popup window
        # ------------------------------------------------------------------
        win = view.design_preview.window
        assert isinstance(win, DesignPreviewWindow)
        assert win.isVisible()
        assert view.design_preview.window_open_count == 1
        assert win.lbl_version.text() == "DESIGN v1"
        assert "STITCH-K12-ACADEMY-V1-HERO" in win.preview_widget._last_valid_html
        assert win.record.approval_state == STATE_AWAITING

        # ------------------------------------------------------------------
        # Step 10: User requests a revision through chat
        # ------------------------------------------------------------------
        view.input_edit.setPlainText(
            "Highlight the Robotics & STEM Innovation Lab in the hero section and add a Merit Scholarship calculator"
        )
        view.btn_send.click()
        _pump(200)

        # ------------------------------------------------------------------
        # Step 11: MIND sends the revision to Stitch (retaining structured brief context)
        # ------------------------------------------------------------------
        assert len(transport.edit_prompts) == 1
        rev_prompt = transport.edit_prompts[0]
        assert "Highlight the Robotics & STEM Innovation Lab" in rev_prompt
        assert "K–12 Academy / Private School" in rev_prompt, "Revision prompt must preserve brief context"

        # ------------------------------------------------------------------
        # Step 12: The existing popup updates in-place to v2
        # ------------------------------------------------------------------
        assert last_result["status"] == "APPROVAL_REQUIRED"
        assert last_result["version"] == 2
        assert view.design_preview.window is win
        assert view.design_preview.window_open_count == 1
        assert win.lbl_version.text() == "DESIGN v2"
        assert "STITCH-K12-ACADEMY-V2-STEM-SCHOLARSHIP-SHOWCASE" in win.preview_widget._last_valid_html
        assert win.record.approval_state == STATE_AWAITING

        # ------------------------------------------------------------------
        # Step 13: User explicitly approves the design
        # ------------------------------------------------------------------
        win.btn_approve.click()
        _pump(120)

        # ------------------------------------------------------------------
        # Step 14: MIND records approval without starting website implementation
        # ------------------------------------------------------------------
        assert last_result["status"] == "DESIGN_APPROVED"
        assert win.record.approval_state == STATE_APPROVED
        assert orch.conversation_state.pending_design_approval is None
        assert orch.conversation_state.approved_stitch_design is not None
        assert orch.conversation_state.approved_stitch_design["version"] == 2
        assert orch.conversation_state.approved_stitch_design["status"] == "approved"
        assert mock_creator.call_count == 0, "Approval must NOT auto-start website code generation"


# =============================================================================
# 5. Live Google Stitch API End-to-End Discovery -> Brief -> Stitch Generation Check
# =============================================================================

@pytest.mark.skipif(
    not os.getenv("STITCH_API_KEY") or os.getenv("STITCH_API_KEY", "").startswith("your_"),
    reason="Live Google Stitch API key not configured in environment.",
)
def test_live_end_to_end_discovery_brief_and_real_stitch_generation(view, tmp_path):
    """
    LIVE STITCH END-TO-END VALIDATION:
    Executes the conversational discovery flow ("Design a modern school website." ->
    "K–12 academy / private school" -> user answers) and then invokes the REAL
    Google Stitch MCP API (`https://stitch.googleapis.com/mcp`) with the generated
    `StructuredDesignBrief`, renders the real Stitch HTML inside `DesignPreviewWindow`,
    and verifies explicit approval.

    To avoid excessive upstream API generation requests during routine pytest runs
    once verified, if a project in the live Stitch account already has a generated
    screen, we verify live MCP `list_projects` + `list_screens` + `download_file`
    unless `MIND_FORCE_LIVE_STITCH_GENERATE=1` is set.
    """
    live_stitch = StitchAdapter()
    assert live_stitch.is_configured is True

    projects = live_stitch.list_projects()
    existing_pid = None
    existing_screens = []
    for p in projects[:5]:
        pid = live_stitch.normalize_project_id(p.get("name", ""))
        if pid:
            existing_pid = pid
            scrs = live_stitch.list_screens(pid)
            if scrs:
                existing_screens = scrs
                break

    cfg = GameDevConfig.load()
    cfg.test_mode = False
    cfg.require_design_approval = True
    cfg.workspace_root = tmp_path / "ws_live_e2e"
    cfg.workspace_root.mkdir(parents=True, exist_ok=True)

    mem = SessionMemory(db_path=tmp_path / "live_e2e.db")
    state = ConversationState(mem)
    orch = GameDevOrchestrator(
        config=cfg,
        enable_voice=False,
        session_memory=mem,
        conversation_state=state,
        stitch_adapter=live_stitch,
    )

    # Turn 1: Ambiguous school website request -> Discovery Stage 1
    r1 = orch.execute_command("Design a modern school website.")
    assert r1["status"] == "CLARIFY"
    assert r1["discovery_stage"] == "subtype"
    view.complete_workflow(r1)
    _pump(60)

    # Turn 2: User selects K–12 -> Discovery Stage 2 (adaptive follow-up)
    r2 = orch.execute_command("K–12 academy / private school")
    assert r2["status"] == "CLARIFY"
    assert r2["discovery_stage"] == "details"
    view.complete_workflow(r2)
    _pump(60)

    # Turn 3: User provides answers -> StructuredDesignBrief built & sent to StitchAdapter
    orig_gen = live_stitch.generate_design
    captured_live_prompts: List[str] = []

    def _live_stitch_handler(prompt: str, session_dir: Path, project_id=None, title="Website Design", **kwargs):
        captured_live_prompts.append(prompt)
        if existing_pid and existing_screens and os.getenv("MIND_FORCE_LIVE_STITCH_GENERATE") != "1":
            # Live MCP screen retrieval + real HTML download without triggering a redundant 3-minute model build
            from MIND_GameDev.adapters.stitch_adapter import StitchDesignBundle
            v_dir = Path(session_dir) / "v1"
            artifacts = live_stitch._materialize_screens(existing_pid, existing_screens[:1], v_dir)
            primary = artifacts[0]
            return StitchDesignBundle(
                session_id=f"stitch_{existing_pid}",
                project_id=existing_pid,
                title=title,
                prompt=prompt,
                version=1,
                version_dir=str(v_dir),
                preview_file=primary.html_path,
                screens=artifacts,
                assistant_text="Live Stitch MCP screen materialized for end-to-end validation.",
            )
        return orig_gen(
            prompt=prompt,
            session_dir=session_dir,
            project_id=project_id or existing_pid,
            title=title,
            **kwargs,
        )

    with patch.object(live_stitch, "generate_design", side_effect=_live_stitch_handler):
        r3 = orch.execute_command(
            "Prospective families and students; pages: Home, Admissions, Academics, Campus Life; "
            "prestigious navy and gold style; campus tour booking and admissions timeline; "
            "public informational website with a parent portal link."
        )

    assert len(captured_live_prompts) == 1
    assert "K–12 Academy / Private School" in captured_live_prompts[0]
    assert "1. Target Audience:" in captured_live_prompts[0]
    assert "3. Required Pages & Screens:" in captured_live_prompts[0]

    assert r3["status"] == "APPROVAL_REQUIRED"
    assert r3["provider"] == "stitch"
    assert isinstance(r3.get("design_brief"), dict)
    assert Path(r3["preview_file"]).exists()
    html_bytes = Path(r3["preview_file"]).stat().st_size
    assert html_bytes > 5000, f"Expected real Stitch HTML (>5KB), got {html_bytes} bytes"

    view.complete_workflow(r3)
    _pump(150)

    win = view.design_preview.window
    assert win is not None and win.isVisible()
    assert len(win.preview_widget._last_valid_html) > 5000
    assert win.record.approval_state == STATE_AWAITING

    # Approve explicitly
    r_appr = orch.execute_command("Approve")
    assert r_appr["status"] == "DESIGN_APPROVED"
    view.complete_workflow(r_appr)
    _pump(60)
    assert win.record.approval_state == STATE_APPROVED
