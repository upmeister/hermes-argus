# Handoffs and implementation contracts

This directory contains active implementation contracts and historical
handoffs. **Old handoff presence is not implementation authority.**

Repository `AGENTS.md` scope-control rules apply to every document here.

## Active baseline — updated 2026-10-03

Read in this order:

1. current `docs/ROADMAP.md`;
2. [production dependency audit](../research/2026-10-03-production-deployment-dependencies.md)
   for RR1 work;
3. exactly one maintainer-selected task contract.

The dated 2026-09-17 execution baseline remains historical research, not the
current selected-task pointer.

Current selected task:

- **None selected.** RR0a/RR0b/RR0c and RR1a are complete; RR1b
  (dependency/preflight/config and module payloads) is the next slice and
  requires its own maintainer-selected contract. Planning input:
  `docs/research/2026-10-03-production-deployment-dependencies.md`.

Prepared candidate (not selected):

- `rr1b-module-runtime-truth-contract.md` — optional dependency truth and
  payload completeness; reviewer Codex; maintainer selection still required.

RR1a is merged, not deployed. Subsequent RR1 subdivisions and the requested
Cronping -> bot Argus heartbeat cycle are
[under discussion](../research/2026-10-03-heartbeat-delivery-roadmap.md).

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
- RR0a default-module/runtime truth — **DONE / PR #51**
- RR0b dead/duplicate runtime removal — **DONE / PR #63**
- RR0c public defaults/naming migration — **DONE / PR #65**
- RR1a managed cron ownership — **DONE / PR #68**
- MCP disabled-server reporting — **DONE / PR #59**
- canonical gateway matcher maintenance fix — **DONE / PR #60**

Closed/upstream-gated:

- `oa2-hermes-status-shadow-reopen-gate.md`

## Implementation baseline recorded 2026-10-03

```text
Argus main = 9aaf0a5a094d0ac950f4a49c2b89fcea9d07a280 (merge of PR #68, 2026-10-03)
R2c.1 merged = 7d6fcf8940c26625103c78004fe69ba65fab4ccb (PR #49, 2026-09-24)
local-services merged = 21cd7edb5bd503e3d5ce01d872b13e73f4720c2d (PR #56, 2026-09-27)
RR0a merged = f1f9a77659b349a10983fb330badef9ef52b5996 (PR #51, 2026-09-24)
MCP disabled-server merged = 3551b08 (PR #59, 2026-10-02)
gateway matcher merged = b39b256 (PR #60, 2026-10-02)
RR0b merged = 72a801f (PR #63, 2026-10-02; implementation 4fa5473, remediation 78fea55)
RR0c merged = 2588581 (PR #65, 2026-10-02; implementation e271317, remediation 0823885)
RR1a merged = 9aaf0a5 (PR #68, 2026-10-03; implementation e14df0f, remediations 88c8237 / 8679158)
```

This records the latest implementation at the audit, not a promise that GitHub
HEAD will remain unchanged. Resolve current `origin/main` before starting code.

R2c.1 is confirmed against Hermes stable v0.21.5 — see the 2026-10-01 upstream
watch. `get_fallback_chain()` is unchanged; the static inventory requires no
rework.

## Release-oriented execution order

```text
R1c DONE
 -> R2a/R2a.1 DONE
 -> R2c.1 DONE
 -> RR0a DONE / PR #51
 -> RR0b DONE / PR #63
 -> RR0c DONE / PR #65
 -> RR1a managed cron ownership                 DONE / PR #68
 -> RR1b dependency/preflight/config and module payloads  (candidate prepared)
 -> RR1c versioned installation/update
 -> RR1d bounded uninstall/resource migration
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

- None selected. RR1b is the next slice and needs its own contract.

Prepared candidate:

- `rr1b-module-runtime-truth-contract.md` — not selected; production risk high;
  maintainer merge after reviewer PASS.

RR1b/c/d require later focused contracts. Planning input:
[production deployment dependencies](../research/2026-10-03-production-deployment-dependencies.md).

Completed:

- `r2c-static-discovery-compat-contract.md` — R2c.1 (PR #49)
- `rr0a-default-module-runtime-truth-contract.md` — RR0a (PR #51)
- `rr0b-dead-runtime-removal-contract.md` — RR0b (PR #63; reviewer Codex,
  verdict PASS-TO-MAINTAINER after one remediation pass)
- `rr0c-public-defaults-naming-migration-contract.md` — RR0c (PR #65)
- `rr1a-managed-cron-contract.md` — RR1a (PR #68; reviewer Codex,
  verdict PASS-TO-MAINTAINER after two bounded remediation passes)
- `mcp-disabled-server-compat-contract.md` — MCP disabled-server handling
  (PR #59)
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

Non-blocking findings and deferred maintenance are tracked in
[`docs/BACKLOG.md`](../BACKLOG.md).

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

Reviewer assignment is per-contract. **Codex** is the current project
reviewer/architect; a contract may name another reviewer when the maintainer
chooses one. Merge authority follows the production-risk classification in
`AGENTS.md`, and deployment always remains a separate maintainer action.
