# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- Gateway liveness detection no longer infers process identity from an `argv`
  substring. `hermes-watchdog.sh` and `gateway-liveness.sh` looked the gateway
  up with `pgrep -f "hermes_cli.main gateway run"`; upstream forbids that
  heuristic, and once a Hermes update switched startup to `runpy` the pattern
  stopped matching. Symptoms differed by caller: the watchdog logged repeated
  false "Gateway процесс НЕ НАЙДЕН", while `gateway-liveness.sh` was worse —
  its guard was shaped `if ! pgrep …; then exit 0`, so a non-match made the
  script exit successfully **without ever checking liveness**, silently
  disabling the safety net. Both callers now use a new helper,
  `hermes-gateway-pids.py`, which delegates to the upstream matcher
  `gateway.status.looks_like_gateway_command_line` (`pgrep` is kept only to
  narrow candidates cheaply) and filters by the current `HERMES_HOME` install.
  The helper distinguishes three outcomes — found, not found, and matcher
  unavailable (exit code 2) — and callers treat an unavailable matcher as "not
  verified", never as "dead", so a broken environment can no longer quietly
  switch the guard off. It re-execs under the Hermes venv because the cron
  `python3` cannot import `gateway`, which would otherwise make the helper
  unavailable exactly where the check is required. Regression probes cover the
  argv-substring ban, manifest presence, and the `rc=2` path.

- Align watchdog self-health with the configured module surface (RR0a): the
  default install no longer requires the optional Analyzer, Telegram bot,
  unmanaged Netdata, a historical integration-checker path, or a legacy
  heartbeat directory. Enabled module surfaces still report missing or stale
  owned state, and existing GitHub-heartbeat installations retain bounded
  legacy-directory compatibility.

- The deployer now verifies its own payload, and the installer's post-deploy
  gate follows the selected modules instead of assuming CORE (RR1b). `install.sh`
  used to run a CORE-only syntax check on `hermes-watchdog.sh` unconditionally,
  so a clean `MODULE_CORE=OFF` install probed a file the module never installs —
  printing no result and leaking a raw `No such file or directory` from bash.
  The verification now lives where the selection already exists: `deploy.sh`
  records every file it wrote from the enabled manifests and checks each one
  for unresolved `@MARKER@` placeholders and syntax before reporting success,
  failing the deploy — and therefore the install — if any of them is wrong.
  Checks cover every deployed script of every enabled module, not one
  representative per module; they never touch foreign infrastructure or
  leftovers of disabled modules that happen to live in the target directories,
  and they never consult a second copy of the module defaults. `deploy.sh`
  also no longer silently skips a manifest source missing from the repository:
  an enabled module without its payload is a failed deploy, not a successful
  one. `install.sh` confirms fail-closed that the payload check actually ran.

### Changed

- Public installs no longer inherit maintainer-specific defaults (RR0c).
  The Telegram egress proxy is explicit: with `TELEGRAM_PROXY` unset every
  component connects directly instead of silently targeting a hardcoded local
  smart proxy, and the v2 health check reports the proxy setting as
  `unconfigured` (direct access) instead of probing a personal address —
  a malformed explicit value fails loudly. The GitHub heartbeat repository
  has no default: without an explicit `GITHUB_REPO` the backend stays
  disabled. Discovery units for new installs use the canonical Argus-owned
  names (`hermes-argus-config.path`, `hermes-argus-discover.service`); a live
  legacy `hermes-vps-kit-*` watcher is never touched or auto-migrated —
  the deploy prints an operator-controlled handoff and the installer
  guarantees a single active producer. Existing maintainer production keeps
  its behavior by setting `TELEGRAM_PROXY`/`GITHUB_REPO` explicitly once (see
  `docs/DEPLOY_CHECKLIST.md`).

- RR1b B1–B4 is merged as PR #71. The module/runtime truth slice is not
  deployed yet; the next host-readiness contract covers private config,
  user-manager and Hermes preflight, network-guard applicability and bounded
  Argus log rotation.

- Optional monitoring surfaces are now expected conditionally, so a default
  install no longer reports failures for components it never promised to
  install (RR1b). The quick integration check and the bot's watchdog panel
  treat an absent Netdata agent as neutral and skip the GitHub token check
  entirely when no token is configured; both keep reporting a failure when the
  surface *is* expected — a Netdata agent that is installed but not answering,
  or a GitHub token that stops authenticating. Expectation comes from evidence
  already on the host (an installed `netdata.service` unit, a configured token)
  rather than a new configuration knob, and healthy-configured output is
  unchanged. Quick-mode neutrality is silent on purpose: the watchdog turns any
  output line into a separate incident, so an informational line would
  reintroduce the very false report this change removes.

