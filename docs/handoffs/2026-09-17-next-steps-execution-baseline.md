# 2026-09-17 next-steps execution baseline

Status: **ACTIVE EXECUTION BASELINE — UPDATED 2026-09-24**

## Architecture invariant

```text
Hermes owns runtime truth.
Argus observes externally, verifies independently where useful, and makes failures loud.
```

## Exact current baseline

```text
Argus main = 5c38fa2381a11974d5b3691def8b5c7fa7849f81

R1c / PR #42 = DONE
R2a / PR #44 = DONE
R2a.1 + baseline follow-up / PR #47 = DONE
PR #47 candidate = 25601493e9bd2986b09f55a82dbe9837843bf30c
CI #92 = success
probes = 133/133
swap tests = 8/8

R2c.1 = NOW
```

Maintainer production rollout of the accepted R1c/R2a/R2a.1 batch completed
successfully after the final gate.

## Hermes authority

```text
stable = v2026.9.21 / v0.21.4
stable tag commit = d337b736aa1e8ebecfab043842d13e4a2d2f48a3
warning-source main = 35b14ad5e24137b836d5c47c21a50c6ea7aeb785
```

Stable is authoritative. Main is a warning/research source.

## Current selected contract

```text
docs/handoffs/r2c-static-discovery-compat-contract.md
```

## Demonstrated R2c.1 gap

Current Argus inventories only:

```text
cfg.fallback_model -> model:fallback
```

Supported Hermes stable defines the effective top-level chain as:

```text
fallback_providers first, preserving order
then fallback_model
dedupe by lower(provider), lower(model), lower(normalized base_url)
```

The stable fallback CLI persists the canonical chain under
`fallback_providers` and removes `fallback_model`.

Therefore current valid Hermes configurations can hide every canonical fallback
rung from Argus inventory.

## Main-only warning source

Current upstream main keeps the stable `get_fallback_chain()` semantics but
adds `scoped_fallback_chain()` for route owners such as delegated children and
cron jobs.

Do not chase that in R2c.1. Scoped/auxiliary coverage remains R2c.2 after RC.

## Release order

```text
R2c.1 NOW
 -> RR0 legacy/personal-dependency reduction
 -> RR1 installer/dependency/managed-cron
 -> RR2 runtime i18n en+ru
 -> RR3 release acceptance
 -> v0.1.0-rc.1
```

## Workflow

```text
Builder implementation
 -> Focused reviewer
 -> at most one remediation
 -> Maintainer exact-head reread
 -> merge OR blocker
```

Production deploy remains a separate maintainer action.
