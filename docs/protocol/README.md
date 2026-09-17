# Loom Protocol

## Status

This document defines the language-neutral protocol boundary for Loom. It is normative for interoperable Loom implementations; it is not a description of the Python `loom-ai` implementation.

## 1. Purpose

Loom defines a protocol for discovering and invoking capabilities supplied by implementations. Loom does not define a programming language, runtime, framework, deployment technology, or mandatory transport.

A Loom implementation may be written in Python, Java, Erlang, or another language. Multiple implementations MUST be able to participate in the same Loom landscape without sharing implementation language or framework.

## 2. Core model

A Loom participant works with four fundamental concepts:

1. **Contract**: defines the operation, inputs, outputs, semantics, version, and failure behavior.
2. **Registration**: associates an implementation of a contract with an endpoint URI and relevant protocol metadata.
3. **Discovery**: finds registrations satisfying a contract and compatibility requirements.
4. **Invocation**: sends a contract-defined request to the selected endpoint and interprets the contract-defined response.

The protocol does not require these concepts to be separate processes or services.

## 3. Contract

A contract is identified independently of implementation language and transport.

A contract defines:

- stable identity
- contract version
- operation names and semantics
- request shape
- response shape
- validation rules
- failure/error semantics
- compatibility requirements
- provenance/evidence requirements when applicable

The contract MUST NOT contain language-specific types, framework classes, vendor SDK concepts, or transport-specific assumptions.

## 4. Registration

A registration states that an implementation is available for a contract.

Conceptually:

```text
contract       = <contract identity>
version        = <contract version>
endpoint       = <URI>
capabilities   = <contract-declared capabilities>
metadata       = <non-normative registration metadata>
```

The endpoint is a URI. The protocol does not require the URI to use HTTP.

A registration MUST NOT require implementation-language metadata for interoperability.

A registry may be implemented by any suitable mechanism, including an in-process registry, file-backed registry, database, LDAP-like directory, NIS-like service, or network service. Registry technology is outside the core Loom protocol.

## 5. Discovery

Discovery resolves a contract requirement to one or more registrations.

Discovery operates on protocol concepts such as:

- contract identity
- version/compatibility
- declared capabilities
- endpoint availability
- applicable policy

Discovery MUST NOT require the caller to know the implementation language or framework.

## 6. Invocation

Invocation addresses a registered endpoint through its URI and supplies a request conforming to the selected contract.

The protocol semantics are independent of how the request is transported.

A Loom binding MAY use:

- HTTP/REST
- JMS
- another messaging protocol
- another URI-addressable transport
- in-process invocation

HTTP/REST is therefore a binding, not the Loom protocol itself.

## 7. URI and binding separation

The URI identifies the endpoint. The URI scheme identifies or selects the mechanism used to reach that endpoint.

For example:

```text
https://example/loom/worker
jms://broker/loom/worker
```

The contract semantics remain the same. A binding implementation translates the protocol operation into the mechanism represented by the URI.

## 8. Implementation neutrality

The following are intentionally outside the Loom protocol:

- programming language
- runtime
- framework
- provider SDK
- operating system
- container/runtime packaging
- registry technology
- transport implementation

`loom-ai` is one implementation of Loom. A future Java or Erlang implementation is a peer implementation, not a special extension of the protocol.

## 9. Conformance

An implementation conforms to Loom when it satisfies the normative contract semantics and binding requirements it claims to implement.

Conformance tests SHOULD exercise protocol semantics independently of implementation language. Language-specific test suites may additionally verify the implementation's local behavior.

## 10. Current Loom mapping

The current `loom-ai` codebase provides concrete Python implementations of selected Loom concepts. These implementations are evidence of conformance to contracts; they do not define the protocol itself.

The provider-neutral model boundary established in ADR 0005 is an example: `ModelProvider`, `ModelRequest`, and `ModelResponse` define a stable capability boundary, while provider adapters and execution mechanisms remain implementation concerns.

## 11. Explicit non-goals

Loom does not require:

- a central registry
- a specific service-discovery product
- HTTP/REST
- microservices for every contract
- a particular programming language
- a particular serialization format beyond what an individual binding requires

A Loom deployment may initially be entirely in-process and later distribute selected boundaries without changing the underlying contract semantics.
