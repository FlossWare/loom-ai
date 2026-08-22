"""Compatibility facade for the declarative workflow language."""

from loom_ai.workflow_lang import WorkflowBuilder, WorkflowDefinition, WorkflowNode, WorkflowValidationError

__all__ = [
    "WorkflowBuilder",
    "WorkflowDefinition",
    "WorkflowNode",
    "WorkflowValidationError",
]
