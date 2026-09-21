# R2a contract — fail-safe malformed YAML discovery

Status: **MERGED / FOLLOW-UP P2 OPEN**

## Exact baseline

```text
Argus main = 133931a8242de0e61cecace5f75905bf63615383

R1c / PR #42 = DONE
R1c candidate = b477d2bbd4d892b3fee97dd188110d4c7bbff94e
R1c CI #81 = success
OA phase = COMPLETE
R2a = current selected task
```

Supported Hermes authority:

```text
stable = v2026.9.14 / v0.21.3
warning-source main = f88c6fc46e1c1c61ae8fdc0d7fb10ec8ad949aab
```

R2a is a public-release correctness gate.

## 1. Demonstrated problem

The authoritative static `scripts/integration-discover.py` can fail
ungracefully on malformed `~/.hermes/config.yaml`.

Current code:

- `load_yaml()` catches only `FileNotFoundError`;
- YAML parser errors escape;
- a syntactically valid top-level list/string later crashes on `cfg.get(...)`.

Current wrapper behavior compounds the problem:

```text
REPORT=$(python3 integration-discover.py ...)
RC=$?
...
[ "$RC" != "2" ] && exit 0
```

So the present end-to-end failure is:

```text
malformed config
 -> discover traceback/crash
 -> no fresh snapshot
 -> previous snapshot remains on disk
 -> wrapper records the failure in a log
 -> wrapper exits success
 -> no operator-visible degradation
```

This is not fail-safe.

## 2. Required semantic distinction

The implementation must distinguish:

```text
config parsed as a mapping
config file missing (preserve current semantics)
config present but syntactically invalid
config present but top-level is not a mapping
```

Empty YAML may preserve the existing empty-config behavior.

Malformed/wrong-shape config is **not** equivalent to an empty valid config.

Do not implement:

```python
except Exception:
    cfg = {}
```

and continue normal diffing. That would make every config-derived entity look
removed and create a false alert storm.

## 3. Last-good inventory model

Use the smallest state model that makes freshness explicit.

Preferred shape: add a small top-level discovery envelope to the existing
snapshot/report; no new schema version is required solely for R2a.

Minimum semantics:

```text
discovery.status = ok | degraded
discovery.reason_code = stable machine-readable reason
discovery.attempted_at = timestamp of current attempt
discovery.last_good_at = timestamp of last successful inventory, if any
```

Exact field names may differ slightly, but equivalent information must exist.

### Valid config

On a successful parse/extract:

- write a normal fresh inventory;
- `updated` continues to represent successful inventory freshness;
- discovery status is ok;
- existing added/removed/changed semantics are preserved.

### Malformed config with previous-good snapshot

On a malformed/wrong-shape config:

- do not traceback;
- preserve the previous-good `entities`;
- preserve the previous-good freshness meaning of `updated`;
- preserve last-good `config_hash` / inventory metadata where practical;
- record the current failed attempt separately;
- mark discovery degraded with a stable reason code;
- do not emit config-derived removed/changed events from a partial/empty parse.

A raw parser exception or source-line excerpt is not required and should not be
put into operator output because YAML may contain secrets.

### Malformed config with no prior snapshot

Still write enough structured degraded snapshot/report state that consumers can
fail closed.

Do not pretend an empty inventory is a successful baseline.

## 4. Recovery semantics

When config becomes valid after degradation:

- run ordinary extraction;
- compare the recovered entity set against the preserved last-good entity set;
- report genuine changes once;
- do not manufacture a remove/add storm caused only by the malformed interval;
- return discovery status to ok;
- surface a bounded recovery event even when the entity diff is empty.

If config legitimately changed while it was malformed, those changes should
appear relative to the last successful inventory after recovery.

## 5. Operator event / exit semantics

Prefer the existing discover contract rather than adding a new systemd exit
code:

```text
0 = no operator-visible change
2 = reportable entity change or discovery-state transition
```

A report may carry a dedicated discovery-state event in addition to the current
entity `events` list.

Required behavior:

- first `ok -> degraded` transition is reportable;
- repeated identical degraded attempts are quiet (no 10-minute cron spam);
- a meaningful degradation reason change may be reportable;
- `degraded -> ok` recovery is reportable;
- valid-config entity events remain unchanged.

`scripts/integration-discover-wrapper.sh` must render degradation/recovery
human-readably instead of silently swallowing the state or dumping opaque JSON.

## 6. Snapshot consumers must fail closed

The snapshot is the source of what Argus considers live.

A snapshot marked degraded must not be consumed as fresh inventory.

Review/update the two current production consumers:

### health-check-v2.py

Before building/running checks:

- detect degraded discovery state;
- print a concise configuration/degraded diagnostic;
- return through the existing configuration-error path;
- perform no network/provider/MCP checks from stale inventory;
- do not rewrite a fresh-looking health report.

Exit code 2 is the natural bounded behavior: the existing wrapper already logs
this configuration error and does not process stale health output.

### ai-deep-check.py

Before catalog/chat curl calls:

- reject degraded discovery state;
- perform no provider network/subprocess work;
- provide a concise operator diagnostic.

This is a manual deep-check boundary, not a health-schema redesign.

