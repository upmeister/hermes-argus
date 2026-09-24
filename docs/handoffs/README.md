# Handoffs and implementation contracts

This directory contains active implementation contracts and historical
handoffs. **Old handoff presence is not implementation authority.**

Repository `AGENTS.md` scope-control rules apply to every document here.

## Active baseline — updated 2026-09-24

Read in this order:

1. `2026-09-17-next-steps-execution-baseline.md`
2. exactly one maintainer-selected task contract.

Current selected task:

- `r2c-static-discovery-compat-contract.md` — **R2c.1 NOW / READY**

Completed:

- R1a deploy/GitHub-heartbeat secret-in-argv — **DONE / PR #29**
- R1b Telegram child-argv secret exposure — **DONE / PR #31**
- R1c Authorization-header argv exposure — **DONE / PR #42**
- OA0 account-auth research — **DONE / PR #33 / STATIC ONLY**
- OA1 generic static account-auth discovery — **DONE / PR #35**
- OA1b OAuth evidence rendering — **DONE / PR #39**
- OA-close acceptance — **DONE / PR #40 / OA PHASE COMPLETE**
- R2a malformed authoritative YAML fail-safe — **DONE / PR #44**
- R2a.1 plugin metadata hardening + baseline follow-up — **DONE / PR #47**

Closed/upstream-gated:

- `oa2-hermes-status-shadow-reopen-gate.md`

## Exact current baseline

```text
Argus main = 5c38fa2381a11974d5b3691def8b5c7fa7849f81
PR #47 candidate = 25601493e9bd2986b09f55a82dbe9837843bf30c
CI #92 = success
probes = 133/133
swap tests = 8/8
candidate/main changed blobs = identical
```

## Release-oriented execution order

```text
R1c DONE
 -> R2a/R2a.1 DONE
 -> R2c.1 NOW
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
R2c.2 bounded scoped/auxiliary fallback coverage
 -> low-risk archive cleanup
```

## Current upstream authority

```text
Hermes stable = v2026.9.21 / v0.21.4
stable tag commit = d337b736aa1e8ebecfab043842d13e4a2d2f48a3
warning-source main = 35b14ad5e24137b836d5c47c21a50c6ea7aeb785
```

Stable behavior is implementation authority. Main is warning/research only.

## Current contracts

Current:

- `r2c-static-discovery-compat-contract.md` — R2c.1

Completed:

- `r2a-baseline-degradation-followup-contract.md`
- `r2a-malformed-yaml-contract.md`
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

## Role-based workflow

Contracts are agent-agnostic:

```text
Maintainer selects one contract
 -> Builder performs one implementation pass
 -> Focused reviewer performs one adversarial review
 -> at most one remediation by default
 -> Maintainer exact-head reread
 -> merge/decision OR blocker
```

A reviewer finding outside the active contract is recorded, not automatically
implemented. Before merge recommendation, refresh the PR body/evidence receipt
to the exact candidate head.
