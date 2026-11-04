"""
MIND Universal Development Studio — Workflow Registry & Intent Classifier.
Maps project types to their specialized workflow engines and intelligently classifies user requests.
Strictly routes web apps, websites, backend services, desktop, mobile, automations, games, and custom projects.
"""

from typing import Dict, Type, Optional, List
import re

from .base_workflow import BaseProjectWorkflow
from .game_workflow import GameWorkflow
from .website_workflow import WebsiteWorkflow
from .web_app_workflow import WebAppWorkflow
from .backend_api_workflow import BackendApiWorkflow
from .desktop_app_workflow import DesktopAppWorkflow
from .automation_workflow import AutomationWorkflow
from .mobile_app_workflow import MobileAppWorkflow
from .custom_workflow import CustomWorkflow
from ..models import ProjectType


class WorkflowRegistry:
    """Central registry and factory for all development workflows."""

    _registry: Dict[ProjectType, Type[BaseProjectWorkflow]] = {
        ProjectType.GAME: GameWorkflow,
        ProjectType.WEBSITE: WebsiteWorkflow,
        ProjectType.WEB_APP: WebAppWorkflow,
        ProjectType.BACKEND_API: BackendApiWorkflow,
        ProjectType.DESKTOP_APP: DesktopAppWorkflow,
        ProjectType.AUTOMATION: AutomationWorkflow,
        ProjectType.MOBILE_APP: MobileAppWorkflow,
        ProjectType.CUSTOM: CustomWorkflow,
    }

    @classmethod
    def get_workflow(cls, project_type: ProjectType, config: Optional[Any] = None) -> BaseProjectWorkflow:
        """Instantiates and returns the workflow engine for the given project type."""
        workflow_class = cls._registry.get(project_type, CustomWorkflow)
        return workflow_class(config=config)

    @classmethod
    def list_available_types(cls) -> List[str]:
        return [pt.value for pt in cls._registry.keys()]

    @classmethod
    def infer_project_type(cls, user_prompt: str) -> ProjectType:
        """
        Infers the most appropriate project type from natural language user input.
        Uses exact token-boundary and compound phrase matching to prevent collisions.
        Guarantees that ambiguous requests default conservatively to CUSTOM, never GAME.
        """
        p = user_prompt.lower().strip()
        if not p:
            return ProjectType.CUSTOM

        # 1. Interactive Web Application Intent (Auth, Login, Dashboards, Portals)
        web_app_phrases = [
            "login screen", "login page", "login form", "authentication screen",
            "auth portal", "signup screen", "sign up screen", "sign up page",
            "registration screen", "registration page", "user portal", "student portal",
            "staff portal", "web app", "web application", "dashboard", "kanban",
            "kanban board", "single page app", "single page application",
            "task management web app", "task manager app", "interactive interface"
        ]
        if any(phrase in p for phrase in web_app_phrases):
            return ProjectType.WEB_APP

        # 2. Responsive Multi-page Website Intent
        website_phrases = [
            "portfolio website", "landing page", "multi-page website", "multi page website",
            "multi-page site", "multi page site", "corporate website", "business site",
            "marketing website", "showcase website", "brochure site", "responsive website",
            "company site", "documentation site", "docs site", "personal portfolio"
        ]
        if any(phrase in p for phrase in website_phrases):
            return ProjectType.WEBSITE

        # 3. Backend API & Microservice Intent
        backend_phrases = [
            "rest api", "rest endpoint", "backend api", "backend service",
            "microservice api", "microservice", "database service", "crud api",
            "fastapi service", "server api", "backend microservice", "rest service"
        ]
        if any(phrase in p for phrase in backend_phrases):
            return ProjectType.BACKEND_API

        # 4. Mobile Application Intent (Android, Flutter, Kotlin, APK)
        mobile_phrases = [
            "android app", "mobile application", "mobile app", "flutter app",
            "kotlin app", "react native app", "ios app", "phone app", "mobile client"
        ]
        if any(phrase in p for phrase in mobile_phrases):
            return ProjectType.MOBILE_APP

        # 5. Desktop Application Intent (Tkinter, Windows utility, GUI)
        desktop_phrases = [
            "desktop application", "desktop app", "windows utility", "desktop tool",
            "windows app", "tkinter app", "desktop software", "gui tool", "system monitor"
        ]
        if any(phrase in p for phrase in desktop_phrases):
            return ProjectType.DESKTOP_APP

        # 6. Automation & CLI Intent
        automation_phrases = [
            "batch processor", "batch process", "file-processing tool", "automation script",
            "automation tool", "cli tool", "cli processor", "cron job", "batch automation"
        ]
        if any(phrase in p for phrase in automation_phrases):
            return ProjectType.AUTOMATION

        # 7. Game Intent (Prioritize strong game terms)
        game_phrases = [
            "endless runner", "3d runner", "platformer game", "arcade game",
            "webgl game", "three.js game", "threejs game", "action game",
            "3d game", "video game", "playable game", "obstacle game"
        ]
        if any(phrase in p for phrase in game_phrases):
            return ProjectType.GAME

        # 8. Single-token regex matches with word boundaries (\b)
        # Check specific tokens that clearly designate domain
        if re.search(r"\b(login|auth|authentication|signup|portal|kanban)\b", p):
            return ProjectType.WEB_APP

        if re.search(r"\b(website|portfolio|webpage)\b", p):
            return ProjectType.WEBSITE

        if re.search(r"\b(api|endpoints?|crud|fastapi|backend)\b", p):
            return ProjectType.BACKEND_API

        if re.search(r"\b(android|mobile|apk|flutter|kotlin)\b", p):
            return ProjectType.MOBILE_APP

        if re.search(r"\b(desktop|tkinter)\b", p):
            return ProjectType.DESKTOP_APP

        if re.search(r"\b(automate|automation|cron)\b", p):
            return ProjectType.AUTOMATION

        if re.search(r"\b(game|gameplay|runner|platformer)\b", p):
            return ProjectType.GAME

        if re.search(r"\bspa\b", p):
            return ProjectType.WEB_APP

        if re.search(r"\b(gui)\b", p):
            return ProjectType.DESKTOP_APP

        if re.search(r"\b(cli)\b", p):
            return ProjectType.AUTOMATION

        # 9. Conservative default for ambiguous / unclassified input
        return ProjectType.CUSTOM
