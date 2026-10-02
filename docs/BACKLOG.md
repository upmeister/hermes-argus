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

- **2026-10-03 observation:** the OS cron wrapper delegates to `--quick`, but
  a disabled Hermes `no_agent` job still references the full checker. Saved
  Hermes jobs must be included in the ownership decision; the absence of an
  active OS-cron invocation is not sufficient deletion evidence.

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

- **2026-10-03 observation:** the canonical discovery watcher is active and
  the legacy watcher is absent, but heartbeat still uses its legacy Git
  directory. Unit handoff completion alone does not close the path debt.

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

### DEBT-007 — hidden Netdata/GitHub requirements in optional-service reporting

- **Status:** RR1b clean-install prerequisite
- **Source:** [production dependency audit](research/2026-10-03-production-deployment-dependencies.md), D1
- **Evidence:** the quick checker requires Netdata API success and a GitHub
  token unconditionally; the bot's watchdog view also reports absent Netdata
  as failed whenever Hermes exists. Conditional systemd self-health alone
  did not remove these paths.
- **Follow-up:** define expectation-aware reporting for optional dependencies;
  preserve failures when a component is explicitly expected/configured.
- **Trigger:** RR1b dependency contract; required before RR3 default install.
- **Scope guard:** no mandatory Netdata install or unrelated v2 schema change.

### DEBT-008 — optional-module payload/interpreter dependencies

- **Status:** RR1b clean-install prerequisite
- **Source:** production audit D2/D3; deploy manifests and bot imports
- **Evidence:** Analyzer expects a collector at a path its manifest does not
  install; production relies on an older copy. Discord imports `webhook.py`,
  currently deployed only by TG_BOT, and its isolated venv lacks PyYAML for
  the registry view. Bootstrap does not include python3-venv.
- **Follow-up:** make each enabled module supply its actual internal payload
  and check imports under the interpreter that will run it. Missing/failed
  collector execution must not look like a clean issue scan.
- **Trigger:** RR1b optional-module fixture acceptance.
- **Scope guard:** bounded wiring/dependency changes, no general plugin system.

### DEBT-009 — L3 workflow setup remains external to ANALYZER

- **Status:** RR1b documentation/setup requirement
- **Source:** production audit D3; active Hermes analysis job metadata
- **Evidence:** Argus schedules Analyzer state updates, but the analysis
  prompt and delivery job live in Hermes and are not provisioned by Argus.
- **Follow-up:** supply a generic operator recipe and declare that full L3
  analysis requires a separately configured Hermes job/model/destination.
- **Trigger:** before advertising reproducible automatic L3 monitoring.
- **Scope guard:** no automatic copying of production prompts or second
  scheduler/provider runtime.

### DEBT-010 — host lifecycle/privilege assumptions need explicit admission

- **Status:** RR1b deployment requirement
- **Source:** production audit D5 and ownership map
- **Evidence:** production separately supplies logrotate, linger and passwordless
  sudo. CORE assumes dashboard availability and includes a DNS/routing guard
  reflecting personal network policy; deploy does not establish these owners.
- **Follow-up:** document/preflight the selected module's privileges, dashboard
  activation and user-manager persistence; provide bounded Argus log rotation
  and an explicit network-guard applicability decision for public hosts.
- **Trigger:** RR1b; no public clean-install readiness claim before disposition.
- **Scope guard:** no global sudo grants, host-network redesign or application
  backup installation by default.

### DEBT-011 — whole-user cron count and restore violate schedule ownership

- **Status:** selected RR1a scope
- **Source:** production audit D4; quick checker and auto-remediation
- **Evidence:** fewer than seven jobs is treated as corruption, and a stale
  full-user backup can replace the current schedule. Module OFF/minimal
  schedules and unrelated operator edits can therefore be undone.
- **Follow-up:** retire the count heuristic and whole-crontab restore alongside
  the managed block; preserve saved backups for operator use.
- **Trigger:** [RR1a contract](handoffs/rr1a-managed-cron-contract.md).
- **Scope guard:** no recurring scheduler repair framework or new state schema.

### DEBT-012 — external provisioning and native-alert claims need reconciliation

- **Status:** optional setup/documentation follow-up
- **Source:** production audit; Netdata notification and heartbeat paths
- **Evidence:** no direct Netdata Telegram setup was found in the inspected
  config/runtime, despite historical comments describing it. Cronping client
  comments describe Management API auto-provisioning absent from deploy.
- **Follow-up:** document the actual optional setup steps; direct Netdata
  delivery needs separate configuration and a maintainer-authorized send test.
  Describe Cronping as operator-provisioned until implementation is contracted.
- **Trigger:** RR1b operator setup documentation and the next authorized
  production notification verification.
- **Scope guard:** no send test, account creation or credential migration during
  the read-only audit or RR1a.

### DEBT-013 — explicit Telegram proxy is not loaded by every cron sender

- **Status:** RR1b delivery/config prerequisite
- **Source:** production audit D6; gateway/dashboard liveness and weekly updates
- **Evidence:** liveness reads bot/chat from `.env` but only inherits
  `TELEGRAM_PROXY`; generated cron does not source it. Weekly updates load
  `.env` but do not apply that explicit proxy option.
- **Follow-up:** make the operator's configured delivery path reach every
  existing caller; preserve direct mode and credential-safe process arguments.
- **Trigger:** RR1b runtime configuration/delivery acceptance.
- **Scope guard:** local existing senders only; no new proxy implementation or
  unapproved production notification tests.

### DEBT-014 — external heartbeat secret URLs remain in curl argv

- **Status:** separate secret-handling maintenance; release disposition required
- **Source:** production audit D6; `heartbeat.sh` Cronping and DMS backends
- **Evidence:** token-bearing ping URLs are passed as curl arguments, unlike
  the existing stdin configuration pattern used for Telegram.
- **Follow-up:** contract a bounded stdin-channel correction preserving ping
  semantics and add an argv canary check.
- **Trigger:** before claiming the process-argument secret invariant for all
  heartbeat backends or publishing the first RC.
- **Scope guard:** no credential rotation, vendor/account provisioning or RR1a
  transport changes.
