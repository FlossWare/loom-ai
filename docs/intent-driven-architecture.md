# Loom Intent-Driven Architecture

Loom is a runtime for turning declarative intent into verified changes in state.

The core architectural model is:

> **Humans describe desired outcomes and constraints. Loom interprets those descriptions, determines how they can be achieved, executes the required capabilities, and verifies the result.**

The implementation mechanisms are deliberately hidden behind stable contracts. The contract describes the relationship between intent, execution state, capabilities, decisions, and outcome; implementations are free to choose whatever execution strategy satisfies that contract.

## Core responsibilities

| Capability | Responsibility |
|---|---|
| **Intent** | Describes the desired outcome. |
| **Arbiter** | Interprets the Intent and determines what needs to happen. |
| **Workers** | Provide executable capabilities. |
| **Strategies** | Determine how choices are made. |
| **Knowledge** | Gives the system reusable understanding. |
| **Model Gateway** | Provides reasoning capabilities. |
| **Evaluation** | Determines whether the desired outcome was actually achieved. |
| **Evidence** | Establishes what actually happened. |
| **Checkpointing** | Preserves the evolving state. |
| **Human interruption** | Lets the human modify the description when the system's interpretation diverges. |
| **Adaptive selection** | Lets the machinery improve how it accomplishes future Intents. |

## The resulting control loop

```text
                 Human
                   |
                   v
                Intent
                   |
                   v
                Arbiter
                   |
          interprets / plans
                   |
        +----------+----------+
        |          |          |
        v          v          v
     Worker     Worker     Worker
        |          |          |
        +----------+----------+
                   |
                   v
              State change
                   |
          +--------+--------+
          |                 |
          v                 v
       Evidence         Evaluation
          |                 |
          +--------+--------+
                   |
                   v
              Desired outcome?
              /             \
            yes              no
             |                |
             v                v
          complete       revise / retry /
                           replan / escalate
                                |
                                +-------> Arbiter

Knowledge, Strategies, Model Gateway, and Adaptive Selection
support the loop without becoming the Intent itself.

Checkpointing preserves the evolving execution state.
Human interruption can modify the Intent when interpretation diverges.
```

## Architectural principle

Loom separates **what is wanted** from **how it is accomplished**.

Intent is semantic rather than procedural. It should describe the desired result, requirements, constraints, and acceptance criteria without prematurely prescribing the execution mechanism.

The Arbiter is responsible for interpreting that description in context. It may construct a task graph, select Workers, invoke Strategies, consult Knowledge, use the Model Gateway for reasoning, and replan when evidence shows that its interpretation or execution was insufficient.

Workers are capabilities, not prescribed pipeline stages. An Arbiter may compose Workers recursively, and a Worker may itself be an Arbiter implementation. Fix, retry, review, verification, and iteration are therefore ordinary execution graphs rather than separate architectural primitives.

## Declarative boundary

The important boundary is not whether an implementation uses procedural code internally. It inevitably will.

The boundary is what the system exposes:

```text
semantic description
        |
        v
       Loom
        |
        +--> interpretation
        +--> capability selection
        +--> execution
        +--> observation
        +--> evaluation
        +--> adaptation
        |
        v
verified outcome
```

A consumer should be able to describe **what should be true** without needing to prescribe every operation required to make it true.

This is the same architectural distinction Loom applies throughout the system: stable contracts describe meaning and relationships; replaceable implementations provide mechanisms.

## Why these capabilities are separate

These responsibilities should remain distinct even when one implementation happens to combine them:

- **Intent** establishes the desired outcome.
- **Arbiter** establishes an executable interpretation of that outcome.
- **Workers** execute capabilities.
- **Strategies** choose among alternatives.
- **Knowledge** supplies reusable information from previous work and observation.
- **Model Gateway** supplies model/reasoning capability without making a particular provider or model an architectural identity.
- **Evidence** records observable execution facts.
- **Evaluation** judges whether the outcome satisfies the acceptance criteria.
- **Checkpointing** makes execution recoverable and replayable.
- **Human interruption** provides an authoritative correction when interpretation diverges from human intent.
- **Adaptive selection** improves future choices from accumulated outcomes.

Hard constraints such as authorization, policy, safety, resource feasibility, and explicit budgets remain authoritative. Learned strategies and adaptive selection improve choices only within the feasible set.

## A useful mental model

Loom can be understood as:

```text
Intent       = what should be true
Arbiter      = what needs to happen
Workers      = what can make things happen
Strategies   = how alternatives are chosen
Knowledge    = what we already understand
Model Gateway= reasoning capability
Evidence     = what happened
Evaluation   = did it work?
Checkpoint   = where are we now?
Human        = authoritative correction
Adaptation   = how can we do better next time?
```

The system therefore forms a closed engineering loop rather than a fixed procedural pipeline:

```text
Intent -> Interpretation -> Execution -> Evidence -> Evaluation
   ^                                                |
   |                                                |
   +---- Human correction / Knowledge / Adaptation -+
```

The goal is not to make AI blindly execute a human-authored procedure. The goal is to make the system capable of turning a meaningful description of a desired outcome into a concrete, observable, verifiable result.
