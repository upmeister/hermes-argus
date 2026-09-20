# 2026-09-17 next-steps execution baseline

Status: **ACTIVE EXECUTION BASELINE — UPDATED 2026-09-20**

This document translates the release roadmap into bounded repository work.
Agents may perform only the named task currently selected by the maintainer.

## Architecture invariant

```text
Hermes owns runtime truth.
Argus observes externally, verifies independently where useful, and makes failures loud.
```

Do not introduce a Hermes runtime-import bridge to improve discovery or health
coverage.

## Exact current baseline

```text
Argus main = 133931a8242de0e61cecace5f75905bf63615383

R1a / PR #29 = DONE
R1b / PR #31 = DONE
R1c / PR #42 = DONE
OA phase / PR #40 = COMPLETE

R2a = NOW
```

R1c final evidence:

```text
candidate head = b477d2bbd4d892b3fee97dd188110d4c7bbff94e
CI #81 = success
115/115 probes
8/8 swap tests
candidate/main changed blobs = identical
```

The sole Pytna remediation changed only the probe harness. It fixed a synthetic
Authorization canary leaking from test detail and made the real-curl seam
capture fail closed. Production R1c code did not change during remediation.

Supported Hermes authority:

```text
v2026.9.14 / v0.21.3
stable commit = 345cd2b057a452236de401d3534b8502a7465e8d
warning-source main = f88c6fc46e1c1c61ae8fdc0d7fb10ec8ad949aab
```

## Current execution order

```text
R1c Authorization-header argv debt        DONE / PR #42
 -> R2a malformed YAML                    NOW
 -> R2c.1 fallback_providers compatibility
 -> RR1 installer/dependency/managed-cron
 -> RR2 runtime i18n (en + ru)
 -> RR3 release acceptance
 -> v0.1.0-rc.1
 -> soak
 -> v0.1.0

R2c.2 auxiliary coverage                 AFTER RC
R3 reduction/stabilization               AFTER RC
OA2 dynamic account status               CLOSED / UPSTREAM-GATED
R2b gateway liveness                     DEFERRED
MP*                                       SEPARATE
```

## Current selected contract

```text
docs/handoffs/r2a-malformed-yaml-contract.md
```

## R2a demonstrated failure chain

Current `integration-discover.py` loads the authoritative
`~/.hermes/config.yaml` with a helper that only catches
`FileNotFoundError`.

Therefore:

- syntactically malformed YAML raises out of discovery;
- a valid YAML list/string later crashes on `cfg.get(...)`;
- no fresh snapshot is written;
- the previous snapshot remains on disk;
- `integration-discover-wrapper.sh` logs the inner non-2 exit and returns 0;
- the operator receives no degradation alert.

Current failure shape:

```text
malformed config
 -> discover crash
 -> stale snapshot remains
 -> wrapper looks successful
 -> no operator alert
```

## R2a selected state model

Do **not** map malformed config to an empty dict and diff it against last good.
That would create false mass-removal events.

The preferred bounded model is:

```text
preserved last-good inventory
+
explicit top-level discovery status
```

A degraded attempt must distinguish:

- current failed attempt time;
- last successful observation time;
- stable reason code;
- preserved last-good entities.

On recovery, the valid inventory is diffed against the preserved last-good
inventory so genuine changes are reported once and malformed-state gaps do not
create remove/add storms.

## Consumer boundary

A degraded snapshot is not live inventory.

At minimum:

- `health-check-v2.py` must fail closed before network/subprocess checks;
- `ai-deep-check.py` must fail closed before curl.

For health-check-v2, existing exit 2 is the natural configuration-error path;
its wrapper already avoids processing stale health reports on that path.

## Operator semantics

Prefer the existing discover process contract:

```text
0 = no operator-visible change
2 = reportable entity/discovery-state transition
```

Entering degradation and recovering may use the existing reportable path rather
than introducing a new systemd exit code. Repeated identical degradation must
not alert every cron cycle.

## Global non-goals for R2a

- Hermes runtime imports;
- YAML repair/normalization;
- R2c `fallback_providers`;
- generic provenance/config frameworks;
- new state database/sidecar architecture;
- installer/i18n work;
- plugin/provider execution;
- multi-profile implementation;
- unrelated cleanup.

## Workflow

```text
one R2a implementation pass
 -> one focused Pytna review
 -> at most one remediation
 -> exact-head reread
 -> merge OR blocker
```

Production deploy remains a separate maintainer action.
