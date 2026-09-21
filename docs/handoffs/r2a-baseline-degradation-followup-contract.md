# R2a follow-up contract — baseline must not swallow first degradation

Status: **DONE / MERGED IN THE R2a.1 BATCH**

## Exact baseline

```text
Argus main = 7b78e9369be72d9a5f08de267ccfc62604710f79
R2a / PR #44 = MERGED
R2a candidate = 6241543d96e93cfbe197706dcbf316fbbc72b58d
CI #86 = success
131/131 probes
8/8 swap tests
```

## Remaining P2

Current degraded logic emits `discovery_degraded` only when
`not baseline`.

Therefore:

```text
valid/legacy or no snapshot
 -> malformed config
 -> integration-discover.py --baseline
 -> degraded snapshot written, events=[]
 -> exit 0

next normal malformed run
 -> prev_status=degraded, same reason
 -> events=[]
 -> exit 0
```

The operator-visible degradation transition is lost indefinitely.

This violates the accepted R2a contract:

- first `ok -> degraded` transition is reportable;
- repeated identical degradation is quiet.

`--baseline` may suppress entity diff. It must not suppress discovery-state
transitions.

## Required fix

Keep the patch local:

- `--baseline` suppresses entity added/removed/changed diff only;
- first `ok -> degraded` still emits exactly one `discovery_degraded`;
- same degraded reason on the next run is quiet;
- degradation reason change remains reportable;
- `degraded -> ok` remains reportable, including via baseline;
- valid `--baseline` from ok remains quiet;
- no new exit code, state file, schema or wrapper behavior.

Primary owner:

- `scripts/integration-discover.py`.

Allowed adjacent:

- `tests/probes.py`;
- `CHANGELOG.md`.

No wrapper/health/deep-check change is expected.

## Required red-capable proof

Add one focused probe:

```text
malformed config + --baseline
 -> exit 2
 -> events == [discovery_degraded]

same malformed config + normal run
 -> exit 0
 -> events == []
```

Run that probe against current main and record RED, then candidate GREEN.

Preserve all existing R2a probes, especially
`r2a_recovery_reportable_via_baseline`.

## Non-goals

No R2c.1, RR0, installer, i18n, state-model redesign, reason-code changes,
consumer changes or generalized baseline redesign.

## Review

This is beyond the default single-remediation budget from PR #44. Keep it one
focused follow-up:

```text
one local fix
 -> one Pytna verification
 -> exact-head reread
 -> close R2a OR maintainer blocker
```

## Accepted

Fixed in the R2a.1 batch together with the community plugin metadata shape
hardening. `--baseline` suppresses only the entity diff; the first
`ok -> degraded` transition is reportable through a baseline run, repeated
identical degradation stays quiet, recovery remains reportable. Probe
`r2a_baseline_degraded_reportable` was RED on main before the fix and GREEN
on the candidate.
