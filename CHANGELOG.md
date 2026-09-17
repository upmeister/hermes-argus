# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- Keep deployment secret values out of the child-process argument list:
  template substitutions are applied through a temporary `sed` script file,
  GitHub Heartbeat secrets are piped to `gh secret set` via stdin, and the
  heartbeat repo push authenticates through an in-memory credential helper
  instead of a token-bearing URL.
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
