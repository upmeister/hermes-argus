# Pre-release legacy / personal-dependency audit — 2026-09-21

Status: **RESEARCH COMPLETE / RR0 PROMOTED BEFORE RR1**

## Decision

The old broad post-RC cleanup stage is too late for a subset of current debt.

Create a bounded pre-release gate:

```text
R2c.1
 -> RR0 legacy/personal-dependency reduction
 -> RR1 installer/distribution hardening
```

RR0 must be split into focused implementation slices. This document is research
authority, not permission for an omnibus refactor.

## A. Release-blocking runtime wiring

### A1. Missing historical check-integrations wrapper

`scripts/hermes-watchdog.sh` executes:

```text
$HOME_DIR/scripts/check-integrations.sh
```

No such file exists in the repository and deploy does not install it.

The current compatibility checker is deployed as:

```text
~/.hermes/scripts/health-check-integrations.sh
```

and its live compatibility surface is `--quick`.

`tests/test_watchdog_swap.py` creates a synthetic
`~/scripts/check-integrations.sh`, masking this clean-install defect.

### A2. CORE depends on default-OFF ANALYZER state

Defaults:

```text
MODULE_CORE=ON
MODULE_ANALYZER=OFF
```

Yet `hermes-watchdog.sh` and `watchdog-health.sh` treat missing/stale
`~/.hermes/logs/health-state.json` as a problem.

That file is produced by optional `health-analyzer.py --update`.

Default module truth and self-health truth therefore disagree.

### A3. Self-monitor requires optional/uninstalled components

`watchdog-health.sh` unconditionally flags:

- inactive `monitoring-bot-poller.service`, although TG_BOT defaults OFF;
- inactive system `netdata.service`, although the bootstrap does not install
  Netdata.

A public default installation can therefore self-report failure for components
it never promised to install.

### A4. GitHub heartbeat path split

Current GH module deploy provisions:

```text
~/.hermes/gh-heartbeat
```

but these live paths still inspect `~/.hermes/hermes-infra`:

- `heartbeat.sh`;
- `watchdog-health.sh`;
- `webhook.py`.

A historical maintainer directory can hide this defect in production.

## B. Personal/public defaults

### B1. Telegram smart-proxy assumption

Multiple runtime paths default to:

```text
http://127.0.0.1:8444
```

`send-monitoring-report.sh` hardcodes it.

A public install must not require an undeclared local proxy. However the current
Russian maintainer deployment may rely on the implicit default, so migration
must preserve that installation explicitly rather than silently flipping it.

### B2. Personal GitHub heartbeat default

`deploy.sh` still defaults `GITHUB_REPO` to:

```text
upmeister/hermes-infra
```

Public heartbeat ownership must be user-specific/explicit.

### B3. Old project naming

Live units remain:

```text
hermes-vps-kit-config.path
hermes-vps-kit-discover.service
```

and `webhook.py` still falls back to `~/hermes-vps-kit/config.env`.

A rename is desirable before public release, but safe unit/config migration
should be coordinated with RR1 rather than deleting old production state.

### B4. Personal bot/provenance strings

Historical personal bot handles and maintainer-specific provenance comments
remain. They are polish unless user-visible or behavior-bearing.

## C. Dead / duplicate code candidates

### C1. health-check-integrations full mode

`health-check-v2.py` explicitly supersedes hardcoded full mode.

Only quick compatibility has live callers today. After A1 is fixed, reduce this
file to the actually-owned compatibility surface or prove another full-mode
owner.

### C2. send-monitoring-report.sh

Deployed by CORE but repository reference search finds no live caller.

It also duplicates send/keyboard logic and hardcodes the smart proxy.

Strong deletion candidate after one final runtime-reference check.

### C3. legacy fallback tracker

`scripts/legacy/model-fallback-tracker.py` is explicitly replaced by
`fallback-tracker-v2.py` and is not deployed.

Archive/delete candidate.

### C4. dead deploy substitutions/settings

No current template consumer was found for:

- `HERMES_BOT_TOKEN`;
- `HERMES_BOT_UID`;
- `DMS_API_KEY`.

HTTP-webhook-era `WEBHOOK_SECRET_TOKEN` /
`NETDATA_WEBHOOK_SECRET` remnants need an explicit keep/delete decision.

## D. Historical archive — not release blockers

- `experiments/c0-runtime-bridge/` is non-production historical evidence;
- old handoffs/contracts preserve provenance;
- old dates/names in comments are cosmetic.

These can remain through RC unless they confuse active install/authority.

## E. Deliberate compatibility — do not delete casually

### E1. fallback_model

Hermes stable itself still reads legacy `fallback_model`, appended after the
canonical chain. R2c.1 must preserve bounded compatibility.

### E2. health schema v1 aliases / dual read

These are migration surfaces. Keep through v0.1 unless a separate proof shows
no supported consumer.

### E3. pre-R2a snapshots

Snapshots without the new `discovery` envelope remain intentionally readable.

## F. Additional P3 carried from R2a

Malformed community `plugin.yaml` syntax is now ignored, but a syntactically
valid non-mapping top level can still reach `meta.get()`.

This is not an R2a reopen condition; include it in RR0 ownership review.

## Suggested RR0 slices

### RR0a — default-module/runtime truth

Fix A1-A4.

Acceptance: the default module set on a clean host does not depend on
non-installed historical/optional components.

### RR0b — dead/duplicate runtime removal

Resolve C1-C4 with caller/deploy evidence.

Acceptance: every deployed script/setting has an owned live purpose.

### RR0c — public defaults and naming migration

Resolve B1-B4, coordinated with RR1 for unit/config migration.

Acceptance: public defaults contain no maintainer-specific infrastructure
assumption, while existing maintainer production has an explicit safe migration.

## Non-goal

Cleanup is not permission to redesign Argus. Each slice still needs:

```text
problem -> evidence -> smallest patch -> owning path -> explicit non-goals
```
