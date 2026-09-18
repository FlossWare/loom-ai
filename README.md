# loom-ai

**`loom-ai` defines the AI-domain contracts and semantics built on the language-neutral Loom protocol.**

The repository layering is:

    loom
      |
      +-- loom-python
      |
      +-- loom-ai
             |
             +-- loom-ai-python

- `loom` defines the language-neutral Loom protocol and semantic contract.
- `loom-python` implements the foundational Loom contract in Python.
- `loom-ai` defines AI-domain contracts and semantics.
- `loom-ai-python` implements those AI-domain contracts in Python.

Python is not part of the AI-domain contract. Future implementations such as
`loom-ai-java` and `loom-ai-erlang` are peers of `loom-ai-python`.

## Contract ownership

`loom-ai` owns the language-neutral semantics for AI-domain concepts including
Intent, Worker, Arbiter, model-related contracts, and AI execution behavior.

AI-specific behavior may extend the Loom execution model, but it must not redefine
or contradict generic Loom semantics. Generic protocol semantics remain
authoritative in `FlossWare/loom`.

## Implementation boundary

Concrete Python code belongs in `FlossWare/loom-ai-python`.

This repository intentionally does not define a Python package, runtime entry
point, Python-specific transport binding, or Python implementation API. Those are
implementation concerns owned by the language-specific repositories.

The model-provider boundary established by this domain remains provider-neutral.
Provider SDKs, credentials, model routing, budgets, caching, evaluation,
optimization strategies, and other reusable capabilities remain separate
capabilities rather than becoming implicit responsibilities of this contract
repository.

## Conformance

AI-domain implementations must conform to both the generic Loom contract and the
AI-domain contracts defined here. A language implementation must be replaceable
without changing the meaning of the AI-domain contract.

See FlossWare engineering standard ADR-0024 for the contract-centric repository
naming and layering convention.
