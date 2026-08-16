"""Prompt-cache policy backend for loom-ai.

Provides ``PromptCachePolicy``, a zero-dependency implementation of the
:class:`~loom_ai.contracts_phase3.CachePolicy` protocol.  It adds
provider-specific cache-control hints to message lists and tracks
hit/miss statistics via content hashing.

Only the standard library is required.
"""

from __future__ import annotations

import hashlib
import json
import threading

from loom_ai.models_phase3 import CacheStats


def _content_hash(messages: list[dict]) -> str:
    """Return a deterministic SHA-256 hex digest for *messages*.

    The messages are serialised with sorted keys so that logically
    identical payloads always produce the same hash regardless of
    dict insertion order.
    """
    serialised = json.dumps(messages, sort_keys=True, default=str)
    return hashlib.sha256(serialised.encode()).hexdigest()


class PromptCachePolicy:
    """Adds provider-specific cache hints and tracks cache statistics.

    Satisfies :class:`~loom_ai.contracts_phase3.CachePolicy` via
    structural subtyping.  Thread-safe via a single lock.

    Cache-hit detection works by hashing the full message list: if the
    same content hash has been seen before, it counts as a hit;
    otherwise it is a miss.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._seen_hashes: set[str] = set()
        self._hits: int = 0
        self._misses: int = 0

    # -- CachePolicy protocol -----------------------------------------------

    def apply_cache_hints(self, messages: list[dict], *, provider: str) -> list[dict]:
        """Annotate *messages* with cache-control hints for *provider*.

        - **anthropic**: adds ``cache_control: {"type": "ephemeral"}`` to
          every system message.
        - **openai**: returned unchanged (OpenAI manages caching
          server-side).
        - **unknown providers**: returned unchanged.

        A shallow copy of the list is always returned so the caller's
        original is never mutated.
        """
        content_hash = _content_hash(messages)

        with self._lock:
            if content_hash in self._seen_hashes:
                self._hits += 1
            else:
                self._seen_hashes.add(content_hash)
                self._misses += 1

        annotated = _apply_provider_hints(messages, provider)
        return annotated

    async def cache_stats(self) -> CacheStats:
        """Return current cache utilization statistics."""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0.0
            return CacheStats(
                hits=self._hits,
                misses=self._misses,
                hit_rate=hit_rate,
                tokens_saved=0,
                cost_saved=0.0,
            )


# ── provider-specific hint helpers ────────────────────────────────────────


def _apply_provider_hints(messages: list[dict], provider: str) -> list[dict]:
    """Dispatch to the correct hint-application function for *provider*."""
    if provider == "anthropic":
        return _apply_anthropic_hints(messages)
    # openai and unknown providers: return a shallow copy, no modifications
    return list(messages)


def _apply_anthropic_hints(messages: list[dict]) -> list[dict]:
    """Add ``cache_control`` to system messages for the Anthropic API."""
    result: list[dict] = []
    for msg in messages:
        if msg.get("role") == "system":
            annotated = {**msg, "cache_control": {"type": "ephemeral"}}
            result.append(annotated)
        else:
            result.append(msg)
    return result
