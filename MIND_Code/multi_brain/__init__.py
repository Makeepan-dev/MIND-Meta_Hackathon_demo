"""MIND Modular Multi-Brain Architecture.

Coordinates specialized AI capabilities across domains via registries,
deterministic verification, and DAG workflow execution.
"""

import os
from multi_brain.brains.analysis_brain import AnalysisDataBrain
from multi_brain.brains.audio_brain import AudioCommunicationBrain
from multi_brain.brains.base import SpecialistBrain
from multi_brain.brains.coding_brain import CodingEngineeringBrain
from multi_brain.brains.creative_brain import CreativeVisualBrain
from multi_brain.brains.reasoning_brain import ReasoningPlanningBrain
from multi_brain.brains.research_brain import ResearchKnowledgeBrain
from multi_brain.brains.threed_brain import ThreeDGenerationBrain
from multi_brain.brains.verification_brain import VerificationCritiqueBrain
from multi_brain.brains.video_brain import VideoGenerationBrain
from multi_brain.contracts import (
    Artifact,
    Capability,
    CancellationToken,
    DesignPrototype,
    DesignSession,
    DesignWorkflowState,
    ExecutionMode,
    PermissionTier,
    Provenance,
    RequestClassification,
    TaskNode,
    TaskPlan,
    TaskRequest,
    TaskResult,
    TaskStatus,
    WorkflowCancelledError,
    WorkflowExecutionError,
    WorkflowProgress,
    WorkflowResult,
)
from multi_brain.orchestrator.orchestrator_brain import OrchestratorBrain
from multi_brain.registries.brain_registry import BrainRegistry
from multi_brain.registries.capability_registry import CapabilityRegistry
from multi_brain.registries.model_registry import ModelDescriptor, ModelModality, ModelRegistry
from multi_brain.registries.provider_registry import ProviderRegistry
from multi_brain.registries.tool_registry import ToolDefinition, ToolRegistry
from multi_brain.security.gateway import ExecutionGateway
from multi_brain.workflow.context import TaskContext
from multi_brain.workflow.engine import WorkflowEngine


from multi_brain.voice import (
    CentralVoiceController,
    CentralVoiceNotificationAuthority,
    DeliveryChannel,
    DeliveryRecord,
    DeliveryState,
    FailureCategory,
    MockVoiceSynthesizer,
    NotificationDecision,
    NotificationEvent,
    NotificationEventType,
    NotificationPriority,
    PowerShellVoiceSynthesizer,
    TaskLifecycleState,
)


_DEFAULT_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def create_multi_brain_system(workspace_root: str = _DEFAULT_REPO_ROOT) -> OrchestratorBrain:
    """
    Factory function initializing the complete MIND Modular Multi-Brain Architecture:
    1. Execution Gateway (Security & Audit)
    2. Model Registry (Ollama, LiteLLM, Deterministic)
    3. Tool Registry (AST checks, Filesystem, Math, Pillow, 3D OBJ, Doc Reader)
    4. Provider Registry (Ollama, Media Engine, Document Reader)
    5. Capability Registry (All capabilities indexed)
    6. Brain Registry (All 9 Specialist Brains registered)
    7. Workflow Engine (DAG execution, retries, bounded parallelism)
    8. Orchestrator Brain (Classifier, Planner, Coordinator)
    """
    try:
        import dotenv
        primary_env = os.path.join(workspace_root, ".env")
        if os.path.exists(primary_env):
            dotenv.load_dotenv(primary_env, override=False)
        media_test_env = os.path.join(workspace_root, ".env.media.test")
        if os.path.exists(media_test_env):
            dotenv.load_dotenv(media_test_env, override=False)
    except Exception:
        pass

    gateway = ExecutionGateway(workspace_root=workspace_root)
    model_registry = ModelRegistry()
    tool_registry = ToolRegistry(gateway=gateway)
    provider_registry = ProviderRegistry()
    capability_registry = CapabilityRegistry()
    brain_registry = BrainRegistry()

    # Register Specialist Brains (Phase 3 Complete Suite)
    brains = [
        ReasoningPlanningBrain(model_registry=model_registry),
        CodingEngineeringBrain(model_registry=model_registry, tool_registry=tool_registry),
        VerificationCritiqueBrain(tool_registry=tool_registry),
        CreativeVisualBrain(tool_registry=tool_registry),
        ThreeDGenerationBrain(tool_registry=tool_registry),
        AudioCommunicationBrain(),
        ResearchKnowledgeBrain(model_registry=model_registry, tool_registry=tool_registry),
        AnalysisDataBrain(tool_registry=tool_registry),
        VideoGenerationBrain(),
    ]

    for brain in brains:
        brain_registry.register(brain)
        # Register brain capabilities into central CapabilityRegistry
        for cap in brain.get_declared_capabilities():
            capability_registry.register(cap)

    # Register GameDev Execution Subsystem Adapter
    try:
        from multi_brain.adapter import GameDevSubsystemBrain
        gamedev_sub = GameDevSubsystemBrain(workspace_root=workspace_root)
        brain_registry.register(gamedev_sub)
        for cap in gamedev_sub.get_declared_capabilities():
            capability_registry.register(cap)
    except Exception:
        pass

    workflow_engine = WorkflowEngine(brain_registry=brain_registry)

    orchestrator = OrchestratorBrain(
        brain_registry=brain_registry,
        model_registry=model_registry,
        tool_registry=tool_registry,
        gateway=gateway,
        workflow_engine=workflow_engine,
        provider_registry=provider_registry,
        capability_registry=capability_registry,
    )

    return orchestrator


__all__ = [
    "create_multi_brain_system",
    "OrchestratorBrain",
    "SpecialistBrain",
    "ReasoningPlanningBrain",
    "CodingEngineeringBrain",
    "VerificationCritiqueBrain",
    "CreativeVisualBrain",
    "ThreeDGenerationBrain",
    "AudioCommunicationBrain",
    "ResearchKnowledgeBrain",
    "AnalysisDataBrain",
    "VideoGenerationBrain",
    "BrainRegistry",
    "CapabilityRegistry",
    "ModelRegistry",
    "ProviderRegistry",
    "ToolRegistry",
    "ExecutionGateway",
    "WorkflowEngine",
    "TaskContext",
    "Artifact",
    "CancellationToken",
    "WorkflowCancelledError",
    "WorkflowExecutionError",
    "TaskStatus",
    "TaskRequest",
    "TaskResult",
    "TaskNode",
    "TaskPlan",
    "WorkflowProgress",
    "WorkflowResult",
    "RequestClassification",
    "PermissionTier",
    "ExecutionMode",
    "Capability",
    "Provenance",
    "DesignWorkflowState",
    "DesignPrototype",
    "DesignSession",
    "CentralVoiceNotificationAuthority",
    "CentralVoiceController",
    "NotificationEvent",
    "NotificationDecision",
    "NotificationEventType",
    "NotificationPriority",
    "TaskLifecycleState",
    "DeliveryState",
    "DeliveryChannel",
    "DeliveryRecord",
    "FailureCategory",
    "MockVoiceSynthesizer",
    "PowerShellVoiceSynthesizer",
]
