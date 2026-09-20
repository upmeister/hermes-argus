# 2026-09-17 next-steps execution baseline

Status: **ACTIVE EXECUTION BASELINE — UPDATED 2026-09-21**

## Exact current baseline

```text
Argus main = 7b78e9369be72d9a5f08de267ccfc62604710f79

R1c / PR #42 = DONE
R2a / PR #44 = MERGED / FOLLOW-UP REQUIRED
R2a candidate = 6241543d96e93cfbe197706dcbf316fbbc72b58d
R2a CI #86 = success
R2a probes = 131/131
R2a swap tests = 8/8

R2a baseline-degradation follow-up = NOW
R2c.1 = PREPARED / HOLD
```

Hermes authority:

```text
stable = v2026.9.14 / v0.21.3
warning-source main = 5171ea18dc4b699e14f0092388be326dc4fc81ab
```

## Remaining R2a blocker

Final exact-tree review found one P2 not covered by the 131-probe suite:

```text
malformed config
 -> integration-discover.py --baseline
 -> degraded snapshot written
 -> discovery_degraded suppressed
 -> exit 0

same malformed config next normal run
 -> already degraded / same reason
 -> no event
 -> exit 0
```

This violates the accepted rule that the first `ok -> degraded` transition is
reportable. Baseline may suppress entity diff, not discovery-state transitions.

Current contract:

```text
docs/handoffs/r2a-baseline-degradation-followup-contract.md
```

## Release order

```text
R2a baseline follow-up NOW
 -> R2c.1 PREPARED / HOLD
 -> RR0 legacy/personal-dependency reduction
 -> RR1 installer/dependency/managed-cron
 -> RR2 runtime i18n en+ru
 -> RR3 release acceptance
 -> v0.1.0-rc.1
```

R2c.1 docs/research may be prepared, but implementation is not active until
R2a closes.

## RR0 decision

The pre-release audit found release-affecting historical coupling, so the old
post-RC cleanup concept is split:

- release-affecting runtime/default/personal dependency cleanup -> **RR0 before RR1**;
- archive-only/cosmetic cleanup -> after RC / ordinary maintenance.

Key RR0 inputs include the missing `check-integrations.sh` caller, default CORE
depending on optional ANALYZER/TG/Netdata state, the GH heartbeat path split,
personal proxy/GitHub defaults, and deployed dead/duplicate surfaces.

## Workflow

```text
one focused R2a follow-up
 -> one Pytna verification
 -> exact-head reread
 -> R2a close OR blocker
```

Production deploy remains a separate maintainer action.
