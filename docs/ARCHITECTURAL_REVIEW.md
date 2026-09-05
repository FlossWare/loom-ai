# Cumulative Architectural, Implementation, and Dogfood-Readiness Review: `FlossWare/loom-ai`

## 1. Executive Summary

`FlossWare/loom-ai` provides a solid, dependency-free core orchestration substrate built around provider-neutral contracts (`typing.Protocol` with structural subtyping across 81 contracts). The internal execution engine (`ExecutionEngine` with DAG topological wave scheduling) and multi-model consensus engine (`ConsensusEngine` with worker fan-out and arbiter synthesis) are implemented as functional code—not merely documented. The unit and conformance test suite is healthy (2,368 passing tests).

However, **Loom is not yet ready to participate in the FlossWare end-to-end dogfood flow.**

The primary blocker identified was a critical contract mismatch at the canonical chunk boundary (`FlossWare/chunking`). Loom's `Chunk` dataclass lacked required metadata, character/byte offset, token-count, and provenance fields, and Loom's REST storage API (`POST /knowledge/chunks/store`) destructively overwritten chunk IDs and sequence indices on ingestion (`chunk-{doc_id}-{i}`). These P0 issues have been addressed in the accompanying PR changes. Additional P1 issues remain around model router integration, control-plane binding (`FlossWare/agent-setup`), and arbiter prompt safety.

---

## 2. Architecture & Implementation Assessment (Areas 1–13)

### Area 1: Overall Architecture
- **Coherence & Structure:** Loom is structured with clean boundaries between protocol contracts (`loom_ai/protocols.py`, `loom_ai/contracts_*.py`), core data models (`loom_ai/models.py`), backend implementations (`loom_ai/backends/`), and REST/CLI endpoints (`loom_ai/routers/`, `loom_ai/clients/`).
- **Separation of Responsibilities:** Core orchestration (consensus, DAG task scheduling, session persistence, MCP bridge) is properly contained in Loom.
- **Unnecessary Coupling & Duplication:**
  - *Text Chunking:* `TokenChunker` in `loom_ai/backends/knowledge.py` duplicates document chunking logic that belongs exclusively in `FlossWare/chunking`.
  - *Model Selection & Routing:* `SimpleModelRouter` and `AdaptiveModelRouter` duplicate routing policies that belong in `FlossWare/model-router`.
  - *Control-Plane Configuration:* Environment variable parsing in `loom_ai/config.py` duplicates control-plane provisioning that belongs in `FlossWare/agent-setup`.

### Area 2: Canonical Chunk Consumer Boundary
- **Field Mapping & Metadata:** `Chunk` dataclass in `loom_ai/models.py` previously defined only `id`, `document_id`, `content`, `chunk_index`, and `content_hash`. It was updated to include `token_count`, `start_offset`, `end_offset`, `metadata`, and `provenance`.
- **Identity & Sequence Integrity:** `POST /knowledge/chunks/store` in `loom_ai/routers/storage.py` previously replaced incoming chunk IDs with `f"chunk-{body.document_id}-{i}"`. It was updated to preserve incoming producer IDs and sequence indices (`sequence` or `chunk_index`).
- **Offset & Unicode Semantics:** Offsets specify character code point indices in Python `str` and match the `FlossWare/chunking` contract.

### Area 3: Agent Architecture
- **Implementation Status:** `ExecutionEngine` (`loom_ai/execution.py`) and `ConsensusEngine` (`loom_ai/consensus.py`) are fully implemented and verified by tests.
- **DAG Wave Scheduling:** `ExecutionEngine` performs topological sorting and executes independent tasks concurrently in waves via `asyncio.gather`. On task failure, transitive downstream dependents are automatically marked `CANCELLED`.
- **Worker Isolation:** Workers execute as async coroutines in the same Python process space; process/container isolation is absent.

### Area 4: Model / Provider Abstraction
- **Router Surface:** Loom defines `ModelRouter` in `contracts_core.py` and ships `SimpleModelRouter` and `AdaptiveModelRouter`.
- **Endpoint Coupling:** `ConsensusEngine` delegates model invocations to a single `LLMBackend` instance (`LOOM_LLM_BASE_URL`). Fanning out to multiple models passes the `model` identifier in the request payload to a single endpoint, forcing downstream deployments to rely on an external proxy (like LiteLLM) rather than resolving provider endpoints dynamically through `FlossWare/model-router`.

