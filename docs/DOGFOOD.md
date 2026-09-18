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

## What conformance means

Conformance is about observable behavior and semantic compatibility, not a particular programming language, package layout, framework, or private implementation detail.

No private chain-of-thought or other hidden reasoning is part of the conformance contract.
