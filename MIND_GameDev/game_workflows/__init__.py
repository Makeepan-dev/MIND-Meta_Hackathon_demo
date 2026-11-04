"""
MIND Universal Development Studio — Project Workflows Package.
Houses specialized workflows for:
- 3D Games (Three.js WebGL)
- Responsive Multi-Page Websites (HTML5/CSS3/JS)
- Interactive Web Applications (Single Page Dashboards)
- Backend APIs (FastAPI Microservices with automated tests)
- Desktop Utilities (Python Tkinter)
- Automations & CLI Processors
- Mobile Android Applications
"""

from .base_workflow import BaseProjectWorkflow
from .endless_runner import EndlessRunnerGenerator
from .game_workflow import GameWorkflow
from .website_workflow import WebsiteWorkflow
from .web_app_workflow import WebAppWorkflow
from .backend_api_workflow import BackendApiWorkflow
from .desktop_app_workflow import DesktopAppWorkflow
from .automation_workflow import AutomationWorkflow
from .mobile_app_workflow import MobileAppWorkflow
from .workflow_registry import WorkflowRegistry
from .asset_generation import AssetWorkflowCoordinator
from .project_creator import GameProjectCreator
from .verification import WorkflowVerifier

# Universal aliases
UniversalProjectCreator = GameProjectCreator

__all__ = [
    "BaseProjectWorkflow",
    "EndlessRunnerGenerator",
    "GameWorkflow",
    "WebsiteWorkflow",
    "WebAppWorkflow",
    "BackendApiWorkflow",
    "DesktopAppWorkflow",
    "AutomationWorkflow",
    "MobileAppWorkflow",
    "WorkflowRegistry",
    "AssetWorkflowCoordinator",
    "GameProjectCreator",
    "UniversalProjectCreator",
    "WorkflowVerifier",
]
