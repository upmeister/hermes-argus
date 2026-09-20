# 2026-09-17 next-steps execution baseline

Status: **ACTIVE EXECUTION BASELINE — UPDATED 2026-09-21**

Agents may perform only the named task selected by the maintainer.

## Architecture invariant

```text
Hermes owns runtime truth.
Argus observes externally, verifies independently where useful, and makes failures loud.
```

## Exact current baseline

```text
Argus main = 7b78e9369be72d9a5f08de267ccfc62604710f79

R1a / PR #29 = DONE
R1b / PR #31 = DONE
R1c / PR #42 = DONE
R2a / PR #44 = DONE
OA phase = COMPLETE

R2c.1 = NOW
```

R2a final evidence:

```text
candidate head = 6241543d96e93cfbe197706dcbf316fbbc72b58d
CI #86 = success
131/131 probes
8/8 swap tests
candidate/main changed blobs = identical
```

Pytna's P1 unreadable-config gap and P2 baseline-recovery gap were fixed in the
single remediation.

Hermes authority:

```text
stable = v2026.9.14 / v0.21.3
stable commit = 345cd2b057a452236de401d3534b8502a7465e8d
warning-source main = 64c7da592d43a9f155ea8606865d9ae1eda3222b
```

## Current execution order

```text
R1c DONE
 -> R2a DONE
 -> R2c.1 fallback_providers compatibility NOW
 -> RR0 legacy/personal-dependency reduction
 -> RR1 installer/dependency/managed-cron
 -> RR2 runtime i18n (en + ru)
 -> RR3 release acceptance
 -> v0.1.0-rc.1
 -> soak
 -> v0.1.0

R2c.2 auxiliary coverage                 AFTER RC
OA2 dynamic account status               CLOSED / UPSTREAM-GATED
R2b gateway liveness                     DEFERRED
MP*                                       SEPARATE
```

## Current selected contract

```text
docs/handoffs/r2c-static-discovery-compat-contract.md
```

## R2c.1 demonstrated gap

Current Argus inventories only:

```text
fallback_model -> model:fallback
```

Supported Hermes stable uses:

```text
fallback_providers first, ordered
+ legacy fallback_model afterwards
+ provider/model/base_url dedupe
```

Hermes CLI writes the canonical list and removes the legacy key.

Therefore canonical fallback chains can be invisible to current Argus.

R2c.1 is a pure/static inventory patch. Do not touch runtime fallback tracking,
OA2, RR0 cleanup, installer work or auxiliary-role expansion.

## RR0 finding — context only, not current permission

The pre-release audit demonstrated live personal-era debt including:

- missing `~/scripts/check-integrations.sh` called by watchdog;
- default CORE dependence on optional analyzer/TG/Netdata;
- GH heartbeat `gh-heartbeat` vs historical `hermes-infra` path split;
- personal proxy/GitHub/old-kit defaults;
- deployed dead/duplicate scripts.

This promotes cleanup before RR1, but **R2c.1 must not fix it**.

Research:
`docs/research/2026-09-21-pre-release-legacy-audit.md`.

## 2026-09-21 upstream watch

From `f88c6fc4...` to `64c7da59...`, Hermes main advanced 951 commits;
stable remains v0.21.3.

- stable/main fallback semantics agree with R2c.1;
- restore marker remains compatible;
- fresh-main MCP test exits are more useful but marker parsing stays for stable;
- OA2 remains closed: Qwen refreshes, token previews remain, OAuth route is not
  token-auth registered.

## Workflow

```text
one R2c.1 implementation pass
 -> one focused Pytna review
 -> at most one remediation
 -> exact-head reread
 -> merge OR blocker
```

Production deploy remains a separate maintainer action.
