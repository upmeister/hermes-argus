# MCP disabled-server compatibility contract

Status: **DRAFT / AWAITING MAINTAINER SELECTION**

## 1. Exact authority

Argus baseline:

```text
main = a58cfcdaadea094281c9aa1e459d7b4bf76f9032
R2c.1 = CLOSED / PR #49
```

Hermes authority:

```text
stable = v2026.9.24 / v0.21.5
stable tag commit = f97608f178d1ffeca59860195ab7da295f7c8e5f
```

Stable behavior is implementation authority. Upstream `main` is warning only.
See `docs/research/2026-10-01-hermes-upstream-watch.md` (§4) and
`docs/research/hermes-argus-seams.md` (S4).

## 2. Demonstrated compatibility gap

Hermes marks a configured MCP server as off with `enabled: false` on its
`mcp_servers.<name>` entry. The canonical reader is
`tools/mcp_tool_common.py:mcp_server_enabled()` — absent, `null`, or
unparseable means **on**.

`hermes mcp test <name>` does **not** consult that key: `cmd_mcp_test()` and
`_lookup_server()` in `hermes_cli/mcp_config.py` probe the server regardless.
Verified on stable v0.21.5.

Argus discovery (`scripts/integration-discover.py`) does not read `enabled`
either, so a disabled server still becomes an `mcp-test` check. Result:

- **disabled HTTP server** (dead URL) → a real probe failure → Argus reports
  `failed` / "connection failed" for a server the operator deliberately turned
  off. This is a false alarm, and it is exactly the "недоступен" the operator
  sees.
- **disabled stdio server** with a valid `command` → the probe can *succeed* →
  a **false-green** on a disabled server.

Both are wrong: a deliberate configuration choice is being reported as either
a failure or a health signal. This is a supported-stable discovery gap, not a
warning-source-main feature.

## 3. Required behavior

### 3.1 Discover the `enabled` intent

`scripts/integration-discover.py` must read `enabled` for each
`mcp_servers.<name>` entry using the canonical Hermes rule and nothing more:

```text
absent / null / unparseable -> enabled (on)
explicit false-y value      -> disabled (off)
```

A pure local helper mirroring this rule is required. Do **not** import Hermes.
The stable rule is `_parse_boolish(cfg.get("enabled", True), default=True)`:

```text
None            -> True
bool / int / float -> bool(value)      (so 0 / 0.0 -> False)
"true"/"1"/"yes"/"on"   (stripped, lowercased) -> True
"false"/"0"/"no"/"off"  (stripped, lowercased) -> False
anything else (incl. unknown strings, lists, dicts) -> True (default)
```

Reproduce exactly this set, including "unparseable means on". Do not widen it
(a server that Hermes would run must never be skipped by Argus).

The disabled intent is carried as a non-secret flag on the existing `mcp:*`
entity (for example `"enabled": false`). Do not invent a new entity type or a
new snapshot schema.

### 3.2 Do not probe a disabled server

`scripts/health-check-v2.py` must not invoke `check_mcp` for an MCP entity
discovered as disabled. It must return a non-failing verdict that does not
count as `failed` and does not count as `healthy`.

Use the existing ADR 0001 vocabulary. Preferred mapping:

```text
status/verdict = skipped
reason_code    = mcp_disabled_by_config
detail         = human-readable, e.g. "mcp: disabled by config"
```

Rationale: `skipped` already means "policy/config did not check", never resets
a failure counter, and is never rendered green. `unknown` is wrong here — a
disabled server is a known, deliberate state, not an unreadable result. Do not
add a new verdict value.

### 3.3 Render it honestly

`scripts/webhook.py` `/integrations` rendering:

- a disabled MCP server must not appear in the `❌` failure list;
- it should be visible as a deliberate skip, not hidden. If grouping is
  unchanged, the existing `skipped` bucket plus a per-item detail is
  sufficient; a dedicated "⏸ disabled" line per server is acceptable only if
  it stays within the owner surface below.

Do not change the meaning of any other skipped reason (`oauth` evidence,
policy skips). The ADR 0001 "skipped-only report is never rendered green" rule
stays intact.

## 4. Boundaries

- **Server-level `enabled` only.** Tool-level filtering
  (`tools.include: []` / `exclude`, an enabled server registering zero tools)
  is **out of scope**. It is a separate, smaller gap: the server is reachable
  but exposes no tools. Do not fold it in.
