"""
MIND Universal Development Studio — Base Workflow Contract.
Defines the abstract interface for all specialized project workflows:
website, web_app, backend_api, mobile_app, desktop_app, game, automation, and custom.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, List, Optional

from ..models import ProjectSpecification, DevProject, ProjectType, ExecutionReport
from ..tools.workspace_files import SafeWorkspaceManager


class BaseProjectWorkflow(ABC):
    """Abstract base class that all specialized development workflows implement."""

    project_type: ProjectType

    def __init__(self, config: Optional[Any] = None, coding_adapter: Optional[Any] = None) -> None:
        from ..config import GameDevConfig
        from ..adapters.coding_adapter import CodingAdapter
        self.config = config or GameDevConfig.load()
        self.coding_adapter = coding_adapter or CodingAdapter(self.config)

    @abstractmethod
    def build(self, spec: ProjectSpecification, workspace: SafeWorkspaceManager) -> Dict[str, Any]:
        """
        Scaffolds all source files, templates, styles, dependencies, and configuration.
        Returns build status metadata.
        """
        pass

    @abstractmethod
    def verify(self, project_dir: Path) -> ExecutionReport:
        """
        Executes static analysis, syntax checking, unit tests, and live server checks
        appropriate for this project type.
        """
        pass

    @abstractmethod
    def get_run_instructions(self, project_dir: Path) -> Dict[str, Any]:
        """
        Returns run commands, local URLs, and execution instructions.
        """
        pass
