"""AI orchestration primitives."""

from ai_orchestrator.catalog import load_model_catalog
from ai_orchestrator.models import (
    BackendLocation,
    CandidateRejection,
    LatencyTarget,
    ModelBackend,
    ModelCapabilities,
    ModelCatalogEntry,
    ModelRecommendation,
    PrivacyClass,
    PromptIssue,
    PromptIssueSeverity,
    PromptJudgeResult,
    QualityThreshold,
    TaskCapability,
    TaskProfile,
    TaskType,
)
from ai_orchestrator.orchestrator import (
    OrchestrationResult,
    OrchestrationStatus,
    prepare_execution,
)
from ai_orchestrator.planner import ExecutionPlan, ExecutionTarget, plan_execution
from ai_orchestrator.prompt_judge import judge_prompt
from ai_orchestrator.recommender import recommend_model

__all__ = [
    "CandidateRejection",
    "ExecutionPlan",
    "ExecutionTarget",
    "LatencyTarget",
    "BackendLocation",
    "ModelBackend",
    "ModelCatalogEntry",
    "ModelCapabilities",
    "ModelRecommendation",
    "OrchestrationResult",
    "OrchestrationStatus",
    "PromptIssue",
    "PromptIssueSeverity",
    "PromptJudgeResult",
    "PrivacyClass",
    "QualityThreshold",
    "TaskCapability",
    "TaskProfile",
    "TaskType",
    "judge_prompt",
    "load_model_catalog",
    "plan_execution",
    "prepare_execution",
    "recommend_model",
]
