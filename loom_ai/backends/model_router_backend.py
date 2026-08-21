"""Loom-AI LLMBackend backed by the standalone model_router package.

Bridges the standalone ``model_router`` decorator-based router
into loom-ai's ``LLMBackend`` protocol. The standalone package
has zero loom-ai dependencies; this module adapts its types.

Usage::

    from loom_ai.backends.model_router_backend import DecoratorModelRouter

    backend = DecoratorModelRouter(
        max_monthly=300.0,
        allowed_models=["gemini-*", "claude-*"],
        free_only=False,
    )
    await backend.initialize()
    response = await backend.chat(messages)
"""

from __future__ import annotations

import logging
import os
from typing import Any, AsyncIterator

from loom_ai.models import ChatMessage as LoomChatMessage
from loom_ai.models import ChatResponse as LoomChatResponse

from model_router import (
    BudgetGuard,
    ChatMessage,
    ChatResponse,
    CohereProvider,
    CostAware,
    GeminiProvider,
    LatencyOptimizer,
    ModelCost,
    OpenAICompatProvider,
    PolicyGuard,
    ProviderRouter,
    ThompsonSamplingSelector,
    VertexAIProvider,
)

logger = logging.getLogger(__name__)


def _to_standalone(msg: LoomChatMessage) -> ChatMessage:
    return ChatMessage(role=msg.role, content=msg.content)


def _to_loom(resp: ChatResponse) -> LoomChatResponse:
    return LoomChatResponse(
        content=resp.content,
        model=resp.model,
        provider=resp.provider,
        usage=resp.usage,
    )


KNOWN_COSTS: dict[str, ModelCost] = {
    "claude-opus-4-6": ModelCost(input_per_1m=15.0, output_per_1m=75.0),
    "claude-sonnet-4-6": ModelCost(input_per_1m=3.0, output_per_1m=15.0),
    "claude-haiku-4-5": ModelCost(input_per_1m=0.80, output_per_1m=4.0),
    "gemini-2.5-flash": ModelCost(input_per_1m=0.15, output_per_1m=0.60, cached_input_per_1m=0.0375),
    "gemini-2.5-pro": ModelCost(input_per_1m=1.25, output_per_1m=10.0, cached_input_per_1m=0.3125),
    "gpt-4o": ModelCost(input_per_1m=2.50, output_per_1m=10.0),
    "gpt-4o-mini": ModelCost(input_per_1m=0.15, output_per_1m=0.60),
    "o3-mini": ModelCost(input_per_1m=1.10, output_per_1m=4.40),
}


class DecoratorModelRouter:
    """Loom-AI LLMBackend using the standalone decorator-based router.

    Composes: PolicyGuard -> BudgetGuard -> CostAware ->
              LatencyOptimizer -> ThompsonSampling -> ProviderRouter

    Parameters
    ----------
    max_monthly:
        Monthly budget cap in USD (default 300.0).
    allowed_models:
        Glob patterns for allowed model IDs (None = all).
    blocked_models:
        Glob patterns for blocked model IDs.
    allowed_providers:
        List of allowed provider names (None = all).
    free_only:
        When True, only discover free-tier models from OpenRouter.
    prefer_free:
        When True (default), free models are tried before paid ones.
    """

    def __init__(
        self,
        max_monthly: float = 300.0,
        allowed_models: list[str] | None = None,
        blocked_models: list[str] | None = None,
        allowed_providers: list[str] | None = None,
        free_only: bool = False,
        prefer_free: bool = True,
    ) -> None:
        self._max_monthly = max_monthly
        self._allowed_models = allowed_models
        self._blocked_models = blocked_models
        self._allowed_providers = allowed_providers
        self._free_only = free_only
        self._prefer_free = prefer_free
        self._router: Any = None
        self._budget_guard: BudgetGuard | None = None

    async def initialize(self) -> None:
        base = ProviderRouter()

        self._register_providers(base)

        stack: Any = base
        stack = ThompsonSamplingSelector(stack)
        stack = LatencyOptimizer(stack)
        stack = CostAware(stack, prefer_free=self._prefer_free)

        self._budget_guard = BudgetGuard(stack, max_monthly=self._max_monthly)
        stack = self._budget_guard

        if self._allowed_models or self._blocked_models or self._allowed_providers:
            stack = PolicyGuard(
                stack,
                allowed=self._allowed_models,
                blocked=self._blocked_models,
                allowed_providers=self._allowed_providers,
            )

        self._router = stack
        await self._router.initialize()

    def _register_providers(self, base: ProviderRouter) -> None:
        for env_key, provider_name in _ENV_PROVIDERS.items():
            api_key = os.environ.get(env_key, "")
            if not api_key:
                continue

            if provider_name == "gemini":
                base.add_provider(
                    GeminiProvider(cost_map=KNOWN_COSTS),
                    api_key=api_key,
                )
            elif provider_name == "cohere":
                base.add_provider(
                    CohereProvider(cost_map=KNOWN_COSTS),
                    api_key=api_key,
                )
            elif provider_name == "openrouter":
                base.add_provider(
                    OpenAICompatProvider(
                        "openrouter",
                        free_only=self._free_only,
                        cost_map=KNOWN_COSTS,
                    ),
                    api_key=api_key,
                )
            else:
                base.add_provider(
                    OpenAICompatProvider(provider_name, cost_map=KNOWN_COSTS),
                    api_key=api_key,
                )

        vertex_project = os.environ.get("VERTEX_PROJECT_ID", "")
        vertex_key = os.environ.get("VERTEX_API_KEY", "")
        if vertex_project and vertex_key:
            base.add_provider(
                VertexAIProvider(
                    project_id=vertex_project,
                    cost_map=KNOWN_COSTS,
                    available_models=[
                        "gemini-2.5-flash",
                        "gemini-2.5-pro",
                        "claude-opus-4-6",
                        "claude-sonnet-4-6",
                        "claude-haiku-4-5",
                    ],
                ),
                api_key=vertex_key,
            )

        openai_key = os.environ.get("OPENAI_API_KEY", "")
        if openai_key and not self._free_only:
            base.add_provider(
                OpenAICompatProvider("openai", cost_map=KNOWN_COSTS),
                api_key=openai_key,
            )

    async def chat(
        self,
        messages: list[LoomChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> LoomChatResponse:
        if self._router is None:
            await self.initialize()
        standalone_msgs = [_to_standalone(m) for m in messages]
        resp = await self._router.chat(
            standalone_msgs,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return _to_loom(resp)

    async def chat_stream(
        self,
        messages: list[LoomChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        resp = await self.chat(
            messages, model=model, temperature=temperature, max_tokens=max_tokens
        )
        yield resp.content

    async def list_models(self) -> list[str]:
        if self._router is None:
            await self.initialize()
        models = await self._router.list_models()
        return sorted({m.model_id for m in models})

    @property
    def budget_status(self) -> dict:
        if self._budget_guard is None:
            return {}
        s = self._budget_guard.status
        return {
            "spent_usd": s.spent_usd,
            "remaining_usd": s.remaining_usd,
            "max_usd": s.max_usd,
            "percent_used": s.percent_used,
            "calls_made": s.calls_made,
        }


_ENV_PROVIDERS: dict[str, str] = {
    "GOOGLE_API_KEY": "gemini",
    "GROQ_API_KEY": "groq",
    "COHERE_API_KEY": "cohere",
    "OPENROUTER_API_KEY": "openrouter",
    "CEREBRAS_API_KEY": "cerebras",
    "DEEPINFRA_API_KEY": "deepinfra",
    "NVIDIA_API_KEY": "nvidia",
}
