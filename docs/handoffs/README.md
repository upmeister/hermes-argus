# Handoffs and implementation contracts

This directory contains both active implementation contracts and historical
handoffs. **Old handoff presence is not implementation authority.**

Repository `AGENTS.md` scope-control rules apply to every document here.

## Active baseline — updated 2026-09-19

Read in this order:

1. `2026-09-17-next-steps-execution-baseline.md`
2. exactly one maintainer-selected task contract.

Current selected task:

- `oa-close-account-auth-acceptance-contract.md` — **NOW / READY**

Completed:

- R1a deploy/GitHub-heartbeat secret-in-argv — **DONE / PR #29**
- R1b Telegram child-argv secret exposure — **DONE / PR #31**
- OA0 account-auth research — **DONE / PR #33 / STATIC ONLY**
- OA1 generic static account-auth discovery — **DONE / PR #35**

OA phase:

```text
OA0 DONE
OA1 DONE
OA2 CLOSED / UPSTREAM-GATED

OA-close NOW
 -> OA PHASE COMPLETE
 -> R1c
```

Queued after successful OA close:

- R1c demonstrated non-Telegram Authorization-header argv debt;
- R2a malformed YAML;
- R2c bounded static compatibility excluding account-auth;
- R3 stabilization/reduction.

Deferred:

- `r2b-gateway-liveness-contract.md`

## OA1 accepted baseline

```text
reviewed PR head = abb7ceecd805fe4c4ffc1f90248a562be88de051
merged main      = cfa6c535518e3d3ad9b78c20d442335f48e84fd6
PR #35           = merged
CI #61           = success
```

The four changed file blobs are identical between reviewed PR head and merged
main.

OA1 preserves the required semantic boundary:

```text
persisted credential evidence present
!= logged in
!= healthy
```

Static account-auth entities now project to a non-green skipped result; Copilot
PAT-only remains unconfigured.

## OA2 status

OA2 is **not** part of closeout implementation.

See:

```text
oa2-hermes-status-shadow-reopen-gate.md
```

Latest stable remains Hermes v0.21.3 / `v2026.9.14`. Fresh main is
`03c9fc892f5cf3f2e02aa4a4888a30ae292d256d`; no account-auth surface relevant
to the reopen gate changed since the previous watch. OA2 remains closed.

## Current contracts

Current:

- `oa-close-account-auth-acceptance-contract.md`

Completed:

- `oa1-static-account-auth-discovery-contract.md`
- `oa0-account-auth-discovery-research-contract.md`
- R1a/R1b contracts

Closed/upstream-gated:

- `oa2-hermes-status-shadow-reopen-gate.md`

Queued:

- `r2a-malformed-yaml-contract.md`
- `r2c-static-discovery-compat-contract.md`

Deferred:

- `r2b-gateway-liveness-contract.md`

## Workflow

```text
one selected contract
 -> one implementation/research/acceptance pass
 -> one focused review
 -> at most one remediation by default
 -> exact-tree reread
 -> merge/decision OR blocker
```

OA-close is expected to be docs/acceptance only. If it discovers a functional
OA1 regression, stop and return it to the maintainer instead of silently
turning closeout into another implementation PR.

Before merge recommendation, refresh the PR body/evidence receipt to the exact
candidate head.