Legacy snapshots without the new discovery envelope must remain readable as
pre-R2a successful snapshots for upgrade compatibility.

## 7. Owner surface

Primary:

- `scripts/integration-discover.py`.

Allowed adjacent because they own the same stale/degraded boundary:

- `scripts/integration-discover-wrapper.sh`;
- `scripts/health-check-v2.py`;
- `scripts/ai-deep-check.py`;
- `tests/probes.py`;
- `CHANGELOG.md`.

Do not widen into unrelated YAML readers merely because they use the same
helper. Malformed community `plugin.yaml` is not the R2a problem unless a
small shared change handles it safely without changing product semantics.

No systemd unit change should be needed if exit code 2 remains the reportable
event code.

## 8. Required red-capable probes

Add focused coverage for at least:

1. **syntax error**
   - malformed YAML does not traceback;
   - snapshot/report are explicitly degraded.

2. **wrong top-level shape**
   - list/string is degraded, not treated as empty/healthy.

3. **valid control**
   - valid config output/entity semantics stay unchanged.

4. **missing config control**
   - existing missing-file behavior stays unchanged.

5. **last-good preservation**
   - establish a good snapshot with entities;
   - corrupt config;
   - entities remain last-good;
   - last-good freshness is not rewritten as a successful current observation.

6. **no false removals**
   - malformed attempt emits no mass removed/changed entity events.

7. **bounded repetition**
   - first degradation is reportable;
   - second identical degraded run is quiet.

8. **recovery**
   - repair config;
   - recovery is reportable;
   - diff is computed against last-good inventory;
   - genuine changes are reported once.

9. **health consumer fail-closed**
   - degraded snapshot returns through configuration-error path;
   - prove curl/MCP/subprocess/network primitives were not called.

10. **deep-check consumer fail-closed**
    - degraded snapshot makes zero curl calls.

11. **wrapper rendering**
    - degradation and recovery produce useful human-facing summary;
    - no real network is required in the probe.

12. **secret/error boundary**
    - a malformed YAML canary resembling a secret is absent from
      stdout/stderr/report/discovery diagnostic text.

Whenever practical, run the new probes against the pre-R2a baseline and record
which ones are red there.

## 9. Regression gates

Run at minimum:

```bash
python3 tests/probes.py
python3 tests/test_watchdog_swap.py
python3 -m py_compile scripts/integration-discover.py scripts/health-check-v2.py scripts/ai-deep-check.py tests/probes.py
bash -n deploy.sh scripts/integration-discover-wrapper.sh
git diff --check
```

Exact candidate-head CI must be green.

## 10. Non-goals

R2a does not authorize:

- canonical Hermes config normalization;
- importing `hermes_cli.config`;
- repairing/reformatting/re-writing user YAML;
- C1/C1a runtime bridge revival;
- generalized config provenance framework;
- a new persistent database/sidecar state format;
- provider/plugin execution during discovery;
- `fallback_providers` / R2c.1 work;
- installer/cron/i18n work;
- multi-profile fan-out;
- unrelated cleanup.

Static auth/env inputs do not need to be rearchitected merely to provide
"partial" output during config degradation; preserving trustworthy last-good
inventory is sufficient for R2a.

## 11. Stop condition

Stop and return the concrete incompatibility if a correct fix appears to
require:

- discovery schema migration across the product;
- a new state database/file family;
- broad health-report schema changes;
- Hermes runtime imports;
- new network/process dependencies;
- repeated remediation beyond the default budget.

## 12. ZCode receipt

```markdown
# R2a outcome

## Exact baseline/head

## Failure reproduction
- syntax error:
- wrong top-level:
- wrapper old behavior:

## State model
- discovery envelope:
- last-good preservation:
- freshness behavior:

## Degradation
- first transition:
- repeated degraded run:
- no false entity events:

## Recovery
- recovery event:
- diff against last-good:
- genuine change behavior:

## Consumer fail-closed
- health-check-v2:
- ai-deep-check:
- zero network/subprocess evidence:

## Wrapper/operator behavior

## Secret/error boundary

## Tests / red capability / CI

## Changed files

## Out-of-scope findings

## Production actions
None.

## Recommendation
READY FOR PYTNA | BLOCKED
```

## 13. Pytna focus

Prioritize:

1. malformed config is silently converted to empty valid config;
2. last-good entities become false removals;
3. stale entities receive a fresh successful timestamp;
4. wrapper still hides degradation;
5. repeated malformed runs alert every cron cycle;
6. recovery compares against partial/empty state instead of last-good;
7. health/deep-check execute against a degraded snapshot;
8. parser/source excerpts leak secret-like YAML content;
9. legacy pre-R2a snapshots stop working;
10. the patch grows into a generalized Hermes config framework.

Recommendation:

```text
PASS-TO-MERGE | REMEDIATE | BLOCKED-FOR-MAINTAINER
```


## Final exact-tree follow-up

After PR #44 merge, final review found that `--baseline` can suppress the first
`discovery_degraded` transition and make subsequent identical degraded runs
quiet indefinitely. See:

`docs/handoffs/r2a-baseline-degradation-followup-contract.md`

R2a is not closed until that focused follow-up passes.
