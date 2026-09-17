# 2026-09-17 next-steps execution baseline

Status: **ACTIVE IMPLEMENTATION BASELINE**

This document translates the stabilization roadmap into bounded repository work. It is deliberately narrower than a product roadmap: agents may implement only the named task currently assigned by the maintainer.

## Architecture invariant

```text
Hermes owns runtime truth.
Argus observes externally, verifies independently where useful, and makes failures loud.
```

Prefer, in order:

1. stable persisted/runtime status owned by Hermes;
2. static user-visible configuration/state files;
3. stable Hermes CLI output where no machine-readable interface exists;
4. log events already required for Argus's product behavior.

Do not introduce a Hermes runtime-import bridge to make discovery more complete.

## Execution order

```text
R1a deploy secret-in-argv
 -> R1b active notification secret-in-argv
 -> R2a malformed YAML degradation
 -> R2b gateway liveness from gateway_state.json
 -> R2c canonical fallback/static discovery drift
 -> R2d credential-pool/OAuth gap audit (research first)
 -> R2e registry scope clarification
 -> R3 cleanup/stabilization
```

Multi-profile support is intentionally separate from this sequence. It is near-term product work, but must not widen these fixes.

## Task ownership map

| Task | Primary owner path | Allowed adjacent paths |
|---|---|---|
| R1a deploy argv | `deploy.sh` | `tests/probes.py` only as needed |
| R1b notification argv | active notifier scripts named by the task | `tests/probes.py`; no shared framework unless separately approved |
| R2a malformed YAML | `scripts/integration-discover.py` | wrapper/tests only if required to preserve current reporting |
| R2b gateway liveness | `scripts/gateway-liveness.sh` | tests only; no Hermes imports |
| R2c fallback/static inventory | `scripts/integration-discover.py` | `scripts/fallback-tracker-v2.py` only if a demonstrated log-marker compatibility bug exists |
| R2d auth-pool audit | research/docs first | implementation requires a new maintainer decision |
| R2e registry semantics | comments/docs + generator wording | no registry architecture rewrite |

## Global non-goals

The following are NOT implied by any task in this baseline:

- C1/C1a/C1b runtime bridge revival;
- provider/plugin execution for discovery;
- credential resolution or token refresh during discovery;
- historical Hermes revision pinning;
- integrity/sandbox/worktree/interpreter verification;
- generalized notification transport framework;
- generalized adapter framework;
- multi-profile implementation;
- support for every Hermes auxiliary model role;
- replacing all static discovery with Hermes internal APIs.

## Required agent loop

```text
one assigned contract
 -> one implementation pass
 -> focused tests
 -> one focused adversarial review
 -> at most one remediation pass
 -> exact committed/staged tree reread
 -> merge recommendation OR blocker to maintainer
```

A reviewer finding outside the assigned contract is recorded as a finding. It does not authorize fixing it.

## Stop conditions

Stop and return to the maintainer if the patch requires:

- a new subsystem;
- a new dependency;
- a new persistent state format;
- changes outside the named owner surface beyond tests/docs;
- a second remediation cycle;
- hundreds of lines for a local bug;
- execution/import of Hermes internals;
- a new security boundary;
- redesign of notification, discovery, or health architecture.

## Evidence rule

Every implementation PR must state:

```text
problem -> evidence -> smallest patch -> preserved behavior -> explicit non-goals
```

Tests should prove the bug and the intended boundary, not enumerate speculative attacks unrelated to the contract.

## Canonical task contracts

- `r1-secret-in-argv-contract.md`
- `r2a-malformed-yaml-contract.md`
- `r2b-gateway-liveness-contract.md`
- `r2c-static-discovery-compat-contract.md`

The maintainer must explicitly select one before implementation begins.
