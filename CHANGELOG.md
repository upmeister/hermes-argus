# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- Authenticate Honcho health checks against the configured workspace queue
  endpoint instead of treating an API-root `404` as a successful handshake.
- Validate the Honcho queue response as JSON with the expected work-unit
  counters, so an unrelated `200` response cannot appear healthy.
- Keep Bearer credentials out of the `curl` process argument list during
  authenticated HTTP checks.

### Added

- Resolve the Honcho base URL and workspace from protected runtime
  configuration, with safe URL/path validation.
- Add regression coverage for Honcho route resolution, authentication
  failures, response-schema failures, path-injection rejection, and secret
  handling.

[Unreleased]: https://github.com/upmeister/hermes-argus/compare/main...HEAD
