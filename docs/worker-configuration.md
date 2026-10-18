# Worker Configuration Contract 0.1

## Status and scope

This document defines a language-neutral declarative configuration for an AI-domain Worker. It is a configuration contract, not a new Agent abstraction or an execution engine. From Loom's perspective, a configured component remains a Worker; an Arbiter is also a Worker when it satisfies the Worker contract.

The normative structural schema is [`schemas/worker-configuration-0.1.json`](../schemas/worker-configuration-0.1.json). Implementations MUST validate a configuration against that schema before activation and MUST separately resolve and authorize every referenced capability.

## Separation of concerns

- `worker_id` is the stable Worker identity; `purpose` describes its responsibility.
- `model_gateway.gateway_ref` and `selection_ref` select a logical gateway and gateway-owned selection policy. They do not identify a provider SDK, account, credential, or direct endpoint.
- `instructions` guide the Worker. They do not override policy or grant capabilities.
- `tools` explicitly declare executable capability bindings. A capability appearing only in `capabilities` expresses a requirement, not permission to execute it. A tool reference is not authorization to invoke the capability.
- `capabilities` declare intended capability requirements. The runtime MUST check them against the resolved policy and available capabilities.
- `policy.policy_ref` names the applicable policy. `approval_required`, allowlists, and denylists are explicit policy inputs, not substitutes for authorization enforcement.
- `limits` bound attempts, duration, and output size. An implementation MUST fail explicitly if a requested limit cannot be enforced; it MUST NOT silently ignore a safety-relevant limit.
- `metadata` is non-sensitive annotation only.

Provider/model/account selection, credentials, endpoint routing, budgets beyond the declared execution limits, and provider-specific mechanics remain in the model gateway and surrounding capability services. Secrets MUST NOT appear in Worker configuration, metadata, output, evidence, or provenance.

## Example

```json
{
  "schema_version": "0.1",
  "worker_id": "coding-worker",
  "purpose": "Make bounded repository changes and report verifiable evidence",
  "model_gateway": {
    "gateway_ref": "default-model-gateway",
    "selection_ref": "coding-balanced"
  },
  "instructions": [
    "Inspect the repository before editing.",
    "Keep changes within the declared task scope.",
    "Report changed files and verification results without claiming unrun checks."
  ],
  "tools": [
    {"capability_ref": "repository.read", "required": true},
    {"capability_ref": "repository.edit", "required": true},
    {"capability_ref": "verification.run", "required": true}
  ],
  "capabilities": ["repository.read", "repository.edit", "verification.run"],
  "policy": {
    "policy_ref": "bounded-repository-change",
    "approval_required": true,
    "allowed_capabilities": ["repository.read", "repository.edit", "verification.run"],
    "denied_capabilities": ["credential.read", "secret.export"]
  },
  "limits": {
    "max_attempts": 2,
    "max_duration_seconds": 900,
    "max_output_bytes": 200000
  },
  "metadata": {"team": "engineering"}
}
```

## Conformance

A conforming implementation MUST demonstrate that:

1. malformed configurations and unknown fields are rejected before activation;
2. Worker purpose is independent from gateway/provider/model selection;
3. all tool and capability references are resolved and authorized before use;
4. instructions cannot override policy, capability grants, or limits;
5. required unresolved capabilities cause an explicit activation failure;
6. capability invocation requires both an explicitly configured tool and an authorized capability, plus a trusted runtime binding;
7. when effective policy requires approval, invocation fails closed unless a trusted approval authorizer approves that specific invocation;
8. attempts, duration, and output bounds are enforced or rejected explicitly;
9. effective Worker configuration and gateway selection identifiers are attributable in non-secret provenance;
10. credentials and secret values are never serialized into the configuration or Result.

Schema validation establishes structural validity only. It does not prove authorization, capability availability, or runtime enforcement; those require executable conformance tests in each implementation.


## Capability invocation boundary

A runtime MUST NOT treat a model response, a capability reference, or a caller-supplied boolean as execution authority. Before invoking a capability, it MUST verify the capability is authorized by the effective policy, verify the capability is explicitly declared as a tool for that Worker, resolve the reference through a trusted runtime binding registry, and enforce any required approval through a trusted authorizer. Missing bindings, failed authorization, failed approval, and invalid arguments MUST fail closed. Tool arguments and results must be bounded and validated by the binding or its registered input/output contract.

This contract does not prescribe a provider-specific tool-call format. Model-native tool-call parsing and the mapping from a model's requested call to this runtime boundary are separate adapter responsibilities; implementations must not infer a tool call by executing arbitrary text emitted by a model.
