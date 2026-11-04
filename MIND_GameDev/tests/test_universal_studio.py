"""
Unit tests for MIND Universal Development Studio:
Tests workflow resolution, multi-page website creation, web app state management,
FastAPI endpoint testing, desktop app diagnostics, automation tools, and Android scaffolding.
"""

import tempfile
import pytest
from pathlib import Path

from MIND_GameDev.config import GameDevConfig
from MIND_GameDev.models import ProjectSpecification, ProjectType
from MIND_GameDev.tools.workspace_files import SafeWorkspaceManager
from MIND_GameDev.game_workflows.workflow_registry import WorkflowRegistry
from MIND_GameDev.game_workflows.project_creator import GameProjectCreator
from MIND_GameDev.game_workflows.website_workflow import WebsiteWorkflow
from MIND_GameDev.game_workflows.web_app_workflow import WebAppWorkflow
from MIND_GameDev.game_workflows.backend_api_workflow import BackendApiWorkflow
from MIND_GameDev.game_workflows.desktop_app_workflow import DesktopAppWorkflow
from MIND_GameDev.game_workflows.automation_workflow import AutomationWorkflow
from MIND_GameDev.game_workflows.mobile_app_workflow import MobileAppWorkflow
from MIND_GameDev.game_workflows.custom_workflow import CustomWorkflow


def test_workflow_intent_inference():
    # Test intent classifier accurately resolves domain without collisions
    assert WorkflowRegistry.infer_project_type("Build a multi-page marketing website") == ProjectType.WEBSITE
    assert WorkflowRegistry.infer_project_type("Create a single page web application dashboard") == ProjectType.WEB_APP
    assert WorkflowRegistry.infer_project_type("Build a backend REST API with FastAPI") == ProjectType.BACKEND_API
    assert WorkflowRegistry.infer_project_type("Create a 3D endless runner game in space") == ProjectType.GAME
    assert WorkflowRegistry.infer_project_type("Build a Windows desktop utility with Tkinter") == ProjectType.DESKTOP_APP
    assert WorkflowRegistry.infer_project_type("Create a batch automation CLI tool") == ProjectType.AUTOMATION
    assert WorkflowRegistry.infer_project_type("Build a mobile Android application in Kotlin") == ProjectType.MOBILE_APP
    # Test defect fix: login screen must be classified as WEB_APP, not GAME
    assert WorkflowRegistry.infer_project_type("Create a responsive login screen for SLIIT Campus") == ProjectType.WEB_APP
    assert WorkflowRegistry.infer_project_type("Build a responsive multi-page portfolio website") == ProjectType.WEBSITE
    assert WorkflowRegistry.infer_project_type("Build a task management web app with persistent local storage") == ProjectType.WEB_APP
    assert WorkflowRegistry.infer_project_type("Create a small REST API with automated endpoint tests") == ProjectType.BACKEND_API
    # Test ambiguous input routes to CUSTOM, never GAME
    assert WorkflowRegistry.infer_project_type("Build a tool for my team") == ProjectType.CUSTOM
    assert WorkflowRegistry.infer_project_type("Something general") == ProjectType.CUSTOM
    # Test collision resistance: "space" must not trigger "spa" for web app
    assert WorkflowRegistry.infer_project_type("Explore outer space mission") == ProjectType.CUSTOM
    assert WorkflowRegistry.infer_project_type("Play space runner game") == ProjectType.GAME


def test_login_screen_build_and_verify():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = SafeWorkspaceManager(Path(tmpdir))
        workflow = WebAppWorkflow()
        spec = ProjectSpecification(
            title="SLIIT Campus Student & Staff Portal",
            project_name="sliit_campus_login",
            description="Create a responsive login screen for SLIIT Campus",
            project_type=ProjectType.WEB_APP,
        )

        res = workflow.build(spec, ws)
        assert res["status"] == "SUCCESS"
        assert res.get("app_variant") == "login_portal"

        # Check files
        index_html = (ws.base_directory / "index.html").read_text(encoding="utf-8")
        assert "<form" in index_html.lower() or "input" in index_html.lower()
        assert "password" in index_html.lower()

        style_css = (ws.base_directory / "style.css").read_text(encoding="utf-8")
        assert "{" in style_css and "}" in style_css

        app_js = (ws.base_directory / "js" / "app.js").read_text(encoding="utf-8")
        assert len(app_js.strip()) > 50

        report = workflow.verify(ws.base_directory)
        assert report.success is True
        assert report.project_type == "web_app"


