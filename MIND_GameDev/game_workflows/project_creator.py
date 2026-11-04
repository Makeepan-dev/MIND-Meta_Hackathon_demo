"""
MIND Universal Development Studio — Universal Project Creator.
Creates project directories, scaffolds source code across diverse architectures
(websites, web apps, backend APIs, mobile, desktop, games, automations),
synthesizes needed media assets, and produces verified DevProject records.
"""

from pathlib import Path
from typing import Optional, Dict, Any, List

from ..config import GameDevConfig
from ..models import GameProject, DevProject, GameSpecification, ProjectSpecification, ProjectType, ProjectStatus, AssetMetadata
from ..tools.workspace_files import SafeWorkspaceManager
from ..tools.project_inspector import ProjectInspector
from .workflow_registry import WorkflowRegistry
from .asset_generation import AssetWorkflowCoordinator


class GameProjectCreator:
    """Universal project factory that routes specifications to specialized workflow engines."""

    def __init__(self, config: Optional[GameDevConfig] = None) -> None:
        self.config = config or GameDevConfig.load()

    def create_project(self, spec: ProjectSpecification) -> DevProject:
        """
        Creates a new development project according to the given specification.
        Dispatches to the specialized workflow engine (website, web_app, backend_api, game, etc.).
        """
        # 1. Determine and validate project directory (authoritative user destination or default)
        if getattr(spec, "destination_dir", None):
            dest = Path(spec.destination_dir)
            try:
                dest_resolved = dest.resolve()
            except Exception as e:
                raise ValueError(f"Invalid destination path '{spec.destination_dir}': {e}")

            from ..models import SafePathValidator
            if SafePathValidator.is_system_protected_path(dest_resolved):
                raise PermissionError(
                    f"Destination path '{dest_resolved}' is a protected system directory and cannot be used."
                )

            try:
                dest_resolved.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                raise PermissionError(
                    f"Destination directory '{dest_resolved}' is inaccessible or cannot be created: {e}"
                )

            project_dir = dest_resolved
        else:
            project_dir = self.config.get_project_dir(spec.project_name)

        workspace = SafeWorkspaceManager(project_dir)

        # 1. Resolve specialized workflow engine
        p_type = getattr(spec, "project_type", ProjectType.GAME)
        if isinstance(p_type, str):
            try:
                p_type = ProjectType(p_type)
            except ValueError:
                p_type = ProjectType.GAME

        workflow = WorkflowRegistry.get_workflow(p_type, config=self.config)

        # 2. Build project source code and layout
        cb = getattr(spec, "progress_callback", None)
        try:
            build_info = workflow.build(spec, workspace, progress_callback=cb)
        except TypeError:
            build_info = workflow.build(spec, workspace)

        # 3. Generate media/3D assets where appropriate
        generated_assets: List[AssetMetadata] = []
        if p_type == ProjectType.GAME:
            asset_coord = AssetWorkflowCoordinator(workspace, self.config)
            generated_assets = asset_coord.generate_game_assets(spec)
        elif p_type in (ProjectType.WEBSITE, ProjectType.WEB_APP):
            # Optional lightweight concept banner
            textures_dir = workspace.base_directory / "assets" / "images"
            workspace.create_directory("assets/images")
            from ..adapters.image_adapter import ImageAssetAdapter
            img_adapter = ImageAssetAdapter(self.config)
            concept_meta = img_adapter.generate_concept_image(
                prompt=f"{spec.title} modern tech branding banner",
                name="hero_banner",
                output_dir=textures_dir,
            )
            generated_assets.append(concept_meta)

        # 4. Inspect final structure
        inspector = ProjectInspector(project_dir)
        summary = inspector.inspect()

        run_info = workflow.get_run_instructions(project_dir)

        project = DevProject(
            name=spec.project_name,
            root_path=str(project_dir.resolve()),
            specification=spec,
            status=ProjectStatus.GENERATED,
            project_type=p_type,
            assets=generated_assets,
            metadata={
                "build_info": build_info,
                "inspector_summary": summary,
                "run_instructions": run_info,
            },
            run_command=run_info.get("run_command", ""),
        )

        return project


# Universal alias
UniversalProjectCreator = GameProjectCreator
