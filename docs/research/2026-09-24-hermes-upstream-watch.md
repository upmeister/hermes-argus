# Hermes upstream watch — 2026-09-24

Status: **RESEARCH COMPLETE / R2c.1 AUTHORITY REFRESHED**

## Authority snapshot

```text
supported stable = v2026.9.21 / Hermes Agent v0.21.4
stable tag commit = d337b736aa1e8ebecfab043842d13e4a2d2f48a3
warning-source main = 35b14ad5e24137b836d5c47c21a50c6ea7aeb785
main ahead of stable at watch = ~1413 commits
```

Argus targets stable behavior first. Main is used only to see likely future
drift.

## 1. R2c.1 fallback authority

Stable `hermes_cli/fallback_config.py` contains
`get_fallback_chain(config)`.

Its effective top-level semantics are:

```text
fallback_providers first, ordered
+ fallback_model afterwards
+ dedupe provider/model/normalized base_url
```

Entry handling in stable:

- source may be one mapping or an ordered list;
- non-mapping entries are ignored;
- provider/model are `str(...).strip()` and must remain non-empty;
- string base_url is trimmed and trailing slashes removed;
- dedupe identity lowercases provider/model/normalized base_url.

Stable `hermes_cli/fallback_cmd.py` writes the resulting chain to
`fallback_providers` and removes `fallback_model`.

Therefore R2c.1 is now fully supported-stable compatibility work.

## 2. Warning-source main fallback drift

Current main preserves the same `get_fallback_chain()` semantics.

It additionally has `scoped_fallback_chain()`, which applies inherited versus
declared chains to route owners with pinned/unpinned semantics (for example
delegated children and cron-style owners).

This is not R2c.1 authority. Mirroring it would expand Argus from top-level
static inventory into moving route-owner semantics.

Decision:

```text
R2c.1 = top-level stable chain only
R2c.2 = optional scoped/auxiliary coverage after RC
```

## 3. Runtime fallback marker

Both stable and watched main still log:

```text
Primary runtime restored for new turn: ...
```

The existing Argus runtime fallback tracker remains compatible. No R2c.1
tracker rewrite is justified.

## 4. MCP seam

Stable v0.21.4 now documents and implements useful process exit codes for
`hermes mcp test <name>`:

```text
0 = connected
1 = connection failed
3 = server absent from config
2 = argparse usage errors
```

It still emits:

```text
Connected (...)
Tools discovered: N
Connection failed (...)
```

Argus currently parses these markers and therefore remains compatible.

A future maintenance patch may consume the stable exit codes to simplify
`check_mcp`. Do not mix that cleanup into R2c.1.

Known local documentation debt: the old comment in `health-check-v2.py`
still says the MCP command always exits zero.

## 5. OA2 watch

OA2 remains CLOSED on both stable and watched main.

### Qwen

`get_qwen_auth_status()` still calls runtime credential resolution with:

```text
refresh_if_expiring=True
```

So listing Qwen status can refresh/write credential state.

### OAuth status payload

OAuth status-card helpers still include `token_preview` values.

### OAuth listing route

The read-only:

```text
GET /api/providers/oauth
```

still returns status cards without the machine-token requirement used on
mutating/disconnect routes.

This does not satisfy the Argus OA2 reopen gate:

```text
refresh-free
+ no provider network/write
+ no secret-ish response fields
+ supported machine-authenticated observation seam
```

Decision: **OA2 stays CLOSED / UPSTREAM-GATED.**

## 6. Stable bump implications for Argus

Promote to stable authority:

- canonical fallback-chain static semantics;
- MCP 0/1/3 exit codes;
- existing fallback restore marker compatibility.

Do not promote from main:

- scoped route-owner fallback inheritance;
- any newer auxiliary/delegation/cron routing semantics.

The architecture invariant remains correct:

```text
Hermes owns runtime truth.
Argus observes externally, verifies independently where useful, and makes failures loud.
```
