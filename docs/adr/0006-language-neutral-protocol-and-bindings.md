# ADR 0006: Language-neutral Loom protocol and pluggable bindings

## Status

Accepted for implementation planning.

## Context

Loom is currently implemented in Python, but the architecture is intended to permit equivalent implementations in Java, Erlang, and other languages. Treating the Python implementation or HTTP/REST interface as the definition of Loom would make the protocol accidentally language- or transport-specific.

The architecture also needs to support endpoints reached through mechanisms such as HTTP/REST or JMS without requiring clients or the core Loom model to understand those technologies.

## Decision

Loom is defined as a language-neutral protocol and set of semantics. Implementations are conforming realizations of those contracts.

The core Loom protocol defines:

- contracts and contract versioning
- request/response semantics
- registration
- discovery
- invocation
- endpoint addressing by URI
- conformance and compatibility
- protocol-level errors
- provenance/evidence semantics where required by a contract

Transport and communication mechanisms are bindings to the Loom protocol. HTTP/REST, JMS, and other mechanisms are peers. No binding is privileged by the core protocol.

The endpoint is represented as a URI. A binding implementation resolves the URI and carries the contract operation to the endpoint.

Registry technology is also replaceable. A registry may be in-process, file-backed, database-backed, directory-backed, or networked. Loom does not require a central registry service.

`loom-ai` is one implementation of Loom. Its Python classes are not the protocol definition. Future implementations in Java, Erlang, or other languages MUST be able to conform to the same protocol without changing the protocol because of language or framework differences.

## Consequences

### Positive

- Loom contracts can be implemented in multiple languages.
- Clients depend on contracts rather than implementation language.
- HTTP/REST and JMS can coexist as endpoint bindings.
- Registry implementations can evolve independently from protocol semantics.
- In-process implementations can become remote implementations without redefining the contract.
- Conformance can be tested independently of programming language.

### Negative

- The protocol must be specified more precisely than a Python interface alone.
- Bindings require explicit compatibility rules.
- Protocol evolution must be managed independently from implementation evolution.
- A conforming implementation may require more work than simply matching a local Python API.

## Rejected alternatives

### Python defines Loom

Rejected. This would make the protocol an implementation artifact and would make future Java/Erlang implementations second-class translations.

### REST defines Loom

Rejected. HTTP/REST is a useful binding but is not the only possible endpoint mechanism.

### One mandatory central registry

Rejected. Registration and discovery are protocol concepts; the persistence/distribution mechanism is an implementation choice.

### Every interface becomes a microservice

Rejected. A contract boundary does not automatically imply a deployment boundary. Deployment boundaries should be introduced where independent lifecycle, scaling, security, runtime, or operational ownership justifies them.

## Implementation guidance

The normative protocol belongs under `docs/protocol/`.

Implementation-specific contracts belong in the Python package and corresponding tests, but must map explicitly to the protocol concepts they implement.

Bindings should be implemented behind protocol-neutral endpoint abstractions. No core contract should require a Python type, Java class, Erlang construct, HTTP server, JMS client, or vendor SDK.