- Enabled modules now receive their own payload and interpreter prerequisites
  (RR1b). `collect-metrics.sh` belongs to `MODULE_ANALYZER` and is installed at
  the canonical `~/.hermes/scripts/` path its only consumer reads — previously
  `MODULE_CORE` deployed a second copy under `~/scripts/` that the Analyzer
  never used, so a fresh Analyzer install depended on a stale file. A missing,
  non-executable, non-zero or empty-output collector is now explicit failure
  evidence: `health-analyzer.py` reports the collection failure, exits non-zero
  and refuses to update `health-state.json`, so absent data can no longer be
  recorded as a healthy host. `webhook.py` — the shared handler library — is
  owned by a dedicated `SHARED` manifest instead of `TG_BOT`, so a Discord-only
  install (`MODULE_DISCORD_BOT=ON`, `MODULE_TG_BOT=OFF`) gets a fresh copy
  instead of importing whatever happened to be installed; deploy also installs
  `PyYAML` into the bot's isolated venv and verifies that the interpreter the
  Discord unit actually runs can import what the exercised handlers need.
  `install.sh` additionally provisions `python3-venv`.

- Argus now owns its schedule through a single managed crontab block
  (`# BEGIN HERMES-ARGUS` / `# END HERMES-ARGUS`, RR1a). `deploy.sh`
  reconciles that block from the existing module/profile generator: enabled
  modules install their jobs, disabled ones lose them, unrelated operator
  jobs, comments and environment declarations are preserved verbatim, and
  known previously generated Argus lines are adopted once on first install
  (both absolute and `~/` path spellings, the legacy bare-`source` heartbeat
  form, and the producer-only local-services form). The manual "append these
  lines to your crontab" instruction is retired; `CRON_FILE` remains a
  proposal/diagnostic artifact only. The global "fewer than 7 crontab jobs"
  quick-check criterion and the whole-crontab restoration from
  `crontab-known-good.txt` in auto-remediation are removed: a small managed
  schedule is valid, and a stale full-user backup can no longer resurrect
  disabled Argus jobs or overwrite operator edits. Reconciliation is a
  fail-closed, lock-serialized transaction: malformed block markers, a failed
  crontab read/write, or a missing crontab utility abort the deploy with a
  clear error instead of reporting success. The heartbeat cron line now loads
  `.env` through an explicit `/bin/bash -c` (cron runs commands with `/bin/sh`,
  where bare `source` silently does nothing). Existing maintainer production
  keeps its behavior: the first managed deploy adopts the previously installed
  Argus lines and leaves every unrelated job untouched.

### Removed

- Dead and duplicate runtime surfaces (RR0b), each backed by a caller/deploy
  search: `send-monitoring-report.sh` (deployed by CORE with no live caller —
  the watchdog, gateway/dashboard liveness and the v2 wrapper own the
  established secret-safe Telegram delivery) and the legacy
  `scripts/legacy/model-fallback-tracker.py` (superseded by
  `fallback-tracker-v2.py`, whose schedule is untouched). The full mode of
  `health-check-integrations.sh` is retained for now: its only documented
  caller is a historical maintainer-personal daily cron that cannot be
  verified from the repository, so its disposition is recorded as backlog
  DEBT-004 instead of a deletion. Dead deploy substitutions
  `HERMES_BOT_TOKEN`, `HERMES_BOT_UID` and `DMS_API_KEY` are removed from
  `deploy.sh` and the config template; `WEBHOOK_SECRET_TOKEN` and
  `DMS_SNITCH` keep their live consumers.

### Added

- Opt-in `MODULE_LOCAL_SERVICES` monitoring (OFF by default): deploy now ships a
  read-only consumer alongside the topology snapshot producer, installs a single
  sequential cron job (snapshot every 5 minutes followed by the check), and
  reconciles its own crontab lines on ON→OFF so a previously hand-installed
  collector line cannot outlive the flag while unrelated operator crontab
  entries are preserved. The consumer compares an operator-authored
  `~/.config/hermes-argus/local-services.json` manifest (strict schema-1
  validation, no auto-discovery) against the cached snapshot with
  healthy/failed/unknown verdicts, alerts once after two distinct fresh
  snapshots show a configured user unit inactive/failed, treats stale, missing
  or unreadable snapshots as unknown that never recovers or escalates an alert,
  emits a deduplicated blind-monitoring diagnostic after two separate
  collection attempts, and reports through the existing Telegram delivery
  (fail-closed without `WATCHDOG_ALLOWED_USER_ID`; silence mutes delivery but
  never fabricates recovery). The Telegram bot gains a `/services` view and a
  module-gated reply-keyboard button, and toggles now re-send the reply
  keyboard after a successful deploy (the previous completion report crashed
  silently). Hosted topology (containers, listeners, addresses) never appears
  in alerts or bot output.

