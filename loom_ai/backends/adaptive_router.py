"""Adaptive model routing with Thompson Sampling and capability profiles.

Builds on :class:`~loom_ai.backends.router.SimpleModelRouter` for
provider registration and fallback routing, and uses a
:class:`~loom_ai.backends.strategy.ThompsonSamplingSelector` bandit
internally to learn which models perform best for different task types.

Classes
-------
ModelCapabilityProfile
    Declares what a model is good at (code, reasoning, chat, etc.).
AdaptiveModelRouter
    Thompson-Sampling model router with capability-based filtering.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from loom_ai.models_core import ModelInfo, ProviderStatus

# ---------------------------------------------------------------------------
# Capability profile
# ---------------------------------------------------------------------------


@dataclass
class ModelCapabilityProfile:
    """Declares a model's capabilities and strengths.

    Parameters
    ----------
    model:
        The model identifier (e.g. ``"gpt-4o"``).
    capabilities:
        Task types the model supports (e.g. ``["code", "reasoning"]``).
    strengths:
        Mapping from task type to a prior strength score in ``[0, 1]``.
        Higher values mean the model is believed to be stronger at that
        task type *before* any empirical observations.
    """

    model: str
    capabilities: list[str] = field(default_factory=list)
    strengths: dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Internal bandit arm
# ---------------------------------------------------------------------------


@dataclass
class _ModelArm:
    """Beta-Bernoulli bandit arm for one (model, task_type) pair."""

    alpha: float = 1.0
    beta: float = 1.0
    total_trials: int = 0
    successes: int = 0
    total_reward: float = 0.0


# ---------------------------------------------------------------------------
# AdaptiveModelRouter
# ---------------------------------------------------------------------------


class AdaptiveModelRouter:
    """Thompson-Sampling model router with capability-based filtering.

    Maintains a Beta-Bernoulli bandit arm per (model, task_type) pair and
    selects the best model by sampling from each arm's posterior
    distribution.  Capability profiles allow callers to restrict the
    candidate set to models known to support a given task type.

    Provider registration and basic routing/fallback are delegated to an
    internal :class:`SimpleModelRouter`.

    Usage::

        router = AdaptiveModelRouter()
        await router.register_provider("openai", backend, models=["gpt-4o"])
        router.set_profile("gpt-4o", ModelCapabilityProfile(
            model="gpt-4o",
            capabilities=["code", "reasoning", "chat"],
            strengths={"code": 0.8, "reasoning": 0.9},
        ))

        model = await router.select("code", candidates=["gpt-4o", "claude-sonnet"])
        # ... call the model ...
        await router.record_outcome("gpt-4o", "code", reward=0.95)
    """

    def __init__(self) -> None:
        self._rng = random.Random()  # noqa: S311
        # (model, task_type) -> bandit arm
        self._arms: dict[tuple[str, str], _ModelArm] = {}
        # model -> capability profile
        self._profiles: dict[str, ModelCapabilityProfile] = {}
        # model -> provider name  (for routing)
        self._model_provider: dict[str, str] = {}
        # provider_name -> backend  (duck-typed LLMBackend)
        self._backends: dict[str, object] = {}
        # provider_name -> priority
        self._priorities: dict[str, int] = {}
        # model -> list of provider names
        self._model_providers: dict[str, list[str]] = {}
        # model -> ModelInfo
        self._model_info: dict[str, ModelInfo] = {}
        # provider health tracking
        self._provider_calls: dict[str, int] = {}
        self._provider_errors: dict[str, int] = {}
        self._provider_latency: dict[str, float] = {}

    # -- arm helpers -----------------------------------------------------------

    def _get_arm(self, model: str, task_type: str) -> _ModelArm:
        key = (model, task_type)
        if key not in self._arms:
            arm = _ModelArm()
            # Apply strength prior from capability profile if available
            profile = self._profiles.get(model)
            if profile and task_type in profile.strengths:
                strength = profile.strengths[task_type]
                # Map strength [0, 1] to a prior: stronger prior alpha
                arm.alpha = 1.0 + strength * 4.0
                arm.beta = 1.0 + (1.0 - strength) * 4.0
            self._arms[key] = arm
        return self._arms[key]

    # -- capability profiles ---------------------------------------------------

    def set_profile(self, model: str, profile: ModelCapabilityProfile) -> None:
        """Register or replace the capability profile for *model*."""
        self._profiles[model] = profile

    def get_profile(self, model: str) -> ModelCapabilityProfile | None:
        """Return the capability profile for *model*, or ``None``."""
        return self._profiles.get(model)

    def models_for_task(self, task_type: str) -> list[str]:
        """Return models whose capability profile includes *task_type*.

        Models without a profile are *not* included.
        """
        return [
            model
            for model, profile in self._profiles.items()
            if task_type in profile.capabilities
        ]

    # -- provider registration (mirrors SimpleModelRouter) ---------------------

    async def register_provider(
        self,
        name: str,
        backend: object,
        *,
        models: list[str],
        priority: int = 0,
    ) -> None:
        """Register a provider backend with its supported models."""
        self._backends[name] = backend
        self._priorities[name] = priority
        for model in models:
            providers = self._model_providers.setdefault(model, [])
            if name not in providers:
                providers.append(name)
            self._model_provider[model] = name
            if model not in self._model_info:
                self._model_info[model] = ModelInfo(model=model, provider=name)

    async def route(self, model: str, *, fallback: bool = True) -> object:
        """Resolve *model* to an ``LLMBackend``.

        Raises ``LookupError`` if no provider is registered.
        """
        provider_names = self._model_providers.get(model)
        if not provider_names:
            raise LookupError(f"No provider registered for model {model!r}")

        sorted_names = sorted(
            provider_names,
            key=lambda n: self._priorities.get(n, 0),
            reverse=True,
        )

        for name in sorted_names:
            if self._is_healthy(name):
                return self._backends[name]
            if not fallback:
                break

        if fallback:
            return self._backends[sorted_names[0]]

        raise LookupError(
            f"No healthy provider for model {model!r} (fallback disabled)"
        )

    async def list_available_models(self) -> list[ModelInfo]:
        """Return ``ModelInfo`` for every registered model."""
        return list(self._model_info.values())

    async def provider_health(self) -> dict[str, ProviderStatus]:
        """Return per-provider health information."""
        result: dict[str, ProviderStatus] = {}
        for name in self._backends:
            total = self._provider_calls.get(name, 0)
            errors = self._provider_errors.get(name, 0)
            latency = self._provider_latency.get(name, 0.0)
            error_rate = errors / total if total > 0 else 0.0
            avg_latency = latency / total if total > 0 else 0.0
            models = [m for m, provs in self._model_providers.items() if name in provs]
            result[name] = ProviderStatus(
                name=name,
                healthy=self._is_healthy(name),
                error_rate=error_rate,
                avg_latency_ms=avg_latency,
                models=models,
            )
        return result

    async def estimate_cost(self, model: str, tokens: int) -> float:
        """Return estimated cost in USD for *tokens* on *model*."""
        info = self._model_info.get(model)
        if info is None:
            raise LookupError(f"No model info for {model!r}")
        return info.cost_per_1k_tokens * (tokens / 1000.0)

    def set_model_info(self, model: str, info: ModelInfo) -> None:
        """Set or replace ``ModelInfo`` for a model."""
        self._model_info[model] = info

    def record_success(self, provider_name: str, *, latency_ms: float = 0.0) -> None:
        """Record a successful call to a provider."""
        self._provider_calls[provider_name] = (
            self._provider_calls.get(provider_name, 0) + 1
        )
        self._provider_latency[provider_name] = (
            self._provider_latency.get(provider_name, 0.0) + latency_ms
        )

    def record_error(self, provider_name: str, *, latency_ms: float = 0.0) -> None:
        """Record a failed call to a provider."""
        self._provider_calls[provider_name] = (
            self._provider_calls.get(provider_name, 0) + 1
        )
        self._provider_errors[provider_name] = (
            self._provider_errors.get(provider_name, 0) + 1
        )
        self._provider_latency[provider_name] = (
            self._provider_latency.get(provider_name, 0.0) + latency_ms
        )

    def _is_healthy(self, provider_name: str, *, threshold: float = 0.5) -> bool:
        total = self._provider_calls.get(provider_name, 0)
        if total == 0:
            return True
        errors = self._provider_errors.get(provider_name, 0)
        return (errors / total) < threshold

    # -- Thompson Sampling selection -------------------------------------------

    async def select(
        self,
        task_type: str,
        *,
        candidates: list[str] | None = None,
    ) -> str:
        """Select the best model for *task_type* using Thompson Sampling.

        When *candidates* is ``None``, all models whose capability profile
        includes *task_type* are considered.  If no profiles match (or no
        profiles exist), all registered models are used.

        Raises ``ValueError`` if no candidates are available.
        """
        if candidates is None:
            candidates = self.models_for_task(task_type)
            if not candidates:
                # Fall back to all registered models
                candidates = list(self._model_info.keys())

        if not candidates:
            raise ValueError(
                f"No candidate models available for task type {task_type!r}"
            )

        best_model = candidates[0]
        best_sample = -1.0

        for model in candidates:
            arm = self._get_arm(model, task_type)
            sample = self._rng.betavariate(arm.alpha, arm.beta)
            if sample > best_sample:
                best_sample = sample
                best_model = model

        return best_model

    async def record_outcome(
        self, model: str, task_type: str, *, reward: float
    ) -> None:
        """Record a reward observation for a (model, task_type) pair.

        Rewards above 0.5 increment alpha (success); rewards at or below
        0.5 increment beta (failure).
        """
        arm = self._get_arm(model, task_type)
        arm.total_trials += 1
        arm.total_reward += reward

        if reward > 0.5:
            arm.alpha += 1.0
            arm.successes += 1
        else:
            arm.beta += 1.0

    async def performance(self, *, task_type: str | None = None) -> dict[str, dict]:
        """Return performance statistics for all known (model, task_type) arms.

        The returned dict is keyed by ``"model:task_type"`` and contains
        bandit state: alpha, beta, total_trials, successes, avg_reward.

        When *task_type* is provided, only matching arms are included.
        """
        result: dict[str, dict] = {}
        for (model, tt), arm in self._arms.items():
            if task_type is not None and tt != task_type:
                continue
            avg_reward = (
                arm.total_reward / arm.total_trials if arm.total_trials > 0 else 0.0
            )
            result[f"{model}:{tt}"] = {
                "model": model,
                "task_type": tt,
                "alpha": arm.alpha,
                "beta": arm.beta,
                "total_trials": arm.total_trials,
                "successes": arm.successes,
                "avg_reward": avg_reward,
            }
        return result
