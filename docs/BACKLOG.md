# Project backlog

This file is the repository's durable backlog for known technical debt,
deferred maintenance, and follow-up work discovered during implementation or
review. The repository remains the source of truth; a GitHub issue is an
optional working handle for a task, not a second canonical backlog.

## How to use it

Add a finding as soon as a builder or reviewer identifies it and the finding is
outside the active contract or intentionally deferred. Each entry records the
source, the reason it is deferred, and the trigger that should bring it back.

Use a GitHub issue when a task needs discussion, an implementation PR, or a
visible external report. Link the issue here when one exists. Close or update
the backlog entry in the same change that changes its status.

Release gates and active implementation contracts stay in
[`docs/ROADMAP.md`](ROADMAP.md) and
[`docs/handoffs/README.md`](handoffs/README.md). Do not duplicate their
acceptance criteria here.

## Open items

### DEBT-001 — adopt `hermes mcp test` exit-code semantics

- **Status:** deferred maintenance
- **Source:** PR #59 focused review; Hermes stable v0.21.5
- **Evidence:** the `check_mcp` comment still describes the exit code as
  always zero, while supported Hermes returns `0` for connected, `1` for a
  connection failure, and `3` when the server is missing.
- **Required follow-up:** correct the stale comment and decide whether Argus
  should use the exit code as an additional signal while preserving the
  established output-marker compatibility path.
- **Trigger:** schedule as a separate maintenance task before changing
  `check_mcp`, or when Hermes changes the command contract again.
- **Scope guard:** do not fold this into MCP disabled-server handling or an
  unrelated health-check change.

### DEBT-002 — dead deploy substitutions outside the RR0b candidate set

- **Status:** deferred maintenance
- **Source:** RR0b C4 owner-matrix search (marker → template-consumer mapping)
- **Evidence:** the deploy sed script still substitutes `@BREAKER_MAX@`,
  `@DMS_SNITCH@` and `@WATCHDOG_BOT_TOKEN@`, but no template in `scripts/`,
  `modules/` or `config/` contains those markers. The settings themselves are
  alive through runtime `.env` readers (`webhook.py` for `BREAKER_MAX`,
  `heartbeat.sh` and the registry kit for `DMS_SNITCH`, watchdog/alert
  scripts for `WATCHDOG_BOT_TOKEN`) — only the substitution lines are dead.
- **Required follow-up:** drop the three `printf 's/@…@/…/g'` lines from
  `deploy.sh` in a dedicated maintenance pass.
- **Trigger:** next deploy.sh maintenance task; not RR0c/RR1 by default.
- **Scope guard:** RR0b was scoped to `HERMES_BOT_TOKEN`, `HERMES_BOT_UID`,
  `DMS_API_KEY` and the webhook/Netdata remnants; these three substitutions
  were deliberately left in place.

### DEBT-003 — stale provenance comments on secret-delivery history

- **Status:** deferred maintenance (cosmetic)
- **Source:** RR0b C4 owner-matrix search
- **Evidence:** `scripts/gen-registry.py` header still says "DMS_* live as
  deploy-time substitutions inside heartbeat.sh", while `heartbeat.sh` reads
  `DMS_SNITCH` from the runtime environment and no template carries a `@DMS_…@`
  marker. The `scripts/webhook.py` top-of-file comment still names
  `NETDATA_WEBHOOK_SECRET`, which has no deploy, generator or runtime surface
  anywhere in the repository.
- **Required follow-up:** correct both comments in a docs-level maintenance
  pass; no behavior change expected.
- **Trigger:** whenever those files are next touched for a functional change.
- **Scope guard:** comment-only; do not use it to reopen RR0b deletions.

### DEBT-004 — health-check-integrations full mode: uncertain owner retained

- **Status:** retained in place (contract rule: uncertainty is not a deletion
  signal); removal deferred
- **Source:** RR0b C1 owner-matrix; review #1 on PR #63 (REMEDIATE)
- **Evidence:** the full mode has no in-repository caller (no cron line, no
  systemd unit, no manifest entry invokes it; the deployed integrations
  schedule owns the structured full check via `health-check-v2-wrapper.sh`),
  but the script header documents a historical operator entry point —
  "Hermes cron daily no_agent" (2026-08-20) — on the maintainer's personal
  host, which cannot be verified or disproved from the repository.
- **Required follow-up:** maintainer verifies the live crontab on the
  production host. If no bare invocation of
  `~/.hermes/scripts/health-check-integrations.sh` exists, remove the full
  mode (plus its full-only helpers) in a dedicated pass and drop this entry;
  if it exists, either point that cron at `--quick` or at the v2 wrapper and
  then remove the surface.
- **Trigger:** maintainer production verification, or the RR0c/RR1 window.
- **Scope guard:** until verified, the full mode stays exactly as shipped;
  do not shrink or redirect it silently.

### DEBT-005 — legacy personal-path read fallbacks cleanup after RR0c handoff

- **Status:** intentional bounded compatibility, deferred cleanup
- **Source:** RR0c B3/B4 evidence gathering (PR #65 review window)
- **Evidence:** the runtime still reads the maintainer's historical paths as
  bounded compatibility fallbacks, each only when the path exists:
  `~/hermes-vps-kit/config.env` as the second candidate in `webhook.py`
  (module-flag/settings heuristics) and `local_services_check.py`
  `config_env_paths()`, and the `~/.hermes/hermes-infra` heartbeat-directory
  fallback in `heartbeat.sh`, `watchdog-health.sh`, `webhook.py` (RR0a
  compat). On a public install none of these paths exist, so the fallbacks
  are inert.
- **Required follow-up:** after the maintainer confirms the RR0c unit/config
  handoff is complete on production, drop the legacy candidates in a single
  maintenance pass.
- **Trigger:** maintainer confirmation that the production handoff finished.
- **Scope guard:** do not remove the fallbacks while the legacy production
  layout may still be live.

### DEBT-006 — historical bot handle in module docstrings

- **Status:** cosmetic polish, out of RR0c scope by contract
- **Source:** RR0c B4 search
- **Evidence:** `webhook.py` and `monitoring-bot-poller.py` module docstrings
  name the maintainer's historical monitoring bot handle. The handle is
  provenance only: bot identity at runtime comes from `WATCHDOG_BOT_TOKEN`,
  and no message/command surface prints it.
- **Required follow-up:** replace with a generic product description in a
  docs-level pass if the maintainer wants the handle out of the public
  source.
- **Trigger:** any RR1/RR2 docs or i18n pass touching those modules.
- **Scope guard:** comment-only; no behavior change.
