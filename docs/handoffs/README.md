# Handoffs and implementation contracts

This directory contains active implementation contracts and historical
handoffs. **Old handoff presence is not implementation authority.**

Repository `AGENTS.md` scope-control rules apply to every document here.

## Active baseline — updated 2026-09-20

Read in this order:

1. `2026-09-17-next-steps-execution-baseline.md`
2. exactly one maintainer-selected task contract.

Current selected task:

- `r1c-authorization-header-argv-contract.md` — **NOW / READY**

Completed:

- R1a deploy/GitHub-heartbeat secret-in-argv — **DONE / PR #29**
- R1b Telegram child-argv secret exposure — **DONE / PR #31**
- OA0 account-auth research — **DONE / PR #33 / STATIC ONLY**
- OA1 generic static account-auth discovery — **DONE / PR #35**
- OA1b OAuth evidence rendering — **DONE / PR #39**
- OA-close acceptance — **DONE / PR #40 / OA PHASE COMPLETE**

Closed/upstream-gated:

- `oa2-hermes-status-shadow-reopen-gate.md`

## Release-oriented execution order

```text
R1c NOW
 -> R2a malformed YAML
 -> R2c.1 fallback_providers compatibility
 -> RR1 installer/dependency/managed-cron
 -> RR2 runtime i18n: en + ru
 -> RR3 release acceptance
 -> v0.1.0-rc.1
 -> soak
 -> v0.1.0
```

After the RC:

```text
R2c.2 bounded auxiliary coverage
 -> R3 reduction/stabilization
```

Deferred/separate:

- R2b gateway-liveness redesign;
- MP0-MP5 multi-profile track;
- OA2 dynamic account-status shadow.

## Current upstream authority

```text
Hermes stable = v2026.9.14 / v0.21.3
stable commit = 345cd2b057a452236de401d3534b8502a7465e8d
warning-source main = f88c6fc46e1c1c61ae8fdc0d7fb10ec8ad949aab
```

The 2026-09-20 watch found meaningful movement toward refresh-free account
observation (Codex read-only status, Nous local snapshot, xAI non-refresh
status), but OA2 remains closed because Qwen still refresh-validates, the OAuth
response still carries token previews, the required machine-auth route is
absent, and stable has not moved.

Fallback activation/restore markers and `hermes mcp test` output remain
compatible.

## Current contracts

Current:

- `r1c-authorization-header-argv-contract.md`

Queued:

- `r2a-malformed-yaml-contract.md`
- `r2c-static-discovery-compat-contract.md` (take R2c.1 before RC; R2c.2 after)

Completed:

- `oa-close-account-auth-acceptance-contract.md`
- `oa1b-oauth-evidence-rendering-contract.md`
- `oa1-static-account-auth-discovery-contract.md`
- `oa0-account-auth-discovery-research-contract.md`
- R1a/R1b contracts

Closed/upstream-gated:

- `oa2-hermes-status-shadow-reopen-gate.md`

Deferred:

- `r2b-gateway-liveness-contract.md`

## Workflow

```text
one selected contract
 -> one implementation/research pass
 -> one focused review
 -> at most one remediation by default
 -> exact-head reread
 -> merge/decision OR blocker
```

A reviewer finding outside the active contract is recorded, not automatically
implemented.

Before merge recommendation, refresh the PR body/evidence receipt to the exact
candidate head.