def test_custom_workflow_build_and_verify():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = SafeWorkspaceManager(Path(tmpdir))
        workflow = CustomWorkflow()
        spec = ProjectSpecification(
            title="Universal Custom Project",
            project_name="custom_tool",
            description="Custom software utility",
            project_type=ProjectType.CUSTOM,
        )

        res = workflow.build(spec, ws)
        assert res["status"] == "SUCCESS"
        assert (ws.base_directory / "app" / "main.py").exists()
        assert (ws.base_directory / "index.html").exists()
        assert (ws.base_directory / "tests" / "test_custom.py").exists()

        report = workflow.verify(ws.base_directory)
        assert report.success is True
        assert report.project_type == ProjectType.CUSTOM


def test_website_workflow_build_and_verify():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = SafeWorkspaceManager(Path(tmpdir))
        workflow = WebsiteWorkflow()
        spec = ProjectSpecification(title="Aura Digital", project_type=ProjectType.WEBSITE)

        res = workflow.build(spec, ws)
        assert res["status"] == "SUCCESS"
        assert (ws.base_directory / "index.html").exists()
        assert (ws.base_directory / "about.html").exists()
        assert (ws.base_directory / "services.html").exists()
        assert (ws.base_directory / "contact.html").exists()
        assert (ws.base_directory / "style.css").exists()
        assert (ws.base_directory / "js" / "main.js").exists()

        report = workflow.verify(ws.base_directory)
        assert report.success is True
        assert report.project_type == "website"


def test_web_app_workflow_build_and_verify():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = SafeWorkspaceManager(Path(tmpdir))
        workflow = WebAppWorkflow()
        spec = ProjectSpecification(title="TaskPulse Pro", project_type=ProjectType.WEB_APP)

        res = workflow.build(spec, ws)
        assert res["status"] == "SUCCESS"
        assert (ws.base_directory / "index.html").exists()
        assert (ws.base_directory / "style.css").exists()
        assert (ws.base_directory / "js" / "store.js").exists()
        assert (ws.base_directory / "js" / "components.js").exists()
        assert (ws.base_directory / "js" / "app.js").exists()

        report = workflow.verify(ws.base_directory)
        assert report.success is True
        assert report.project_type == "web_app"


def test_backend_api_workflow_build_and_live_pytest():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = SafeWorkspaceManager(Path(tmpdir))
        workflow = BackendApiWorkflow()
        spec = ProjectSpecification(title="Test Microservice API", project_type=ProjectType.BACKEND_API)

        res = workflow.build(spec, ws)
        assert res["status"] == "SUCCESS"
        assert (ws.base_directory / "app" / "main.py").exists()
        assert (ws.base_directory / "app" / "models.py").exists()
        assert (ws.base_directory / "tests" / "test_api.py").exists()

        # Run live automated test suite on the generated API
        report = workflow.verify(ws.base_directory)
        assert report.success is True
        assert report.tests_passed == 8
        assert report.tests_failed == 0


def test_desktop_app_workflow_build_and_verify():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = SafeWorkspaceManager(Path(tmpdir))
        workflow = DesktopAppWorkflow()
        spec = ProjectSpecification(title="Test Desktop Monitor", project_type=ProjectType.DESKTOP_APP)

        res = workflow.build(spec, ws)
        assert res["status"] == "SUCCESS"
        assert (ws.base_directory / "app" / "main.py").exists()
        assert (ws.base_directory / "app" / "diagnostics.py").exists()

        report = workflow.verify(ws.base_directory)
        assert report.success is True
        assert report.tests_passed >= 1


def test_automation_workflow_build_and_verify():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = SafeWorkspaceManager(Path(tmpdir))
        workflow = AutomationWorkflow()
        spec = ProjectSpecification(title="Test Automation Engine", project_type=ProjectType.AUTOMATION)

        res = workflow.build(spec, ws)
        assert res["status"] == "SUCCESS"
        assert (ws.base_directory / "automation" / "cli.py").exists()
        assert (ws.base_directory / "automation" / "engine.py").exists()

        report = workflow.verify(ws.base_directory)
        assert report.success is True
        assert report.tests_passed >= 2


def test_mobile_app_workflow_build_and_verify():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = SafeWorkspaceManager(Path(tmpdir))
        workflow = MobileAppWorkflow()
        spec = ProjectSpecification(title="Test Android App", project_type=ProjectType.MOBILE_APP)

        res = workflow.build(spec, ws)
        assert res["status"] == "SUCCESS"
        assert (ws.base_directory / "app" / "src" / "main" / "AndroidManifest.xml").exists()
        assert (ws.base_directory / "app" / "build.gradle.kts").exists()

        report = workflow.verify(ws.base_directory)
        assert report.success is True
