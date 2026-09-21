# Handoffs and implementation contracts

This directory contains active implementation contracts and historical
handoffs. **Old handoff presence is not implementation authority.**

Repository `AGENTS.md` scope-control rules apply to every document here.

## Active baseline — updated 2026-09-21

Read in this order:

1. `2026-09-17-next-steps-execution-baseline.md`
2. exactly one maintainer-selected task contract.

Current selected task:

- `r2a-baseline-degradation-followup-contract.md` — **NOW / READY**

Completed:

- R1a deploy/GitHub-heartbeat secret-in-argv — **DONE / PR #29**
- R1b Telegram child-argv secret exposure — **DONE / PR #31**
- R1c Authorization-header argv exposure — **DONE / PR #42**
- OA0 account-auth research — **DONE / PR #33 / STATIC ONLY**
- OA1 generic static account-auth discovery — **DONE / PR #35**
- OA1b OAuth evidence rendering — **DONE / PR #39**
- OA-close acceptance — **DONE / PR #40 / OA PHASE COMPLETE**

Closed/upstream-gated:

- `oa2-hermes-status-shadow-reopen-gate.md`

## R1c accepted baseline

```text
contract baseline = 96149309dba4b5b539ba6f111e375355b2ab4cfd
candidate head    = b477d2bbd4d892b3fee97dd188110d4c7bbff94e
merged main       = 133931a8242de0e61cecace5f75905bf63615383
CI #81            = success
probes            = 115 pass / 0 fail
swap tests        = 8 pass / 0 fail
```

All four changed blobs are identical between candidate and merged main.
The final Pytna remediation changed only `tests/probes.py` and strengthened the
artifact/capture boundary; production code was unchanged.

## Release-oriented execution order

```text
R1c DONE
 -> R2a baseline-degradation follow-up NOW
 -> R2c.1 fallback_providers compatibility PREPARED / HOLD
 -> RR0 legacy/personal-dependency reduction
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
warning-source main = 5171ea18dc4b699e14f0092388be326dc4fc81ab
```

## Current contracts

Current:

- `r2a-baseline-degradation-followup-contract.md`

R2a base contract:

- `r2a-malformed-yaml-contract.md`

Prepared / held:

- `r2c-static-discovery-compat-contract.md` (R2c.1 before RC; R2c.2 after)

Completed:

- `r1c-authorization-header-argv-contract.md`
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
implemented. Before merge recommendation, refresh the PR body/evidence receipt
to the exact candidate head.