### Area 5: Configuration and Profiles
- **Environment Precedence:** Configured via `LoomConfig.from_env()`, which reads `LOOM_*` environment variables.
- **Control-Plane Surface:** Lacks a structured adapter or contract interface to receive configuration profiles, rate limits, or policies directly from `FlossWare/agent-setup`.

### Area 6: CLI / API Compatibility
- **Public Surface:** CLI (`loom`), TUI (`loom-tui`), REST server (`server.py`), and Python SDK (`loom_ai/clients`).
- **Endpoints:** REST endpoints wrap storage, LLM chat, consensus, search, secrets, queue, and graph functions.

### Area 7: Reliability and Resilience
- **Error Sanitization:** `ConsensusEngine._sanitize_error` and `loom_ai/backends/security.py` strip sensitive provider data and raw HTTP bodies from error messages.
- **Resilience Mechanisms:** Includes `CircuitBreaker` (`resilience.py`) and exponential backoff with jitter (`retry.py`). Unbounded queues in `MemoryQueueBackend` present memory growth risks under heavy ingestion.

### Area 8: Testing and Dogfood Coverage
- **Coverage Quality:** 2,377 tests pass across unit, conformance, and protocol contract suites.
- **Contract Verification:** Added 9 integration tests in `tests/test_canonical_chunk_integration.py` proving canonical chunk preservation, metadata/provenance roundtripping, sequence integrity, and REST API behavior.

### Area 9: Cross-Repository Integration
- **`FlossWare/scraping`:** Compatible; basic `Document` fields align.
- **`FlossWare/chunking`:** Preserved canonical contract with updated `Chunk` model and REST router.
- **`FlossWare/model-router`:** Partially decoupled; Loom duplicates routing backends rather than consuming `model-router` contracts.
- **`FlossWare/agent-setup`:** Isolated; configuration is limited to raw environment variables.
- **`FlossWare/curses-tui`:** Fixed direct-reference build setting (`allow-direct-references = true`) in `pyproject.toml`.

### Area 10: Performance and Scalability
- **DAG Execution:** Efficient async wave scheduling via `asyncio.gather`.
- **In-Memory Search:** `InMemoryKnowledgePipeline.query` performs linear O(N) scans over all stored chunks for keyword matching.

### Area 11: Security
- **Secret Scrubbing:** Raw HTTP response bodies and API tokens are stripped from logs and client errors.
- **Prompt Injection Surface:** `ConsensusEngine.synthesize()` interpolates raw worker response strings directly into arbiter prompts without structural XML/JSON delimiters or prompt escaping.

### Area 12: Documentation vs Implementation
- **Accuracy:** Core stdlib-only claims in README are accurate.
- **Gaps:** Documentation does not warn that `POST /knowledge/chunks/store` previously overwrote chunk IDs and stripped metadata.

### Area 13: Repository Scope & Refactoring
- **Deprecations:** `TokenChunker` in `loom_ai/backends/knowledge.py` should be deprecated and removed; text chunking belongs strictly in `FlossWare/chunking`.

---

## 3. Detailed P0 / P1 / P2 Findings

### Finding 1 (P0) — FIXED in PR #927
- **Severity:** P0
- **Short title:** Destructive Overwriting of Chunk Identity, Index, and Hash in Storage REST Endpoint
- **Exact file/path:** `loom_ai/routers/storage.py`
- **Relevant symbol/function/class:** `store_chunks` route handler function
- **Status:** **REMEDIATED.** Updated `_extract_chunk_object` to preserve incoming `id`, `sequence`/`chunk_index`, `content_hash`, `start_offset`, `end_offset`, `token_count`, `metadata`, and `provenance`.

---

### Finding 2 (P0) — FIXED in PR #927
- **Severity:** P0
- **Short title:** Canonical Chunk Data Model Mismatch Lacks Offset, Token Count, Metadata, and Provenance Fields
- **Exact file/path:** `loom_ai/models.py`
- **Relevant symbol/function/class:** `Chunk` dataclass
- **Status:** **REMEDIATED.** Expanded `Chunk` dataclass with `token_count`, `start_offset`, `end_offset`, `metadata`, `provenance`, and `@property sequence`.

---

### Finding 3 (P1) — FIXED in PR #927
- **Severity:** P1
- **Short title:** Direct References setting missing in `pyproject.toml` for `flossware-loom-ai[tui]`
- **Exact file/path:** `pyproject.toml`
- **Relevant symbol/function/class:** `[tool.hatch.metadata]`
- **Status:** **REMEDIATED.** Added `allow-direct-references = true` under `[tool.hatch.metadata]`.

