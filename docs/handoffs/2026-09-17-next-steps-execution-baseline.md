# 2026-09-17 next-steps execution baseline

Status: **ACTIVE IMPLEMENTATION BASELINE — UPDATED 2026-09-18**

This document translates the stabilization roadmap into bounded repository work. It is deliberately narrower than a product roadmap: agents may implement only the named task currently assigned by the maintainer.

## Architecture invariant

```text
Hermes owns runtime truth.
Argus observes externally, verifies independently where useful, and makes failures loud.
```

Prefer, in order:

1. stable persisted/runtime status owned by Hermes when its semantics are proven;
2. static user-visible configuration/state files;
3. stable Hermes CLI output where no machine-readable interface exists;
4. log events already required for Argus's product behavior.

Do not introduce a Hermes runtime-import bridge to make discovery more complete.

A proposed upstream seam must be verified against actual upstream/production semantics before it becomes monitoring authority. The deferred `gateway_state.json.updated_at` liveness idea is the current example: the persisted field exists, but production/upstream evidence proved it is not the always-advancing heartbeat the earlier plan assumed.

## Current execution order

```text
R1a deploy secret-in-argv                     DONE / merged PR #29
 -> R1b active shell Telegram secret-in-argv  NEXT
 -> R2a malformed YAML degradation
 -> R2c bounded static discovery compatibility
 -> R3 cleanup/stabilization
```

Deferred:

```text
R2b gateway liveness redesign — research only until a stable external seam is proven
```

Multi-profile support is intentionally separate from this sequence. It is near-term product work, but must not widen these fixes.

## Task ownership map

| Task | Status | Primary owner path | Allowed adjacent paths |
|---|---|---|---|
| R1a deploy argv | DONE | `deploy.sh` | no follow-up without demonstrated regression |
| R1b notification argv | NEXT | active shell notifier scripts proven to leak token into child argv | `tests/probes.py`; docs; no shared framework unless separately approved |
| R2a malformed YAML | AFTER R1b | `scripts/integration-discover.py` | wrapper/tests only if required to preserve current reporting |
| R2b gateway liveness | DEFERRED | research only | no implementation contract active |
| R2c fallback/static inventory | AFTER R2a | `scripts/integration-discover.py` | registry docs/generator wording; fallback tracker only for a separately demonstrated log-marker break |
| R2c auth-pool audit | research/evidence first | docs/current static structures | implementation requires a demonstrated current gap |
| R3 reduction | later | actual dead/duplicate paths | deletion/simplification preferred |

## Current selected contract

The next implementation contract is:

```text
docs/handoffs/r1b-telegram-secret-argv-contract.md
```

The older `r1-secret-in-argv-contract.md` remains the parent R1 record. R1a is complete; use the dedicated R1b contract for new implementation/review decisions.

## Global non-goals

The following are NOT implied by any task in this baseline:

- C1/C1a/C1b runtime bridge revival;
- provider/plugin execution for discovery;
- credential resolution or token refresh during discovery;
- historical Hermes revision pinning;
- integrity/sandbox/worktree/interpreter verification;
- generalized notification transport framework;
- generalized adapter framework;
- multi-profile implementation inside R1/R2;
- support for every Hermes auxiliary model role;
- replacing all static discovery with Hermes internal APIs;
- treating `gateway_state.json.updated_at` freshness as a liveness contract without new evidence.

## Required agent loop

```text
one assigned contract
 -> one implementation pass
 -> focused tests
 -> one focused adversarial review
 -> at most one remediation pass by default
 -> exact committed/staged tree reread
 -> merge recommendation OR blocker to maintainer
```

A reviewer finding outside the assigned contract is recorded as a finding. It does not authorize fixing it.

If an additional remediation is genuinely required after the normal budget, STOP and request a maintainer decision with the exact blocker. A maintainer may explicitly approve a narrow extra remediation; do not interpret one approval as a permanent relaxation of the rule.

## Stop conditions

Stop and return to the maintainer if the patch requires:

- a new subsystem;
- a new dependency;
- a new persistent state format;
- changes outside the named owner surface beyond focused tests/docs;
- a second remediation cycle without explicit approval;
- hundreds of lines for a local bug unless the duplicated current owner surface itself justifies it;
- execution/import of Hermes internals;
- a new security boundary;
- redesign of notification, discovery, or health architecture.

## Evidence rule

Every implementation PR must state:

```text
problem -> evidence -> smallest patch -> preserved behavior -> explicit non-goals
```

Tests should prove the bug, the real compatibility seam and the intended boundary. Prefer a small negative/mutation control that proves a test can catch regression over a large speculative attack matrix.

Before merge recommendation, refresh the PR body/evidence receipt so it describes the exact candidate head after remediation. Do not leave superseded implementation details or stale test counts as the primary PR summary.

## Canonical task contracts

Active/next:

- `r1b-telegram-secret-argv-contract.md`
- `r2a-malformed-yaml-contract.md`
- `r2c-static-discovery-compat-contract.md`

Deferred/history:

- `r1-secret-in-argv-contract.md` — parent R1 record; R1a complete, R1b split out
- `r2b-gateway-liveness-contract.md` — implementation direction deferred after contrary production/upstream evidence

The maintainer must explicitly select one active contract before implementation begins.
