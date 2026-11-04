"""
Unit and Integration Tests for AI-Driven Website Generation & Destination Handling.
Validates:
1. Exact user prompt destination and name extraction without hardcoded shortcuts.
2. Drive letter normalization and subfolder path joining.
3. AI-driven design planning with mock provider invocation.
4. Dynamic generation for unfamiliar domains without predefined category dictionaries.
5. Verification that no static domain creative dictionaries exist in the codebase.
6. Offline fallback transparency (truthful reporting without fake AI success).
7. End-to-end project creation and verification on the filesystem.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from MIND_GameDev.config import GameDevConfig
from MIND_GameDev.models import ActionType, ProjectType, ProjectSpecification
from MIND_GameDev.tools.instruction_parser import InstructionParser
from MIND_GameDev.game_workflows.website_design import AIDesignPlanner, AIDesignPlan, GenericComponentRenderer
from MIND_GameDev.game_workflows.website_workflow import WebsiteWorkflow
from MIND_GameDev.game_workflows.project_creator import GameProjectCreator
from MIND_GameDev.tools.workspace_files import SafeWorkspaceManager
from MIND_GameDev.orchestrator import GameDevOrchestrator


def test_user_prompt_destination_and_name_extraction():
    """Validates the exact user prompt scenario reported in Problem A."""
    prompt = (
        'create a fully functional website for a sports day registration and event '
        'announcements and details about couple of sports like cricket and football '
        'use css to style the website in a sports theme and save it in D drive with the name of "Sports website"'
    )
    instruction = InstructionParser.parse(prompt)

    assert instruction.action == ActionType.CREATE_PROJECT
    assert instruction.project_type == ProjectType.WEBSITE
    assert instruction.project_name == "Sports website"
    assert instruction.destination_dir == "D:\\Sports website"


def test_destination_parsing_variations():
    """Validates diverse natural phrasing for drives, parent folders, and quoted names."""
    # 1. 'in D drive with the name "Sports website"'
    inst1 = InstructionParser.parse('create a website and save it in D drive with the name "Sports website"')
    assert inst1.project_name == "Sports website"
    assert inst1.destination_dir == "D:\\Sports website"

    # 2. 'on D drive with name "Athletics Portal"'
    inst2 = InstructionParser.parse('build a site on D drive with name "Athletics Portal"')
    assert inst2.project_name == "Athletics Portal"
    assert inst2.destination_dir == "D:\\Athletics Portal"

    # 3. 'in D:\\Projects with the name "Online Banking"' -> joins parent + name
    inst3 = InstructionParser.parse('build a banking app in D:\\Projects with the name "Online Banking"')
    assert inst3.project_name == "Online Banking"
    assert inst3.destination_dir == "D:\\Projects\\Online Banking"

    # 4. 'save to D:\\TheWebsite and name it TheWebsite' -> already contains name, no duplication
    inst4 = InstructionParser.parse('create a website, save to D:\\TheWebsite and name it TheWebsite')
    assert inst4.project_name == "TheWebsite"
    assert inst4.destination_dir == "D:\\TheWebsite"

    # 5. Documents folder alias
    inst5 = InstructionParser.parse('build a portfolio site and save to my documents with the name "Portfolio"')
    assert inst5.project_name == "Portfolio"
    assert inst5.destination_dir.endswith("Documents\\Portfolio")

    # 6. Bare drive without separate name
    inst6 = InstructionParser.parse('create a website in D drive')
    assert inst6.destination_dir == "D:\\"


def test_ai_design_planner_with_mock_ai_brain():
    """Validates that AIDesignPlanner parses a bespoke JSON design plan returned by the AI provider."""
    mock_adapter = MagicMock()
    mock_adapter.config.test_mode = False

    ai_json_response = """```json
    {
      "title": "Aethelgard Medieval Forge",
      "purpose": "Custom bespoke blacksmith weaponry and chainmail fabrication",
      "target_audience": "Historical reenactors and theatrical productions",
      "visual_direction": "Rustic forged iron with molten amber accents",
      "color_palette": {
        "primary": "#d97706",
        "primary_hover": "#b45309",
        "secondary": "#78350f",
        "accent": "#ef4444",
        "bg_dark": "#18120c",
        "bg_card_dark": "#261c14",
        "text_dark": "#fef3c7",
        "bg_light": "#fffbeb",
        "bg_card_light": "#ffffff",
        "text_light": "#451a03"
      },
      "typography": {
        "display": "'Cinzel', serif",
        "body": "'Inter', sans-serif"
      },
      "hero": {
        "badge": "MASTER BLACKSMITH",
        "heading": "Forged in Dragon's Breath",
        "subtitle": "Hand-hammered Damascus steel swords and authentic battle plate",
        "cta_primary": "Commission a Blade",
        "cta_target": "#commission-form",
        "cta_secondary": "Armory Catalog",
        "cta_secondary_target": "#armory"
      },
      "sections": [
        {
          "id": "armory",
          "type": "cards",
          "heading": "Featured Weaponry",
          "lead": "Individually balanced steel forged under coal furnaces.",
          "cards": [
            {"title": "Damascus Longsword", "description": "Folded 512 times with high-carbon core.", "badge": "Masterwork"},
            {"title": "Riveted Chainmail Hauberk", "description": "Mild steel interlocking rings with oil quenched finish.", "badge": "Armor"}
          ]
        }
      ],
      "form_spec": {
        "id": "commission-form",
        "heading": "Commission a Custom Forging",
        "lead": "Submit your custom dimensions and metal requirements.",
        "submit_label": "Submit Forging Request",
        "fields": [
          {"name": "fullname", "label": "Client Name", "type": "text", "required": true},
          {"name": "email", "label": "Courier Pigeon / Email", "type": "email", "required": true},
          {"name": "weapon_type", "label": "Item Type", "type": "select", "options": ["Sword", "Armor", "Shield", "Axe"], "required": true}
        ]
      },
      "pages": [
        {"filename": "index.html", "title": "Home", "purpose": "Overview of forge"},
        {"filename": "gallery.html", "title": "Armory Gallery", "purpose": "Showcase of past commissions"}
      ],
      "features": ["Damascus folding", "Coal quenching"]
    }
    ```"""

    mock_adapter.generate.return_value = {
        "success": True,
        "code": ai_json_response,
        "provider": "openrouter",
        "model": "google/gemma-2-9b-it:free",
    }

    plan = AIDesignPlanner.plan(
        title="Aethelgard Medieval Forge",
        description="Bespoke blacksmith forge for swords and armor",
        theme="rustic forge",
        coding_adapter=mock_adapter,
        requested_pages=["index.html", "gallery.html"],
    )

    assert plan.is_fallback is False
    assert plan.ai_provider == "openrouter"
    assert plan.title == "Aethelgard Medieval Forge"
    assert plan.color_palette["primary"] == "#d97706"
    assert "Cinzel" in plan.typography["display"]
    assert len(plan.sections) == 1
    assert plan.sections[0]["cards"][0]["title"] == "Damascus Longsword"
    assert plan.form_spec["fields"][2]["name"] == "weapon_type"


def test_no_hardcoded_domain_dictionaries_in_codebase():
    """Ensures that no static creative templates or domain dictionaries exist in website_design.py."""
    design_file = Path("MIND_GameDev/game_workflows/website_design.py")
    content = design_file.read_text(encoding="utf-8")

    # Check that hardcoded domain methods and strings were deleted
    assert "_plan_sports_design" not in content
    assert "_plan_hospitality_design" not in content
    assert "_plan_finance_design" not in content
    assert "_plan_education_design" not in content
    assert "_plan_creative_design" not in content
    assert "_plan_health_design" not in content
    assert "_plan_tech_design" not in content

    # Check that specific sports/food text was removed
    assert "Cricket Championship" not in content
    assert "Single-Origin Pour Overs" not in content
    assert "Panama Geisha" not in content
    assert "11-a-side regulation football" not in content
    assert "Launchpad $1,499" not in content


def test_unfamiliar_domains_work_dynamically_without_dictionaries():
    """Verifies that arbitrary, novel domains produce valid dynamic plans without predefined categories."""
    novel_prompts = [
        ("Bioluminescent Deep Sea Station", "Underwater research lab studying deep-sea abyssal organisms"),
        ("Quantum Cryptography Foundry", "Hardware security modules for quantum key distribution"),
        ("Alpine Yurt Glamping", "Off-grid luxury yurt retreats in the Swiss Alps with solar energy"),
    ]

    for title, desc in novel_prompts:
        plan = AIDesignPlanner.plan(title, desc)
        assert plan.title == title
        assert plan.purpose == desc
        assert plan.hero["heading"] == title
        assert plan.hero["subtitle"] == desc
        # Must produce clean color palette and valid structure
        assert "primary" in plan.color_palette
        assert "bg_dark" in plan.color_palette
        assert len(plan.sections) > 0


def test_offline_fallback_transparency():
    """Ensures that offline mode truthfully reports fallback status without claiming AI generation."""
    plan = AIDesignPlanner.plan(
        title="Test Project",
        description="A simple test website",
        coding_adapter=None,
    )

    assert plan.is_fallback is True
    assert plan.ai_provider == "offline_generic_scaffolding"


def test_website_generation_produces_valid_structure_and_styles():
    """Verifies end-to-end website generation on disk with generic UI primitives and test verification."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir) / "Dynamic Project"
        ws = SafeWorkspaceManager(project_dir)

        cfg = GameDevConfig.load()
        cfg.test_mode = True
        workflow = WebsiteWorkflow(config=cfg)
        spec = ProjectSpecification(
            title="Dynamic Observatory",
            project_name="Dynamic Project",
            description="Deep space astronomical observatory and star-tracking portal",
            project_type=ProjectType.WEBSITE,
            destination_dir=str(project_dir),
        )

        res = workflow.build(spec, ws)
        assert res["status"] == "SUCCESS"
        assert res["is_fallback"] is True

        # Check required files exist
        assert (project_dir / "index.html").exists()
        assert (project_dir / "style.css").exists()
        assert (project_dir / "js" / "main.js").exists()
        assert (project_dir / "project.json").exists()

        # Check HTML content reflects the specific prompt, NOT a sports or coffee template
        index_content = (project_dir / "index.html").read_text(encoding="utf-8")
        assert "Dynamic Observatory" in index_content
        assert "Deep space astronomical observatory" in index_content
        assert "Cricket" not in index_content
        assert "Football" not in index_content

        # Check CSS custom properties & high-contrast styling
        css_content = (project_dir / "style.css").read_text(encoding="utf-8")
        assert ":root" in css_content
        assert "--primary-color:" in css_content
        assert '[data-theme="light"]' in css_content

        # Check automated verification
        report = workflow.verify(project_dir)
        assert report.success is True
        assert report.project_type == "website"


def test_orchestrator_honors_destination_without_fallback():
    """Ensures GameDevOrchestrator creates project at user-specified location instead of workspace."""
    with tempfile.TemporaryDirectory() as tmpdir:
        target_dir = Path(tmpdir) / "TargetObservatory"

        cfg = GameDevConfig.load()
        cfg.test_mode = True
        orch = GameDevOrchestrator(cfg)

        cmd = f'create a website for star tracking observatory save to {target_dir} and name it TargetObservatory'
        plan_res = orch.execute_command(cmd)
        assert plan_res["status"] == "APPROVAL_REQUIRED"

        res = orch.execute_command("approve")
        assert res["status"] == "SUCCESS"
        assert Path(res["project_path"]).resolve() == target_dir.resolve()
        assert (target_dir / "index.html").exists()
        assert (target_dir / "style.css").exists()

        # Must NOT be in the default workspace root
        assert cfg.workspace_root not in target_dir.parents
