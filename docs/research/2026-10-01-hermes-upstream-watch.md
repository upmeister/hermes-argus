# Hermes upstream watch — 2026-10-01

Status: **RESEARCH COMPLETE — authority refreshed. No production code in this PR.**

Supersedes the authority snapshot of `2026-09-24-hermes-upstream-watch.md`. The
seam list that these findings feed lives in
`docs/research/hermes-argus-seams.md`.

## Authority snapshot

```text
previous supported stable = v2026.9.21 / Hermes Agent v0.21.4
                          = d337b736aa1e8ebecfab043842d13e4a2d2f48a3
new supported stable      = v2026.9.24 / Hermes Agent v0.21.5
                          = f97608f178d1ffeca59860195ab7da295f7c8e5f
previous warning-source main = 35b14ad5e24137b836d5c47c21a50c6ea7aeb785
main drift at watch           = +4908 commits past the new stable tag
```

`35b14ad5` (the previous warning-source main) is an ancestor of `v2026.9.24`:
what the previous watch called "main-only" has now been released as stable.

Verified on a local checkout of `NousResearch/hermes-agent`, tag-to-tag and
against the recorded canon SHAs.

## 1. Stable moved: v0.21.4 → v0.21.5

The stable tag advanced one release. The intervening commits
(`v2026.9.21..v2026.9.24`) are dominated by memory/compression/config-ladder
hardening and desktop/dashboard fixes; none touch the Argus observation
surfaces except the one fallback change below.

## 2. R2c.1 authority — unchanged, still correct

`hermes_cli/fallback_config.py:get_fallback_chain()` in v0.21.5 is
**semantically identical** to the v0.21.4 form R2c.1 was built against:

```text
fallback_providers first, ordered
+ fallback_model afterwards
+ dedupe by (provider.lower(), model.lower(), normalized base_url)
```

Entry handling is unchanged: mapping-or-list source, non-mapping dropped,
provider/model `str(...).strip()` and non-empty required, string base_url
trimmed with trailing slashes removed. `_iter_fallback_entries` /
`_entry_identity` in v0.21.5 match the static inventory Argus ships.

Decision: **R2c.1 (PR #49) is confirmed correct against the new stable. No
rework required.**

## 3. Drift closed: `scoped_fallback_chain()` is now stable

This is the substantive change since the previous watch. The previous research
recorded `scoped_fallback_chain()` as **warning-source main only**, explicitly
not R2c.1 authority. In v0.21.5 it is **stable**, introduced by:

```text
e7bff4b6d831 fix(cron): a pinned job never falls back to the global fallback
chain (#120312)
```

Stable semantics of `scoped_fallback_chain(inherited, declared, *, pinned, owner)`:

- a **pinned** owner (explicit provider/endpoint/model) never borrows the
  inherited chain — predictability beats liveness;
- an **unpinned** owner inherits the chain when `declared` is absent/None;
- explicit `[]` disables fallback either way;
- any other `declared` value is the owner's own chain, normalized by
  `get_fallback_chain` (malformed entries dropped; if nothing usable remains,
  fall back to the pinned/inherited default).

Implication for Argus:

- This is a **route-owner** semantics, not the top-level static inventory R2c.1
  owns. R2c.1 is not affected and does not need to move.
- But the reason R2c.2 was scoped as "main-only / moving territory" no longer
  holds: the seam is now a **stable contract**. R2c.2 remains deferred to
  post-RC, but its justification is now "bounded stable work with operator
  value" rather than "chasing unstable main". Re-sequence deliberately, do not
  pull it into R2c.1 or the release gate.

## 4. MCP seam — stable, and the `enabled` gap is real

`hermes mcp test <name>` exit codes in v0.21.5:

```text
0 = connected
1 = connection failed
3 = server absent from config
2 = argparse usage errors (owned by argparse)
```

Output markers unchanged (`Connected (...)`, `Tools discovered: N`,
`Connection failed (...)`). Argus still parses markers and stays compatible;
adopting the exit codes remains a separate bounded maintenance task.

Confirmed on v0.21.5 (`hermes_cli/mcp_config.py`): `cmd_mcp_test()` and
`_lookup_server()` **do not consult the `enabled` key**. A server with
`enabled: false` is still probed for real. Consequences:

- HTTP disabled server (dead URL) → genuine probe failure → Argus reports
  `fail` / "недоступен" for a server the operator deliberately turned off;
- stdio disabled server with a valid `command` → the probe can *succeed* → a
  false-green on a disabled server.

The canonical reader of the key is `tools/mcp_tool_common.py:mcp_server_enabled()`
(absent/null/unparseable = on). Argus discovery does not read `enabled` at all.
This is the subject of the proposed MCP disabled-server contract.

## 5. Runtime fallback marker — unchanged

Both stable and main still emit:

```text
Primary runtime restored for new turn: ...
```

(`agent/agent_runtime_helpers.py:1307` on v0.21.5.) The Argus runtime
fallback tracker remains compatible. No rewrite.

## 6. OA2 — still CLOSED / UPSTREAM-GATED

Re-checked on v0.21.5:

- `GET /api/providers/oauth` (`hermes_cli/web_routers/oauth.py`) still returns
  status cards without the machine-token requirement used on mutating routes;
- status cards still carry `token_preview` (last-N chars, not the full token),
  also surfaced in `web_routers/ops.py` and the desktop types;
- Qwen status refresh behavior is unchanged from the previous watch.

The reopen gate is not satisfied:

```text
refresh-free
+ no provider network/write
+ no secret-ish response fields
+ supported machine-authenticated observation seam
```

Decision: **OA2 stays CLOSED / UPSTREAM-GATED.** Re-check on the next watch.

## 7. Implications for the roadmap

- **R2c.1** — done (PR #49) and confirmed against v0.21.5. No rework.
- **RR0** — becomes the current release gate (status docs must say so).
- **R2c.2** — still post-RC, but re-framed: `scoped_fallback_chain` is now a
  stable seam, so R2c.2 is bounded stable compatibility work rather than
  main-chasing. Sequence deliberately; no scope change to R2c.1.
- **MCP disabled-server** — a separate bounded maintenance contract, not part
  of R2c.1/RR0.
- **OA2** — unchanged, upstream-gated.

The architecture invariant still holds:

```text
Hermes owns runtime truth.
Argus observes externally, verifies independently where useful, and makes failures loud.
```
