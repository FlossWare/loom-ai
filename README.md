# loom-ai

**loom-ai defines AI-domain contracts and semantics built on the language-neutral Loom protocol.**

The canonical Loom protocol and semantic specification live in FlossWare/loom. This repository is the **domain-contract layer** for AI. It defines AI-specific contracts, concepts, and semantics without making Python the architectural authority.

Concrete Python realizations belong in FlossWare/loom-ai-python. Future Java, Erlang, or other implementations are peers:

    loom
      |
      +-- loom-python
      |
      +-- loom-ai
            |
            +-- loom-ai-python
            +-- loom-ai-java
            +-- loom-ai-erlang

The repository family follows FlossWare engineering standard ADR-0024.

## AI domain model

The AI layer defines concepts such as:

    Loom contracts
         |
         v
    AI-domain contracts
         |
         +-- Intent
         +-- Worker
         +-- Arbiter
         +-- model-related contracts
         +-- execution evidence
         +-- AI-specific results

An implementation of these contracts is not part of this repository merely because the implementation happens to be written in Python.

## Boundary

Loom owns language-neutral protocol semantics.

loom-ai owns AI-domain contracts and semantics.

loom-ai-python owns Python implementations of those AI-domain contracts.

Provider SDKs, credentials, model routing, and other capabilities remain behind their own explicit contracts and repositories where appropriate.

## Architectural rule

AI-specific behavior must not redefine generic Loom semantics. When an AI concept requires a generic protocol capability, the AI contract builds on Loom rather than copying or specializing the Loom protocol itself.
