# Project backlog

This is the canonical repository ledger of findings, decisions and maintenance.
`DEBT-004` is a local ledger ID, **not a GitHub issue number**. Link actual
GitHub issues separately. The vault project backlog is a readable index using
these same IDs and canonical card links.

## Recording and finding a tail

Use this format here and in other projects: **plain-language problem, operator
impact, current status, source/evidence, next action and responsible role,
closure evidence, and release disposition**. An ID/link alone is insufficient.
Receipts and review reports must link the specific card with its short title.

The maintainer selects product decisions and production changes; the architect
scopes follow-up; the builder works only after contract selection. Record the
next responsible role when a task is assigned. A merged fix is not a deployed
fix: keep closure PR and deployment state separate, and retain resolved IDs.

The table is the scan view; cards retain evidence. Update table, card and vault
index together when status changes. No private credentials, commands or raw
production payloads belong in any of them.

The [roadmap](ROADMAP.md) sequences release work; the
[handoff index](handoffs/README.md) selects implementation authority.
A backlog entry is not implementation authorization.

Documentation-surface incidents use the `SYNC-*` namespace. They are not
product DEBT IDs and are tracked here because they can make an agent or
maintainer read an incomplete project state.

## All findings at a glance

| ID | Problem | Status | Next action |
| --- | --- | --- | --- |
| [DEBT-001](#debt-001) | MCP probe assumes obsolete exit codes | Deferred | Correct the comment; separately decide exit-code adoption. |
| [DEBT-002](#debt-002) | Unused deploy substitutions | Deferred | Remove only the three unused substitution lines. |
| [DEBT-003](#debt-003) | Obsolete secret-delivery comments | Deferred | Correct the named provenance comments. |
| [DEBT-004](#debt-004) | Decide whether the old full integration checker can be retired | Owner decision | Retire, migrate or deliberately retain the saved full-mode Hermes job. |
| [DEBT-005](#debt-005) | Remove old paths after all callers migrate | Partial migration | Confirm config readers and heartbeat-directory migration separately. |
| [DEBT-006](#debt-006) | Personal bot handle in docstrings | Deferred | Replace provenance handles with generic descriptions if desired. |
| [DEBT-007](#debt-007) | Optional Netdata/GitHub treated as mandatory | Resolved in RR1b source | Deploy and read back; re-entry only for a new optional surface. |
| [DEBT-008](#debt-008) | Analyzer/Discord payload and interpreter gaps | Resolved in RR1b source | Deploy and read back; re-entry for a new payload/interpreter. |
| [DEBT-009](#debt-009) | L3 analysis job is external to ANALYZER | Open | Publish a generic Hermes job/model/delivery recipe. |
| [DEBT-010](#debt-010) | Privileges, lifecycle and log rotation supplied externally | Open | Resolve dashboard, linger, sudo, network policy and rotation. |
| [DEBT-011](#debt-011) | Global cron restore/count removed | Merged; deploy pending | Deploy RR1a separately and read back preserved operator cron. |
| [DEBT-012](#debt-012) | Provisioning and notification claims need correction | Open | Describe actual external setup and verification. |
| [DEBT-013](#debt-013) | Some cron senders ignore configured proxy | Open | Load/apply the existing Telegram proxy in affected senders. |
| [DEBT-014](#debt-014) | Heartbeat credentials exposed in curl arguments | Open | Contract the bounded stdin-channel correction. |
| [DEBT-015](#debt-015) | Empty-crontab detection is locale-sensitive | Deferred | Make empty/read-error detection locale-independent. |
| [DEBT-016](#debt-016) | Heartbeat selection follows credentials | Needs decision | Choose explicit backend selection and compatibility migration. |
| [DEBT-017](#debt-017) | Cronping Telegram delivery/setup incomplete | Needs hosting decision | Plan external webhook delivery through bot Argus and public setup guide. |
| [DEBT-018](#debt-018) | Public GitHub workflow differs from production | Needs decision | Choose public timing/dedup/recovery/pin behavior. |
| [DEBT-019](#debt-019) | Analyzer UI shows stale state as healthy | Open | Maintainer selects a stale-evidence policy before RR3. |
| [DEBT-020](#debt-020) | Discord `!deepcheck` needs a TG_BOT-owned payload | Open | Maintainer decides payload ownership vs. unsupported-module reporting. |

## Open finding cards

<a id="debt-001"></a>

### DEBT-001 — adopt `hermes mcp test` exit-code semantics

- **Operator impact:** Misleading maintenance guidance.
- **Next action / responsible roles:** Correct the comment; separately decide exit-code adoption. Maintainer selects; architect scopes; builder after contract.
- **Closure evidence:** Comment/behavior match supported Hermes with compatibility probes.
- **Release disposition:** Maintenance; no current blocker.

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

<a id="debt-002"></a>

### DEBT-002 — dead deploy substitutions outside the RR0b candidate set

- **Operator impact:** Unclear mapping of settings to runtime.
- **Next action / responsible roles:** Remove only the three unused substitution lines. Maintainer selects; architect scopes; builder after contract.
- **Closure evidence:** No active template changes after marker/consumer search.
- **Release disposition:** Maintenance.

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

<a id="debt-003"></a>

### DEBT-003 — stale provenance comments on secret-delivery history

- **Operator impact:** Old documentation misdescribes setup.
- **Next action / responsible roles:** Correct the named provenance comments. Maintainer selects; architect scopes; builder after contract.
- **Closure evidence:** Comments agree with runtime readers; behavior unchanged.
- **Release disposition:** Cosmetic.

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

<a id="debt-004"></a>

### DEBT-004 ? old full integration-check mode: retire or retain?

- **Operator impact:** Deletion could break a saved job; retention leaves two full-check surfaces.
- **Next action / responsible roles:** Retire, migrate or deliberately retain the saved full-mode Hermes job. Maintainer selects; architect scopes; builder after contract.
- **Closure evidence:** Every active/saved caller has an approved disposition; --quick is preserved.
- **Release disposition:** Deferred cleanup, not a demonstrated RC blocker.

- **Status:** waiting for a maintainer ownership decision; full mode retained.
- **Source:** [RR0b / PR #63](https://github.com/upmeister/hermes-argus/pull/63),
  C1 remediation; [production dependency audit](research/2026-10-03-production-deployment-dependencies.md#legacy-follow-up-evidence).
- **What exists:** `health-check-integrations.sh` runs `--quick` for watchdog
  compatibility, but a bare invocation or `--full` runs the older expanded
  checker. Structured full checks are now owned by the v2 engine.
- **Known caller:** the audited OS-cron wrapper calls `--quick`. A disabled,
  saved Hermes `no_agent` job still references the old full checker. Deleting
  code would leave that job broken if the operator re-enables it.
- **Decision needed:** retire the saved job, migrate it to the v2 wrapper, or
  deliberately keep its full-mode support? Switching to `--quick` changes
  coverage and is not an equivalent replacement.
- **Next action:** account for active AND saved OS/Hermes schedules; record the
  maintainer's choice, then contract the corresponding small change. This
  documentation task neither deletes the mode nor edits production jobs.
- **Required boundary:** preserve `--quick`, its output/incident semantics and
  secret-safe requests. Full-mode retirement is separate from RR1a.

<a id="debt-005"></a>

### DEBT-005 — legacy personal-path read fallbacks cleanup after RR0c handoff

- **Operator impact:** Premature deletion could break current configuration/heartbeat.
- **Next action / responsible roles:** Confirm config readers and heartbeat-directory migration separately. Maintainer selects; architect scopes; builder after contract.
- **Closure evidence:** Every listed legacy reader is retired with evidence or explicitly retained.
- **Release disposition:** Compatibility follow-up.

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

- **Later heartbeat audit:** dedicated heartbeat and infra clones have been
  separated. This supersedes the earlier heartbeat-path observation; legacy
  config readers still require their own confirmation.

<a id="debt-006"></a>

### DEBT-006 — historical bot handle in module docstrings

- **Operator impact:** Personal identity remains in source only.
- **Next action / responsible roles:** Replace provenance handles with generic descriptions if desired. Maintainer selects; architect scopes; builder after contract.
- **Closure evidence:** Named docstrings cleaned; configured runtime identity unchanged.
- **Release disposition:** Cosmetic.

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

<a id="debt-007"></a>

### DEBT-007 — hidden Netdata/GitHub requirements in optional-service reporting

- **Operator impact:** Clean installs can report unwanted dependency failures.
- **Next action / responsible roles:** Define absent/configured/broken dependency expectations. Maintainer selects; architect scopes; builder after contract.
- **Closure evidence:** Unconfigured is neutral; expected broken components stay visible.
- **Release disposition:** Clean-install prerequisite.

- **Status:** RESOLVED by RR1b (source; not deployed)
- **Source:** [production dependency audit](research/2026-10-03-production-deployment-dependencies.md), D1
- **Evidence:** the quick checker required Netdata API success and a GitHub
  token unconditionally; the bot's watchdog view also reported absent Netdata
  as failed whenever Hermes exists. Conditional systemd self-health alone
  did not remove these paths.
- **Resolution:** expectation comes from host evidence already available —
  Netdata is expected when the `netdata.service` unit is installed, GitHub when
  a token is configured. Absent is neutral, expected-and-broken stays visible,
  healthy-configured output is unchanged. No new config knob, no mandatory
  Netdata. Quick-mode neutrality is silent because the watchdog turns every
  output line into a separate incident.
- **Re-entry trigger:** a new optional surface needs an expectation predicate,
  or an operator must declare Netdata expected on a host with no installed unit.
- **Scope guard honored:** no mandatory Netdata install, no v2 schema change.

<a id="debt-008"></a>

### DEBT-008 — optional-module payload/interpreter dependencies

- **Operator impact:** Old production files mask fresh-install failures.
- **Next action / responsible roles:** Fix collector path and independent Discord payload/imports. Maintainer selects; architect scopes; builder after contract.
- **Closure evidence:** Independent module fixtures pass; missing collector is not a clean scan.
- **Release disposition:** Enabled-module prerequisite.

- **Status:** RESOLVED by RR1b (source; not deployed)
- **Source:** production audit D2/D3; deploy manifests and bot imports
- **Evidence:** Analyzer expected a collector at a path its manifest did not
  install; production relied on an older copy. Discord imports `webhook.py`,
  currently deployed only by TG_BOT, and its isolated venv lacked PyYAML for
  the registry view. Bootstrap did not include python3-venv.
- **Resolution:** `collect-metrics.sh` moved to the `MODULE_ANALYZER` manifest
  at the canonical `~/.hermes/scripts/` path the consumer reads (the CORE copy
  under `~/scripts/` is gone — no second competing copy); `health-analyzer.py`
  treats a missing, non-executable, non-zero or empty collector as explicit
  failure evidence and refuses the `health-state.json` update. `webhook.py` is
  owned by a `SHARED` manifest, so Discord-only deploys get a fresh handler
  library; the venv install adds `PyYAML` and deploy verifies the unit's own
  interpreter imports what the exercised handlers need; `install.sh`
  provisions `python3-venv`.
- **Re-entry trigger:** a new module gains an internal payload or a second
  isolated interpreter; or a handler starts importing a package the deploy
  import check does not cover.
- **Scope guard honored:** bounded wiring/dependency changes, no plugin system.

<a id="debt-009"></a>

### DEBT-009 — L3 workflow setup remains external to ANALYZER

- **Operator impact:** Installing scripts does not install full L3 analysis.
- **Next action / responsible roles:** Publish a generic Hermes job/model/delivery recipe. Maintainer selects; architect scopes; builder after contract.
- **Closure evidence:** Public recipe reproduces workflow without private prompts.
- **Release disposition:** Before claiming reproducible L3.

- **Status:** RR1b documentation/setup requirement
- **Source:** production audit D3; active Hermes analysis job metadata
- **Evidence:** Argus schedules Analyzer state updates, but the analysis
  prompt and delivery job live in Hermes and are not provisioned by Argus.
- **Follow-up:** supply a generic operator recipe and declare that full L3
  analysis requires a separately configured Hermes job/model/destination.
- **Trigger:** before advertising reproducible automatic L3 monitoring.
- **Scope guard:** no automatic copying of production prompts or second
  scheduler/provider runtime.

<a id="debt-010"></a>

### DEBT-010 — host lifecycle/privilege assumptions need explicit admission

- **Operator impact:** New hosts lack declared setup or may adopt unsuitable policy.
- **Next action / responsible roles:** Resolve dashboard, linger, sudo, network policy and rotation. Maintainer selects; architect scopes; builder after contract.
- **Closure evidence:** Every selected host prerequisite has tested availability/error behavior.
- **Release disposition:** Public installer prerequisite.

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

<a id="debt-012"></a>

### DEBT-012 — external provisioning and native-alert claims need reconciliation

- **Operator impact:** Pings/API availability can be mistaken for working alerts.
- **Next action / responsible roles:** Describe actual external setup and verification. Maintainer selects; architect scopes; builder after contract.
- **Closure evidence:** Docs distinguish setup, ping acceptance and delivery.
- **Release disposition:** Setup-documentation prerequisite.

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

<a id="debt-013"></a>

### DEBT-013 — explicit Telegram proxy is not loaded by every cron sender

- **Operator impact:** Different senders can use different delivery paths.
- **Next action / responsible roles:** Load/apply the existing Telegram proxy in affected senders. Maintainer selects; architect scopes; builder after contract.
- **Closure evidence:** Direct/proxy fixtures cover affected senders with secret-safe argv.
- **Release disposition:** Configured-delivery prerequisite.

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

<a id="debt-014"></a>

### DEBT-014 — external heartbeat secret URLs remain in curl argv

- **Operator impact:** Secret URLs can appear in process listings.
- **Next action / responsible roles:** Contract the bounded stdin-channel correction. Maintainer selects; architect scopes; builder after contract.
- **Closure evidence:** Argv canary absent while unchanged ping request is delivered.
- **Release disposition:** Secret invariant; disposition before RC.

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

<a id="debt-015"></a>

### DEBT-015 — `no crontab for` detection is locale-sensitive

- **Operator impact:** Localized cron can block an otherwise valid deploy.
- **Next action / responsible roles:** Make empty/read-error detection locale-independent. Maintainer selects; architect scopes; builder after contract.
- **Closure evidence:** Empty localized cron works; actual read failure remains fail-closed.
- **Release disposition:** Portability follow-up.

- **Status:** deferred maintenance (fail-closed direction, not a false green)
- **Source:** RR1a implementation review of `reconcile_argus_cron`
- **Evidence:** an absent user crontab is recognized by the English cron
  message `no crontab for`. On a system with a localized cron (non-English
  message catalog) the same state is treated as a failed read and the deploy
  stops with a clear error — safe but noisy for that configuration.
- **Required follow-up:** switch detection to a locale-independent probe
  (for example `crontab -l </dev/null` exit-status semantics verified per
  cron implementation) in a maintenance pass.
- **Trigger:** when a localized-cron host is actually in scope, or next time
  deploy.sh cron reconciliation is touched.
- **Scope guard:** keep fail-closed behavior for genuinely failed reads.

<a id="debt-016"></a>

### DEBT-016 ? explicit heartbeat backend selection is missing

- **Operator impact:** Old credentials can unintentionally activate extra backends.
- **Next action / responsible roles:** Choose explicit backend selection and compatibility migration. Maintainer selects; architect scopes; builder after contract.
- **Closure evidence:** Selected backend set and credential failures have tested semantics.
- **Release disposition:** Heartbeat cycle; not contracted.

- **Status:** product semantics not selected.
- **Source:** [heartbeat/RR1 review](research/2026-10-03-heartbeat-delivery-roadmap.md);
  `heartbeat.sh` checks all credential sets independently.
- **Evidence:** `MODULE_GH_HEARTBEAT` controls provisioning rather than
  runtime selection. Existing credentials determine backend activation.
- **Boundary:** one backend/list/redundancy and migration need a maintainer
  decision; a redundant backend is not automatically failover.

<a id="debt-017"></a>

### DEBT-017 ? Cronping Telegram delivery and public heartbeat setup

- **Operator impact:** Account audit reports pings without Telegram notification.
- **Next action / responsible roles:** Plan external webhook delivery through bot Argus and public setup guide. Maintainer selects; architect scopes; builder after contract.
- **Closure evidence:** Independent receiver and synthetic outage/recovery evidence, with public guide.
- **Release disposition:** Requested heartbeat cycle; not implemented.

- **Status:** requested cycle; bot Argus preferred, independent hosting open.
- **Source:** later heartbeat audit and maintainer clarification;
  [discussion](research/2026-10-03-heartbeat-delivery-roadmap.md).
- **Evidence:** audit reports accepted pings but no Telegram integration.
  [Cronping](https://cronping.com/docs/integrations) offers a provider bot or
  generic webhook; the maintainer prioritizes delivery from bot Argus.
- **Boundary:** no bridge on the monitored host for full-host-loss coverage;
  no live sends, account provisioning or deployment during docs work.

<a id="debt-018"></a>

### DEBT-018 ? GitHub heartbeat public template differs from the audited workflow

- **Operator impact:** New-user template does not reproduce audited production behavior.
- **Next action / responsible roles:** Choose public timing/dedup/recovery/pin behavior. Maintainer selects; architect scopes; builder after contract.
- **Closure evidence:** Template tests/docs describe chosen public behavior and actual secret names.
- **Release disposition:** Public heartbeat acceptance.

- **Status:** supported public behavior not selected.
- **Source:** [comparison](research/2026-10-03-heartbeat-delivery-roadmap.md#public-github-template-is-not-the-production-workflow);
  `modules/gh-heartbeat/heartbeat-alert.yml`.
- **Evidence:** public template uses fifteen-minute schedule/900-second age
  threshold and repeats stale alerts; audit describes five minutes/ten minutes
  with dedup/pinning in a separate production workflow.
- **Boundary:** choose public behavior explicitly; do not copy private
  workflow/config or claim those features are already shipped.

<a id="debt-019"></a>

### DEBT-019 — Analyzer UI marks old state healthy without a freshness decision

- **Operator impact:** after collection failures, `/watchdog` can keep a green
  Analyzer line indefinitely while showing an old last-check timestamp.
- **Next action / responsible roles:** maintainer selects the desired stale
  evidence policy; architect scopes a bounded UI/consumer follow-up; builder
  only after selection.
- **Closure evidence:** an old valid Analyzer state renders neutral/stale
  instead of healthy per the selected policy; a fresh success stays healthy and
  malformed/absent state stays visible.
- **Release disposition:** does not block RR1b; decide before RR3.

- **Status:** open, outside RR1b.
- **Source:** RR1b focused review at `4dfc6ed`;
  `scripts/webhook.py` renders a check mark whenever the stored JSON is
  readable, without checking age.
- **Evidence:** RR1b deliberately preserves `health-state.json` on a failed
  collection, which makes the consumer's missing freshness decision visible.
  The timestamp itself is shown, so this is not hidden data.
- **Boundary:** do not add failed-attempt state and do not change what the
  Analyzer writes; this is a consumer acceptance decision.

<a id="debt-020"></a>

### DEBT-020 — Discord deepcheck calls a TG_BOT-owned executable

- **Operator impact:** on a fresh Discord-only deployment, `!deepcheck` has its
  shared handler but fails because `~/scripts/ai-deep-check.py` is absent.
- **Next action / responsible roles:** maintainer decides whether the Discord
  command should own that payload or report the unsupported module
  combination; architect scopes; builder after selection.
- **Closure evidence:** the chosen Discord-only deepcheck behavior is verified
  in a fresh isolated deployment, without old files or live API calls.
- **Release disposition:** not a RR1b blocker under the selected B3 payload and
  import boundary; review command completeness before RR3.

- **Status:** open, outside RR1b.
- **Source:** RR1b focused review at `4dfc6ed`; `scripts/discord-bot.py` binds
  `handle_deep_check`, `scripts/webhook.py` starts `~/scripts/ai-deep-check.py`,
  and `deploy.sh` supplies that script only through `TG_BOT_HOME_SCRIPTS`.
- **Evidence:** an isolated Discord-only deploy confirms the file is absent.
- **Boundary:** RR1b fixed ownership of the shared handler library
  (`webhook.py`) and its interpreter, not the deepcheck payload decision.

## Resolved source changes with pending deployment

<a id="debt-011"></a>

### DEBT-011 — whole-user cron count and restore violate schedule ownership

- **Status:** RESOLVED by RR1a (managed block, PR #68): the `<7` heuristic and
  the whole-crontab restore branch are removed; the saved backup file remains
  for operator use; deploy.sh is the single schedule writer.
- **Source:** production audit D4; quick checker and auto-remediation
- **Evidence (historical):** fewer than seven jobs was treated as corruption,
  and a stale full-user backup could replace the current schedule. Module
  OFF/minimal schedules and unrelated operator edits could therefore be undone.

- **Deployment status:** not deployed, per maintainer. Source closure is
  PR #68; production acceptance requires a separately authorized read-back.

## Documentation operations

<a id="sync-001"></a>

### SYNC-001 — Windows vault stage is missing the Argus project tree

- **Operator impact:** a local maintainer view can appear to have no Argus
  backlog even though the connected server vault contains it.
- **Status:** open infrastructure finding.
- **Source:** 2026-10-04 read-back of the connected Obsidian MCP vault and
  `C:\Users\covhnw\vault-stage\files`; detailed ownership is in
  [`docs/VAULT-SYNC.md`](VAULT-SYNC.md).
- **Next action / responsible role:** sync owner identifies the stage-population
  process and restores a deterministic project-tree sync; maintainer verifies
  the three required paths.
- **Closure evidence:** local stage contains the Argus card, roadmap, backlog
  index and latest selected/research pointers, with a recorded source revision
  or sync date.
- **Release disposition:** documentation operations; does not block runtime
  code, but agents must not treat the incomplete local stage as a complete
  mirror.
