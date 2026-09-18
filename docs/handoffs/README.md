# Handoffs and implementation contracts

This directory contains both active implementation contracts and historical handoffs. **Old handoff presence is not implementation authority.**

Repository `AGENTS.md` scope-control rules apply to every document here.

## Active baseline — updated 2026-09-19

Read in this order:

1. `2026-09-17-next-steps-execution-baseline.md`
2. exactly one maintainer-selected task contract.

Current selected task:

- `oa1-static-account-auth-discovery-contract.md` — **NOW / READY**

Completed:

- R1a deploy/GitHub-heartbeat secret-in-argv — **DONE / PR #29**
- R1b Telegram child-argv secret exposure — **DONE / PR #31**
- OA0 account-auth discovery research — **DONE / PR #33 / decision STATIC ONLY**

OA phase:

- OA1 generic static account-auth discovery — **NOW**
- OA2 Hermes status shadow — **CLOSED / UPSTREAM-GATED**
- OA-close acceptance — **AFTER OA1**

Queued after OA close:

- R1c demonstrated non-Telegram Authorization-header argv debt;
- R2a malformed YAML;
- R2c bounded static compatibility excluding account-auth.

Deferred:

- `r2b-gateway-liveness-contract.md` — research only until a stable external liveness seam is demonstrated.

## Current execution order

```text
R1a DONE / PR #29
R1b DONE / PR #31
OA0 DONE / PR #33 / STATIC ONLY

OA1 NOW — generic static account-auth discovery
 -> OA-close exact-main acceptance
 -> OA PHASE COMPLETE

OA2 CLOSED / UPSTREAM-GATED

then:
R1c Authorization-header argv debt
 -> R2a malformed YAML
 -> R2c bounded static discovery
 -> R3 stabilization/reduction
```

OA1 must preserve the OA0 semantic boundary:

```text
persisted credential evidence present
!= logged in
!= healthy
```

This matters because the current `health-check-v2.py` projects every
`type=oauth` entity to `ok / logged in`; OA1 must correct that adjacent
false-green path while adding generic static discovery.

## OA2 status

Do not implement or poll `GET /api/providers/oauth` now.

See:

```text
oa2-hermes-status-shadow-reopen-gate.md
```

The 2026-09-19 upstream watch found partial progress on fresh Hermes `main`,
but latest stable remains v0.21.3 and all reopen conditions are not satisfied.

## Current contracts

Current:

- `oa1-static-account-auth-discovery-contract.md`

After OA1:

- `oa-close-account-auth-acceptance-contract.md`

Closed/upstream-gated:

- `oa2-hermes-status-shadow-reopen-gate.md`

Completed/history:

- `oa0-account-auth-discovery-research-contract.md`
- `r1-secret-in-argv-contract.md`
- `r1b-telegram-secret-argv-contract.md`

Queued:

- `r2a-malformed-yaml-contract.md`
- `r2c-static-discovery-compat-contract.md`

Deferred:

- `r2b-gateway-liveness-contract.md`

## Multi-profile boundary

Multi-profile remains a separate near-term product track. OA1 may preserve
profile-compatible raw store semantics but must not implement profile discovery,
projection or alerting.

## Historical / superseded

The following remain evidence only:

- `b1b-adr0002-agent-handoff.md`
- `b1b-adr0002-implementation-contract.md`
- `c0-runtime-bridge-zcode.md`
- `c1a-shadow-bridge-agent-handoff.md`
- `c1a-shadow-bridge-implementation-contract.md`

C1a/C1b runtime-bridge productionization remains superseded.

## Agent workflow

```text
maintainer selects one active contract
 -> one implementation/research pass
 -> focused review
 -> at most one remediation by default
 -> exact-tree reread
 -> merge/decision OR blocker
```

If a second remediation is required, stop and return the exact blocker to the
maintainer unless a narrow extra remediation is explicitly authorized.

Before merge recommendation, refresh the PR description/evidence receipt so it
describes the actual exact candidate head.

If an active task conflicts with a historical handoff, the active baseline and
`AGENTS.md` win.
