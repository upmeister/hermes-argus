# Handoffs and implementation contracts

## Current programme — 2026-10-25

The maintainer selected reconnaissance steps 1–5, stopping after RR1c/RR1d,
with three implementation PRs. Start with the
[programme and delivery protocol](2026-10-25-restart-through-rr1.md).
This replaces the old RR1b active pointer. PR #75 is already merged.

| Order | Contract | State |
| --- | --- | --- |
| A | [Hermes 0.22.5 compatibility](restart-a-hermes-compatibility-contract.md) | **DONE / PR #77**, deployed 2026-10-26 at `17b3975`; Codex GO/PASS on `64eca82b` |
| B | [Delivery/evidence correctness](restart-b-delivery-evidence-contract.md) | **DONE / PR #78**, deployed 2026-10-26 at `17b3975`; Codex GO/PASS on `d396399` |
| Ops | [Production checkpoint](../DEPLOY_CHECKLIST.md#ops-receipt--2026-10-26) | **DONE**, separately authorized deploy/read-back of `17b3975`; diagnosed integration failures retained |
| C | [RR1c/d versioned lifecycle](restart-c-versioned-lifecycle-contract.md) | **IMPLEMENTED / Codex review pending** on `feat/restart-c-versioned-lifecycle`, base `5551579`; no merge/deploy yet |

Builder: maintainer-assigned coder. Focused reviewer: **Codex**.
Implementation risk: A/B medium, C high; **maintainer merge after PASS**.
One implementation pass -> focused review -> at most one remediation -> exact
candidate reread -> maintainer merge decision or blocker. No automated second
review wave. See each contract's acceptance table and the programme's receipt.

Read repository `AGENTS.md`, [ROADMAP](../ROADMAP.md), then the selected
contract. For RR1 read the [dependency audit](../research/2026-10-03-production-deployment-dependencies.md).
Old contract presence does not grant new implementation scope.

## Verified source and production baseline

- GitHub main at planning: `f433c531bff935d869e2dd75beaf2a5bfdd200d8`,
  [PR #75](https://github.com/upmeister/hermes-argus/pull/75), merged October 6.
  Main `argus-ci` [passed](https://github.com/upmeister/hermes-argus/actions/runs/37502441206).
- Refresh `origin/main` before each task; record the actual baseline.
- Read-only October 25 production inspection found PR #65 checkout `2588581`,
  matching core Python payloads, an existing marked cron block, and a modified
  quick checker. This is historical: the October 26 authorized rollout
  reconciled those artifacts at `17b3975`; see the linked Ops receipt.
- Hermes installed and latest published stable: v0.22.5 / `bf0203a`.
  Accepted stable authority since the contract A merge (PR #77): v0.22.5 /
  `bf0203a`. See the
  [current watch](../research/2026-10-25-hermes-upstream-watch.md).

## Completed source work

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
- RR1b module dependency truth and payload completeness — **DONE / PR #71; deployed and read back 2026-10-26**
- MCP disabled-server reporting — **DONE / PR #59**
- canonical gateway matcher maintenance fix — **DONE / PR #60**

- RR1b host readiness — **DONE / PR #75**, merged 2026-10-06; deployed and read back 2026-10-26

## Later and upstream-gated

After this programme: public setup/L3 recipe and unresolved release decisions,
RR2 English/Russian runtime UI, RR3 clean-install/release acceptance,
`v0.1.0-rc.1`, soak, `v0.1.0`. No tag or release is authorized here.

- R2c.2 scoped/auxiliary fallback remains post-RC.
- Multi-profile support remains separate.
- OA2 remains closed/upstream-gated; see `oa2-hermes-status-shadow-reopen-gate.md`.
- R2b remains deferred; `r2b-gateway-liveness-contract.md` records the rejected
  timestamp-freshness design, not an implementation instruction.
- Native Cronping Telegram remains selected; backend policy/setup automation
  are outside A/B/C.

All tails live in the [backlog](../BACKLOG.md); vault status and sync evidence
live in [VAULT-SYNC](../VAULT-SYNC.md). New findings require a readable card,
not an unexplained ID. A source closure is not production verification.