- Inventory the ordered Hermes `fallback_providers` chain, append unique legacy
  `fallback_model` entries, and keep route metadata sanitized. This is static
  configuration evidence, not a claim about the route used for a request.

### Fixed

- Report a deliberately disabled MCP server honestly. A server configured with
  `enabled: false` on `mcp_servers.<name>` is now tagged during discovery
  (mirroring the Hermes default-on rule: absent/null/unparseable means on) and
  is no longer probed via `hermes mcp test` — previously it surfaced as a
  false `fail` (disabled HTTP server with a dead URL) or even a false green
  (disabled stdio server with a valid command). The health report records it
  as a classified `skipped` check (`mcp_disabled_by_config`), the Telegram
  `/integrations` views render each disabled server as its own
  `⏸ <name> — отключён` line instead of folding it into the generic
  "пропущены политикой" counter, and a report whose only non-ok rows are
  disabled servers is never rendered green.

- Make the Telegram reply keyboard natively collapsible and swap the Settings
  and Maintenance positions. Remove duplicated status/monitoring buttons from
  the Maintenance action menu and stop attaching action keyboards to automatic
  watchdog alerts while preserving critical-alert pinning.
- Classify Telegram updates before authorization: service messages and other
  non-action updates are silently ignored, while unauthorized commands and
  callback presses are still denied. Denial cooldown is keyed by Telegram user
  instead of callback-query id.
- Harden community plugin metadata discovery (R2a.1): a `plugin.yaml` that is
  unreadable, malformed YAML, or valid YAML with a non-mapping top level now
  skips the plugin instead of crashing discovery; a valid mapping keeps the
  existing semantics. The authoritative `config.yaml` degradation semantics
  are unaffected. Also make `--baseline` suppress only the entity diff: the
  first `ok -> degraded` discovery transition is reportable even in a
  baseline run (previously a degradation first observed via `--baseline`
  stayed operator-invisible indefinitely), while repeated identical
  degradation stays quiet and recovery remains reportable.

- Make integration discovery fail-safe against a malformed Hermes
  `config.yaml` (R2a): a syntactically invalid YAML or a valid YAML whose
  top level is not a mapping now produces an explicit degraded observation
  instead of a traceback, an empty healthy-looking inventory, or stale state
  that looks fresh. The snapshot/report carries a discovery envelope
  (`status ok|degraded`, stable `reason_code`, `attempted_at`,
  `last_good_at`); during degradation the last-good inventory is preserved
  verbatim (no false mass removals, freshness not rewritten), repeated
  identical degradation is quiet, and first degradation and recovery are
  reportable events (existing exit 0/2 contract). Both snapshot consumers
  fail closed on a degraded snapshot before any network/subprocess work:
  `health-check-v2` returns through its existing configuration-error path,
  `ai-deep-check` refuses before curl. Legacy pre-R2a snapshots without the
  envelope remain valid; raw parser error text is never surfaced (the config
  may contain secrets). The Telegram wrapper renders degradation/recovery
  human-readably; a malformed community `plugin.yaml` is skipped instead of
  crashing discovery.

- Keep Authorization values out of child-process argv in the remaining
  demonstrated owners (R1c): the integration shell checker now delivers both
  token-bearing URLs and `Authorization` headers to `curl` through the single
  stdin config channel (`curl -K -`, quoted header values — an unquoted
  `header =` value is silently dropped by real curl), and the deep-check
  helper feeds the `Authorization: Bearer` header to `curl` via stdin
  (`-H @-`). Request semantics are unchanged (URL, method, proxy, retries,
  timeouts, payloads, status parsing). The header value must still reach the
  HTTP request while never appearing in process listings.

