"""Tests for the consolidated contract surface.

Verifies that:
- All 78 protocols are importable from ``loom_ai.contracts``
- Every exported protocol is ``@runtime_checkable``
- The count matches expectations
- No naming collisions exist in the consolidated namespace
- Old import paths still work (backward compatibility)
"""

from __future__ import annotations

import importlib
import inspect
from typing import Protocol

import pytest

import loom_ai.contracts as contracts

# ---------------------------------------------------------------------------
# Expected protocols by source module
# ---------------------------------------------------------------------------

EXPECTED_PROTOCOLS: dict[str, list[str]] = {
    "loom_ai.protocols": [
        "EmbeddingBackend",
        "GraphBackend",
        "IdempotentStore",
        "LLMBackend",
        "QueueBackend",
        "ResourceProvider",
        "SearchBackend",
        "SecretsBackend",
        "StorageBackend",
        "TaskRunner",
        "ToolProvider",
    ],
    "loom_ai.contracts_phase1": [
        "ChunkingStrategy",
        "ConversationManager",
        "ExecutionPattern",
        "KnowledgePipeline",
        "ModelRouter",
        "PersistentMemoryBackend",
        "StructuredOutputMixin",
    ],
    "loom_ai.contracts_phase2": [
        "BudgetTracker",
        "LearningExtractor",
        "ObservabilityBackend",
        "ResiliencePolicy",
        "StrategySelector",
        "TranscriptStore",
        "WorkflowEngine",
        "WorkflowStorageBackend",
    ],
    "loom_ai.contracts_phase3": [
        "CachePolicy",
        "EvaluationHarness",
        "FeedbackLoopDetector",
        "HumanInTheLoop",
        "SessionInitializer",
        "WorkerRegistry",
    ],
    "loom_ai.contracts_phase4": [
        "BeliefManager",
        "ExternalGraphAdapter",
        "GraphRetriever",
        "KnowledgeGraph",
        "TemporalKnowledgeStore",
    ],
    "loom_ai.contracts_phase5": [
        "AgentLifecycleRuntime",
        "AgentMemory",
        "EvalSuite",
        "GenAITelemetry",
        "InferenceRouter",
        "OutputValidator",
        "ProgramOptimizer",
        "SecurityGate",
    ],
    "loom_ai.contracts_phase6": [
        "ACPAdapter",
        "AgentCapabilityRegistry",
        "AgentEnvironment",
        "AgentLoop",
        "ContextAssembler",
        "RecipeExecutor",
        "TrajectoryStore",
    ],
    "loom_ai.contracts_phase7": [
        "CatalogSynchronizer",
        "PolicyRegistry",
        "ProviderCapabilityRegistry",
        "ProviderRegistry",
    ],
    "loom_ai.contracts_phase8": [
        "CapabilitySelector",
        "ConsensusStrategy",
        "EvalCapabilityRegistry",
        "EvaluationEnvironment",
        "InferenceOptimizer",
        "InteractionEvaluator",
        "OutputNormalizer",
        "SkillEstimator",
        "TournamentRunner",
    ],
    "loom_ai.contracts_phase9": [
        "CanonicalSourceIndex",
        "CapabilityBackend",
        "ContextCompressor",
        "ContextEngine",
        "EvaluationEngine",
        "HealthCheckPolicy",
        "ModelEvaluationCandidate",
        "PluggableAgentRuntime",
        "PromptCacheOptimizer",
        "RequestValidator",
    ],
    "loom_ai.contracts_api": [
        "ErrorHandler",
        "Middleware",
        "RequestLifecycle",
    ],
}

ALL_PROTOCOL_NAMES: list[str] = sorted(
    name for names in EXPECTED_PROTOCOLS.values() for name in names
)

EXPECTED_COUNT = 78


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestContractCount:
    """Verify the total contract count matches expectations."""

    def test_expected_count_matches_inventory(self) -> None:
        assert len(ALL_PROTOCOL_NAMES) == EXPECTED_COUNT

    def test_all_exported_from_contracts(self) -> None:
        assert len(contracts.__all__) == EXPECTED_COUNT


class TestImportability:
    """Every protocol must be importable from loom_ai.contracts."""

    @pytest.mark.parametrize("name", ALL_PROTOCOL_NAMES)
    def test_importable_from_contracts(self, name: str) -> None:
        obj = getattr(contracts, name, None)
        assert obj is not None, f"{name} not found in loom_ai.contracts"

    @pytest.mark.parametrize("name", ALL_PROTOCOL_NAMES)
    def test_is_protocol_class(self, name: str) -> None:
        obj = getattr(contracts, name)
        assert inspect.isclass(obj), f"{name} is not a class"
        assert issubclass(obj, Protocol), f"{name} does not subclass Protocol"


class TestRuntimeCheckable:
    """Every exported protocol must be @runtime_checkable."""

    @pytest.mark.parametrize("name", ALL_PROTOCOL_NAMES)
    def test_runtime_checkable(self, name: str) -> None:
        obj = getattr(contracts, name)
        assert getattr(obj, "__protocol_attrs__", None) is not None or getattr(
            obj, "_is_runtime_protocol", False
        ), f"{name} is not @runtime_checkable"


class TestNoCollisions:
    """No naming collisions in the consolidated namespace."""

    def test_no_duplicate_names(self) -> None:
        seen: set[str] = set()
        duplicates: list[str] = []
        for names in EXPECTED_PROTOCOLS.values():
            for name in names:
                if name in seen:
                    duplicates.append(name)
                seen.add(name)
        assert duplicates == [], f"Duplicate protocol names: {duplicates}"

    def test_all_matches_contracts_all(self) -> None:
        assert sorted(contracts.__all__) == ALL_PROTOCOL_NAMES


class TestBackwardCompatibility:
    """Old import paths must still work."""

    @pytest.mark.parametrize(
        "module_name,names",
        list(EXPECTED_PROTOCOLS.items()),
    )
    def test_original_module_still_exports(
        self, module_name: str, names: list[str]
    ) -> None:
        mod = importlib.import_module(module_name)
        for name in names:
            assert hasattr(mod, name), (
                f"{name} not found in original module {module_name}"
            )

    @pytest.mark.parametrize(
        "module_name,names",
        list(EXPECTED_PROTOCOLS.items()),
    )
    def test_identity_matches(self, module_name: str, names: list[str]) -> None:
        """The facade re-exports the exact same class objects."""
        mod = importlib.import_module(module_name)
        for name in names:
            original = getattr(mod, name)
            facade = getattr(contracts, name)
            assert original is facade, (
                f"{name}: facade object differs from {module_name}"
            )


class TestTopLevelExports:
    """Key contracts should be importable from loom_ai directly."""

    TOP_LEVEL_CONTRACTS = [
        "EmbeddingBackend",
        "GraphBackend",
        "IdempotentStore",
        "LLMBackend",
        "QueueBackend",
        "ResourceProvider",
        "SearchBackend",
        "SecretsBackend",
        "StorageBackend",
        "TaskRunner",
        "ToolProvider",
        "ConversationManager",
        "EvaluationHarness",
        "ModelRouter",
        "ObservabilityBackend",
        "PersistentMemoryBackend",
        "SessionInitializer",
        "StructuredOutputMixin",
        "WorkerRegistry",
        "WorkflowEngine",
    ]

    @pytest.mark.parametrize("name", TOP_LEVEL_CONTRACTS)
    def test_importable_from_top_level(self, name: str) -> None:
        import loom_ai

        assert hasattr(loom_ai, name), f"{name} not importable from loom_ai"
