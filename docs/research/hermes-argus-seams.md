# Argus ↔ Hermes seams

Status: **durable reference; research refreshed 2026-10-25**. Accepted support
remains v0.21.5 (`f97608f`) pending contract A's compatibility evidence.
Latest inspected target is v0.22.5 (`bf0203a`); see the
[watch](2026-10-25-hermes-upstream-watch.md). Research verification is not a
clean-install or deployment receipt.

This file lists every place where Argus depends on a Hermes-owned behavior.
An upstream watch pass is the act of re-verifying this list, not of reading the
whole upstream changelog. Add a seam when Argus starts relying on new Hermes
behavior; remove one when the dependency goes away.

Each seam records: what Argus reads, why it is a seam, where it lives in Argus,
where it lives in Hermes, and what to re-check on a watch pass.

## S1 — Top-level fallback chain

- **Argus reads:** `fallback_providers` (ordered) + legacy `fallback_model`,
  deduped by `(provider.lower(), model.lower(), normalized base_url)`.
- **Why a seam:** Argus inventories *configured* fallback routes; the
  merge/dedupe/order semantics are Hermes-owned.
- **Argus:** `scripts/integration-discover.py` (fallback inventory).
- **Hermes:** `hermes_cli/fallback_config.py:get_fallback_chain()`.
- **Re-check:** source-key order, mapping-vs-list handling, dedupe identity,
  base_url normalization.
- **Status:** source order remains stable; v0.22.5 adds canonical provider
  aliases to dedupe identity. Argus now mirrors that identity from the
  installed `_ALIAS_GROUPS` literal (implemented, contract A review pending;
  [DEBT-025](../BACKLOG.md#debt-025)). A re-check on a watch pass must still
  verify the alias source path/symbol and the fallback_config identity.

## S2 — Scoped route-owner fallback

- **Argus reads:** nothing yet (post-RC candidate for R2c.2).
- **Why a seam:** pinned/unpinned route owners (delegated children, cron jobs)
  may inherit or declare their own fallback chain. Argus does not model route
  owners; if R2c.2 is taken up this becomes a live read.
- **Hermes:** `hermes_cli/fallback_config.py:scoped_fallback_chain()`
  (introduced into stable by `e7bff4b6d831`, #120312).
- **Re-check:** pinned-never-inherits, explicit `[]` disables, malformed-entry
  fallback to default.
- **Status:** stable as of v0.21.5; R2c.2 deferred to post-RC.

## S3 — `hermes mcp test` process contract

- **Argus reads:** stdout markers `Connected (...)`, `Tools discovered: N`,
  `Connection failed (...)`.
- **Why a seam:** the probe result is Hermes-owned; Argus branches on it.
- **Argus:** `scripts/health-check-v2.py:check_mcp()`.
- **Hermes:** `hermes_cli/mcp_config.py:cmd_mcp_test()`.
- **Re-check:** marker wording, and the exit codes
  (0 connected / 1 connection failure / 3 server absent / 2 argparse).
- **Known debt:** `check_mcp` still says "exit code is always 0"; adopting the
  stable exit codes is a separate maintenance task.
- **Status:** stable, matches. Last verified v0.21.5.

## S4 — MCP `enabled` key

- **Argus reads:** `enabled` intent since merged PR #59; disabled entries are
  skipped without a real probe.
- **Hermes:** `tools/mcp_tool_common.py:mcp_server_enabled()`; default-on for
  absent/null/unparseable values. Explicit `mcp test` still probes disabled entries.
- **Re-check:** boolean interpretation and explicit test behavior.
- **Status:** fixed in Argus; semantics rechecked against v0.22.5. The previous
  wording that Argus did not read the key was stale.

## S5 — Runtime fallback marker

- **Argus reads:** the log line `Primary runtime restored for new turn: ...`.
- **Why a seam:** it is the signal Argus' fallback tracker keys on.
- **Hermes:** `agent/agent_runtime_helpers.py` (logged at info).
- **Re-check:** the literal marker text.
- **Status:** stable, matches. Last verified v0.21.5.

## S6 — OA2 OAuth observation seam

- **Argus wants:** a refresh-free, no-provider-write, no-secret,
  machine-authenticated read of provider OAuth status.
- **Why a seam:** OA2 is permanently gated on Hermes exposing such a route.
- **Hermes:** `hermes_cli/web_routers/oauth.py` — `GET /api/providers/oauth`.
- **Re-check:** whether the read route gained machine auth, whether
  `token_preview` / secret-ish fields were removed, whether status reads still
  refresh credentials.
- **Status:** CLOSED / UPSTREAM-GATED (gate not satisfied on v0.21.5).

## S7 — installation-bound launch and interpreter

- **Argus:** deploy preflight, MCP binary default, gateway helper and service
  templates currently assume checkout `venv/bin`; A adapts these consumers.
- **Hermes:** `hermes_cli/_launchers.py` published launcher and
  `--print-runtime-command`; `pm/environments.py` owns environment selection.
- **Re-check:** a managed install without legacy venv; commands after a
  generation change; no stale selected-interpreter path in installed templates.
- **Status:** implemented (contract A review pending,
  [DEBT-024](../BACKLOG.md#debt-024)): every launch consumer binds to the
  configured installation root through `scripts/hermes-runtime.py` — the
  published launcher for CLI calls, `--print-runtime-command --module runpy`
  for Argus Python scripts; legacy in-tree venv remains the no-launcher
  fallback; present-but-unusable launcher is a bounded failure, never a
  stale-venv fallback. A watch pass re-verifies the launcher path, the
  `--print-runtime-command` argv shape and the module-only deploy manifests.

## S8 — gateway identity and log routing

- **Argus:** `hermes-gateway-pids.py` imports Hermes's strict matcher/private
  cmdline reader and filters by installation path; liveness and fallback
  tracking read default-home logs.
- **Hermes:** `gateway/status.py`, multiplexed profile routing and runtime logs.
- **Re-check:** import names, real launch argv, process/home scope and logger
  identities. A preserves current scope; broader multi-profile coverage is separate.
- **Status:** imports/log markers retained on v0.22.5; no full multi-profile claim.

## S9 — registry source data

- **Argus:** `scripts/gen-registry.py` statically parses `OPTIONAL_ENV_VARS`.
- **Hermes:** `hermes_cli/config_defaults.py` data and helper signatures.
- **Re-check:** generator completes against immutable source; generated fields
  retain intended semantics; integration completeness is a separate question.
- **Status:** v0.22.5 parser experiment succeeds (153 entries + 9 kit entries).

## S10 — static account/plugin inventory scope

- **Argus:** single-home auth structure and `plugins/model-providers` metadata.
- **Hermes:** profile credential inheritance and plugin discovery/catalog ownership.
- **Re-check:** source locations/shapes and whether static evidence is being
  mistaken for the effective runtime set. Never execute plugins for inventory.
- **Status:** coverage boundary; no full plugin or multi-profile expansion selected.

## Watch procedure

1. Resolve the current stable tag and record its commit SHA.
2. For each seam above, re-check the named Hermes location at that SHA.
3. Record drift in a dated `docs/research/<date>-hermes-upstream-watch.md`.
4. Update seam statuses here and adjust the roadmap only where drift warrants.
5. Do not promote a seam to a roadmap item without a maintainer decision; this
   list is observation, not authorization.
