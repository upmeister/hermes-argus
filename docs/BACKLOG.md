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
| [DEBT-007](#debt-007) | Optional Netdata/GitHub treated as mandatory | Open | Define absent/configured/broken dependency expectations. |
| [DEBT-008](#debt-008) | Analyzer/Discord payload and interpreter gaps | Open | Fix collector path and independent Discord payload/imports. |
| [DEBT-009](#debt-009) | L3 analysis job is external to ANALYZER | Open | Publish a generic Hermes job/model/delivery recipe. |
| [DEBT-010](#debt-010) | Privileges, lifecycle and log rotation supplied externally | Open | Resolve dashboard, linger, sudo, network policy and rotation. |
| [DEBT-011](#debt-011) | Global cron restore/count removed | Merged; deploy pending | Deploy RR1a separately and read back preserved operator cron. |
| [DEBT-012](#debt-012) | Provisioning and notification claims need correction | Open | Describe actual external setup and verification. |
| [DEBT-013](#debt-013) | Some cron senders ignore configured proxy | Open | Load/apply the existing Telegram proxy in affected senders. |
| [DEBT-014](#debt-014) | Heartbeat credentials exposed in curl arguments | Open | Contract the bounded stdin-channel correction. |
| [DEBT-015](#debt-015) | Empty-crontab detection is locale-sensitive | Deferred | Make empty/read-error detection locale-independent. |
| [DEBT-016](#debt-016) | Heartbeat selection follows credentials | Needs decision | Choose explicit backend selection and compatibility migration. |
| [DEBT-017](#debt-017) | Native Cronping Telegram setup | Native route selected; setup pending | Publish provider-bot instructions and verify delivery separately from pings. |
| [DEBT-018](#debt-018) | Public GitHub workflow differs from production | Needs decision | Choose public timing/dedup/recovery/pin behavior. |

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

<a id="debt-008"></a>

### DEBT-008 — optional-module payload/interpreter dependencies

- **Operator impact:** Old production files mask fresh-install failures.
- **Next action / responsible roles:** Fix collector path and independent Discord payload/imports. Maintainer selects; architect scopes; builder after contract.
- **Closure evidence:** Independent module fixtures pass; missing collector is not a clean scan.
- **Release disposition:** Enabled-module prerequisite.

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

### DEBT-017 — native Cronping Telegram setup and public heartbeat guide

- **Operator impact:** accepted pings do not establish a configured Telegram route.
- **Status:** native provider-bot delivery selected on 2026-10-04; setup/delivery
  verification and public guide remain open.
- **Source:** maintainer correction and
  [heartbeat review](research/2026-10-03-heartbeat-delivery-roadmap.md).
- **Next action / responsible roles:** document Dashboard setup, Telegram bot
  activation, heartbeat integration assignment and a separately authorized
  outage/recovery test. Optional API assistance requires a later bounded task.
- **Closure evidence:** public instructions match native configuration, and
  chosen delivery is verified separately from successful pings.
- **Release disposition:** heartbeat setup/acceptance; outside frozen RR1b.
- **Boundary:** no Argus webhook or external-VPS prerequisite; no automatic
  account operations or real notification sends in this docs repair.

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

### SYNC-001 — vault synchronization repaired and regressed notes restored

- **Status:** closed after maintainer repair and documentation recovery.
- **Operator impact (historical):** stale local notes were published over newer
  server notes; three Argus documents lost current project decisions/status.
- **Source:** actual Obsidian vault configuration and Git history. A temporary
  staging folder was mistakenly treated as the local vault in the earlier
  audit. Desktop vault commit `2d76b33` regressed the card, roadmap and audit;
  the pre-regression notes were recovered from `4e835c3`.
- **Closure evidence:** recovered/current Argus notes committed through the
  real local vault, published to its GitHub remote and compared with the
  connected server vault. See [VAULT-SYNC.md](VAULT-SYNC.md).
- **Next action:** none for this finding; future updates must distinguish
  actual vault Git mirrors from temporary staging directories.
- **Release disposition:** documentation operations; neither this closure nor
  note restoration certifies an Argus runtime deployment.