---

### Finding 4 (P1)
- **Severity:** P1
- **Short title:** Unescaped Prompt Injection Vulnerability in Multi-Model Arbiter Synthesis
- **Exact file/path:** `loom_ai/consensus.py` and `loom_ai/prompts.py`
- **Relevant symbol/function/class:** `ConsensusEngine.synthesize` and `build_arbiter_messages`
- **What is wrong:** `ConsensusEngine.synthesize()` aggregates raw worker model responses into `worker_dicts` and formats them directly into system and user prompts via `build_arbiter_messages()`. Untrusted worker outputs and ingested document content are interpolated as plain string text without structural delimiters or XML/JSON escaping.
- **Why it matters:** An attacker who injects prompt override instructions into an ingested document can jailbreak or hijack the arbiter model's synthesis logic during multi-model consensus rounds.
- **Recommended remediation:** Implement structural encapsulation (e.g. XML tags or JSON encapsulation) in `loom_ai/prompts.py`.

---

### Finding 5 (P1)
- **Severity:** P1
- **Short title:** `ConsensusEngine` Hard-Coupled to Single HTTP Endpoint Base URL
- **Exact file/path:** `loom_ai/consensus.py` and `loom_ai/backends/http_llm.py`
- **Relevant symbol/function/class:** `ConsensusEngine.__init__` and `HttpLLMBackend.chat`
- **What is wrong:** `ConsensusEngine` accepts a single `LLMBackend` instance. When `ConsensusEngine.gather` fans out calls to a list of models `["gemini-3.5-flash", "llama-3.3-70b"]`, it passes each `model_id` in the JSON body payload sent to `LOOM_LLM_BASE_URL`.
- **Why it matters:** Loom cannot natively route consensus requests across multiple distinct model providers without placing an external proxy server (like LiteLLM) in front.
- **Recommended remediation:** Refactor `ConsensusEngine` to accept a `ModelRouter` interface to resolve model endpoints dynamically.

---

### Finding 6 (P1)
- **Severity:** P1
- **Short title:** Lack of `FlossWare/agent-setup` Control-Plane Integration Surface
- **Exact file/path:** `loom_ai/config.py`
- **Relevant symbol/function/class:** `LoomConfig.from_env`
- **What is wrong:** `LoomConfig.from_env()` reads environment variables directly with no formal adapter or contract interface to receive configuration profiles or policies from `FlossWare/agent-setup`.
- **Recommended remediation:** Define a clean control-plane profile binding interface in `loom_ai/config.py`.

---

## 4. Dogfood Qualification Assessment

1. **Can the current repository be installed from a clean environment?**
   - **Yes:** Editable build metadata and package installation succeed cleanly.
2. **Can the documented CLI actually be executed?**
   - **Yes:** Commands such as `loom health`, `loom chat`, `loom docs list`, and `loom secrets list` execute correctly.
3. **Can it consume canonical chunks from "FlossWare/chunking"?**
   - **Yes:** `POST /knowledge/chunks/store` preserves incoming chunk IDs, sequences, offsets, token counts, metadata, and provenance without destructive overwriting.
4. **Can it select and use the intended model/provider abstraction?**
   - **Partial:** `ConsensusEngine` couples multi-model fan-out to a single `LOOM_LLM_BASE_URL` endpoint, requiring a proxy for multi-provider routing.
5. **Can the worker/arbiter workflow execute end-to-end?**
   - **Yes:** When `LOOM_LLM_BASE_URL` is configured, `ConsensusEngine.synthesize()` executes worker fan-out and arbiter synthesis end-to-end.
6. **Are failures handled predictably?**
   - **Yes:** Partial failures in consensus return successful worker responses, and DAG task failures propagate cancellation predictably.
7. **Are the critical paths covered by executable tests?**
   - **Yes:** 2,377 passing unit and integration tests cover protocol contracts, storage roundtrips, and execution engines.

---

## 5. Overall Verdict

**`B / FIX BEFORE DOGFOOD`**

*Rationale:* FlossWare/loom-ai possesses an exceptionally well-structured, dependency-free core with comprehensive unit test coverage (2,377 passing tests) and a solid DAG execution and consensus engine. The P0 canonical chunk producer-consumer contract issues (chunk ID/index overwriting, missing metadata/offset fields) have been fully remediated in PR #927. Remaining P1 items (model router integration, control-plane binding, arbiter prompt injection protection) should be addressed prior to full production dogfood deployment.
