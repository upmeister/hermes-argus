# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Inventory the ordered Hermes `fallback_providers` chain, append unique legacy
  `fallback_model` entries, and keep route metadata sanitized. This is static
  configuration evidence, not a claim about the route used for a request.

### Fixed

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