- Discover persisted account-auth identities structurally from the Hermes
  auth store instead of a hard-coded provider roster: nested provider token
  state (`providers.<id>.tokens.*`), flat provider state with a refresh token,
  and `credential_pool.<id>[]` rows persisted with `auth_type: "oauth"` (or
  legacy rows without an auth type but with a refresh token) now produce
  `oauth:<id>` inventory entities. This closes the demonstrated false negative
  where a working OpenAI/Codex account was invisible to integration discovery.
  Provider identity comes from the store keys themselves; no credential values,
  fingerprints, labels, or expiry metadata are emitted.
- Stop reporting static auth-store evidence as a green "logged in" verdict:
  `oauth` inventory entities are now projected as `skipped` ("persisted
  credential evidence present; login/health not verified") because presence of
  persisted credentials is not proof of login or health. Copilot PAT-only
  remains `unconfigured`.
- Render static OAuth auth-evidence rows in the Telegram integration views as
  informational ("🔐 … — учётные данные обнаружены · runtime-статус не
  проверяется") instead of the generic skipped "⏸ … — пропущено": credentials
  were found, runtime login/health was intentionally not verified. The
  rendered generic-skipped count now excludes OAuth evidence rows (a separate
  neutral 🔐 count is shown), and the quick view no longer summarizes
  unverified OAuth rows as "пропущены политикой" or claims "всё в порядке"
  over them. The full view's 4000-character cap now cuts at whole lines and
  never drops or splits the OAuth evidence block or real failure/unknown
  rows (they survive complete). Canonical verdicts, report schema, and
  summary JSON are unchanged.
- Keep Telegram bot tokens out of child-process argv in every active shell and
  Python notifier: token-bearing URLs are delivered to `curl` via stdin config
  (`curl -K -`) instead of being expanded into the command line. Request
  wiring (proxy, timeouts, payload, retries, response parsing) is unchanged.
- Keep deployment secret values out of the child-process argument list:
  template substitutions are applied through a temporary `sed` script file,
  GitHub Heartbeat secrets are piped to `gh secret set` via stdin, and the
  heartbeat repo push authenticates through an in-memory credential helper
  instead of a token-bearing URL. A failed `gh secret set` now aborts the
  deploy with a clear error instead of reporting the heartbeat ready.
- Make swap monitoring pressure-aware: high swap occupancy alone is
  informational; alerts now require low `MemAvailable` plus swap activity or
  memory PSI, with two-cycle alert and recovery hysteresis.
- Stop swap-triggered page-cache remediation, serialize watchdog/remediation/
  heartbeat cron runs with non-blocking locks, and canonicalize `~` versus
  absolute paths when deduplicating generated cron entries.
- Resolve the Honcho health target with profile-aware host/workspace/base-URL
  precedence compatible with current upstream Hermes, and require the queue
  endpoint to declare `application/json` before schema validation.
- Authenticate Honcho health checks against the configured workspace queue
  endpoint instead of treating an API-root `404` as a successful handshake.
- Validate the Honcho queue response as JSON with the expected work-unit
  counters, so an unrelated `200` response cannot appear healthy.
- Keep Bearer credentials out of the `curl` process argument list during
  authenticated HTTP checks.
- Pipe the configured runtime Bearer token to `curl` through stdin rather than
  sending a placeholder authorization value.

### Added

- Add a pinned GitHub Actions `argus-ci` job covering static validation and
  the regression probe suite for pull requests and `main`.
- Resolve the Honcho base URL and workspace from protected runtime
  configuration, with safe URL/path validation.
- Add regression coverage for Honcho route resolution, authentication
  failures, response-schema failures, path-injection rejection, and secret
  handling.

### Changed

- Health reports now use a schema-v2 envelope (ADR 0001): canonical `summary`
  with per-check `verdict`/`reason_code` and `claims`/`effects`/`evidence`
  containers, plus temporary v1 top-level aliases. The alert wrapper and
  `/integrations` read canonical verdicts: `unknown` and `skipped` no longer
  reset failure counters, and `/integrations` renders them as ⚠️/⏸.
- Health reports are validated fail-closed by all consumers: a report with an
  unknown future schema, missing contract fields (`source`, per-check
  `entity_id`/`primitive`/`reason_code`/`legacy_status`/`claims`/`effects`/
  `evidence`), non-integer or boolean counts, non-ISO timestamps, malformed
  inventory shapes, duplicate ids, or aliases inconsistent with the canonical
  summary is rejected whole — it is never rendered as legacy or green, and
  hysteresis state is preserved untouched.

[Unreleased]: https://github.com/upmeister/hermes-argus/compare/main...HEAD
