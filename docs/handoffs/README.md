# Handoffs and implementation contracts

This directory contains active implementation contracts and historical
handoffs. **Old handoff presence is not implementation authority.**

Repository `AGENTS.md` scope-control rules apply to every document here.

## Active baseline — updated 2026-10-01

Read in this order:

1. `2026-09-17-next-steps-execution-baseline.md`
2. exactly one maintainer-selected task contract.

Current selected task:

- **none** — R2c.1 is complete; the next release gate is RR0, whose contract is
  not yet selected.

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
- R2c.1 canonical fallback_providers inventory — **DONE / PR #49**

Closed/upstream-gated:

- `oa2-hermes-status-shadow-reopen-gate.md`

## Exact current baseline

```text
Argus main = a58cfcdaadea094281c9aa1e459d7b4bf76f9032
R2c.1 merged = 7d6fcf8940c26625103c78004fe69ba65fab4ccb (PR #49, 2026-09-24)
local-services merged = 21cd7edb5bd503e3d5ce01d872b13e73f4720c2d (PR #56, 2026-09-27)
```

R2c.1 is confirmed against Hermes stable v0.21.5 — see the 2026-10-01 upstream
watch. `get_fallback_chain()` is unchanged; the static inventory requires no
rework.

## Release-oriented execution order

```text
R1c DONE
 -> R2a/R2a.1 DONE
 -> R2c.1 DONE
 -> RR0 legacy/personal-dependency reduction      <-- CURRENT GATE
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
      (now a stable seam — see the 2026-10-01 upstream watch)
 -> low-risk archive cleanup
```

## Current upstream authority

```text
Hermes stable = v2026.9.24 / v0.21.5
stable tag commit = f97608f178d1ffeca59860195ab7da295f7c8e5f
previous warning-source main = 35b14ad5e24137b836d5c47c21a50c6ea7aeb785
```

Stable behavior is implementation authority. Main is warning/research only.

Upstream watches: `docs/research/2026-10-01-hermes-upstream-watch.md` (current)
and `docs/research/2026-09-24-hermes-upstream-watch.md` (superseded). Argus'
dependency-on-Hermes list is `docs/research/hermes-argus-seams.md`.

## Current contracts

Current:

- **none selected.** R2c.1 completed; RR0 is the next gate and awaits a
  maintainer-selected contract.

Completed:

- `r2c-static-discovery-compat-contract.md` — R2c.1 (PR #49)
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

Reviewer assignment is per-contract. The default focused reviewer on the Peetna
MCP is **not** currently in effect; a contract names its reviewer explicitly
until further notice.
