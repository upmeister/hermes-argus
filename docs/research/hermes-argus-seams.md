# Argus ↔ Hermes seams

Status: **durable reference.** Last verified 2026-10-01 against Hermes stable
`v2026.9.24 / v0.21.5` (`f97608f178d1ffeca59860195ab7da295f7c8e5f`).

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
- **Status:** stable, matches R2c.1. Last verified v0.21.5.

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

- **Argus reads:** currently nothing — this is the gap.
- **Why a seam:** `enabled: false` on an `mcp_servers.<name>` entry means the
  server is deliberately off, but `hermes mcp test` still probes it. Argus
  therefore reports a disabled server as failed/unavailable (HTTP) or even
  green (stdio with a valid command).
- **Hermes:** `tools/mcp_tool_common.py:mcp_server_enabled()` — the one reader
  of the key; absent/null/unparseable = on.
- **Re-check:** the default-on rule and that no other surface disagrees.
- **Status:** stable gap; subject of the proposed MCP disabled-server
  contract.

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

## Watch procedure

1. Resolve the current stable tag and record its commit SHA.
2. For each seam above, re-check the named Hermes location at that SHA.
3. Record drift in a dated `docs/research/<date>-hermes-upstream-watch.md`.
4. Update seam statuses here and adjust the roadmap only where drift warrants.
5. Do not promote a seam to a roadmap item without a maintainer decision; this
   list is observation, not authorization.
