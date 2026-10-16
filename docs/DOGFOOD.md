# Loom AI contract conformance

The Loom AI contract repository defines language-neutral semantics and conformance expectations. Executable dogfood belongs to language-specific implementation repositories.

## Contract-repository validation

This repository's CI validates the contract artifacts themselves:

- JSON conformance fixtures are syntactically valid.
- The conformance documentation and normative architecture documents are present.
- The repository boundary documentation continues to identify the AI layer as language-neutral.

The executable Python dogfood, package build, runtime tests, and HTTP/server qualification live in `FlossWare/loom-ai-python`.

## Python implementation dogfood

For the current Python realization, use the dogfood entry points in `loom-ai-python`. They exercise the implementation against the AI-domain contracts defined here.

The Python implementation is not the authority for the meaning of Intent, Worker, Arbiter, Result, Evidence, or ModelProvider. Those semantics are defined in this repository and realized by language-specific repositories.

## External-agent qualification status (#949)

**Status: not yet qualified.** The generic MCP adapter is implemented in
[loom-ai-python](https://github.com/FlossWare/loom-ai-python/blob/main/scripts/loom_mcp_server.py)
and maps client tools to Loom's public HTTP boundary. Its submit, observe,
continue, and cancellation behavior is covered by implementation tests.
The durable process-boundary qualification is tracked separately in #1010.

The real external-client qualification uses
[dogfood-crush-mcp-real.py](https://github.com/FlossWare/loom-ai-python/blob/main/scripts/dogfood-crush-mcp-real.py)
against a fresh clone of this repository. It requires:

- the Crush executable to be installed and a model provider configured for it;
- the Python environment used by the MCP command to have the project's MCP dependency;
- a durable Loom server profile with an execution state store;
- a fresh Crush session that performs the real repository edit through generic
  MCP and then receives the persisted verification result and evidence.

Run the harness from a configured `loom-ai-python` checkout:

```sh
python scripts/dogfood-crush-mcp-real.py --timeout-seconds 900
```

The `--expect-failure` option qualifies the negative path, where verification
must remain failed rather than being reported as success. The default timeout
bounds the agent run; it does not turn a timeout into a successful qualification.

Unit tests, HTTP smoke tests, and process-boundary tests do not by themselves
satisfy #949. Do not mark the external-agent path qualified until a fresh Crush
session completes the real task and the execution identity, verification
outcome, evidence, and provenance are inspected. The latest recorded live
attempt was blocked because Crush had no configured model provider.

## What conformance means

Conformance is about observable behavior and semantic compatibility, not a particular programming language, package layout, framework, or private implementation detail.

No private chain-of-thought or other hidden reasoning is part of the conformance contract.