- **No new persistent state**, no new snapshot schema, no new module flag.
- **No Hermes imports**, no provider/plugin execution, no credential
  resolution.
- **`enabled` default-on must match Hermes exactly.** A server with no
  `enabled` key is enabled; the patch must not start skipping servers that
  Hermes itself would run.

## 5. Owner surface

Primary:

- `scripts/integration-discover.py` — read `enabled`, tag the entity.
- `scripts/health-check-v2.py` — short-circuit the check for a disabled entity.

Allowed adjacent:

- `scripts/webhook.py` — only if the existing `skipped` rendering genuinely
  cannot surface the disabled state without a change;
- `tests/probes.py`;
- `CHANGELOG.md`.

Not owners:

- `fallback-tracker-v2.py`;
- `registry.yaml` / `scripts/gen-registry.py`;
- OAuth/account-auth code;
- installer/i18n/RR0 surfaces;
- `local_services_check.py`.

## 6. Required red-capable probes

At minimum:

1. **disabled HTTP server is not failed**
   - `enabled: false` + dead URL → verdict `skipped`, reason
     `mcp_disabled_by_config`, not in the failure list.

2. **disabled stdio server is not green**
   - `enabled: false` + valid `command` → not `healthy`, not `failed`;
     `check_mcp` is not invoked.

3. **enabled default**
   - a server with no `enabled` key is still probed normally (no behavior
     change).

4. **explicit enabled true**
   - `enabled: true` behaves exactly as today.

5. **falsy-value fidelity**
   - the local helper's false-y set matches the stable `mcp_server_enabled()`
     result for the same inputs.

6. **no probe side effect**
   - for a disabled server, no subprocess/`hermes mcp test` runs (assert via
     the probe harness, not by timing).

7. **render**
   - a mixed report (one enabled-ok, one enabled-failed, one disabled) shows
     the disabled server as a skip, keeps the failure, and does not render the
     report green.

8. **unrelated discovery control**
   - provider/OAuth/plugin/fallback discovery is byte-identical to baseline
     for a fixture with no disabled MCP servers.

Run probes 1–2 against baseline `a58cfcda` and record the expected RED
capability failure.

## 7. Regression gates

At minimum:

```bash
python3 tests/probes.py
python3 tests/test_watchdog_swap.py
python3 -m py_compile scripts/integration-discover.py scripts/health-check-v2.py scripts/webhook.py tests/probes.py
bash -n deploy.sh
git diff --check
```

Exact candidate-head `argus-ci` must be green.

## 8. Non-goals

This contract does not authorize:

- tool-level (`tools.include`/`exclude`) filtering awareness;
- R2c.2 scoped/auxiliary fallback coverage;
- adopting the `hermes mcp test` 0/1/3 exit codes (separate maintenance task);
- OA2 changes;
- RR0 cleanup;
- installer/i18n work;
- multi-profile fan-out;
- new snapshot schema or new verdict values.

## 9. Stop condition

Stop and report the concrete blocker if the patch begins to require:

- a new verdict value or schema version;
- Hermes imports or a vendored copy of `mcp_server_enabled`;
- a config/settings framework;
- changes to how skipped reasons other than MCP are computed;
- RR0 or exit-code work to make this pass.

## 10. Role-based delivery

Reviewer: **to be named by the maintainer** (the Pytna default is not
currently in effect).

### Builder

Perform one implementation pass and return a receipt with:

```text
# MCP disabled-server implementation receipt

## Exact baseline/head
## enabled rule reproduced (and its falsy set)
## disabled-server verdict + reason_code
## probe non-execution proof
## render behavior (disabled / failed / ok mix)
## default-on regression
## unrelated-discovery control
## Tests / red capability / CI
## Changed files
## Out-of-scope findings
## Production actions: None
## Recommendation: READY FOR FOCUSED REVIEW | BLOCKED
```

### Focused reviewer

Prioritize:

1. `enabled` default-on diverges from Hermes (skips a server Hermes would run);
2. disabled server still reported as failed or still probed;
3. disabled server reported as healthy/green;
4. a new verdict/schema value slipped in;
5. skipped reasons other than MCP changed;
6. tool-level filtering folded in (scope creep);
7. Hermes imports or RR0/exit-code work mixed into the patch.

Return: `PASS-TO-MAINTAINER | REMEDIATE | BLOCKED-FOR-MAINTAINER`.

### Maintainer

After review/remediation: reread the exact candidate head, verify CI and
receipt match that head, compare changed blobs after merge, and authorize
production deploy separately.
