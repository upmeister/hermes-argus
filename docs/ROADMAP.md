# Roadmap

This is the public, product-facing roadmap for hermes-argus.

Detailed implementation contracts live under `docs/handoffs/`. A roadmap item
is not permission to pull adjacent work into the same PR.

## Design principles

1. **Hermes owns runtime truth.** Argus observes externally and independently;
   it does not become a second provider/credential/runtime resolver.
2. **Failures must be loud without becoming false-green.**
3. **Secret handling is part of correctness.**
4. **Public installation is a product surface.**
5. **Prefer bounded compatibility to mirroring Hermes internals.**
6. **Runtime localization and documentation are separate concerns.** Runtime UI
   will support English and Russian; project documentation remains English-only.
7. **Default modules must be internally truthful.** A clean default install
   must not depend on optional or historical components that were not installed.

## Completed foundation

Completed release gates include:

- R1a deploy/GitHub-heartbeat secret-in-argv hardening;
- R1b Telegram child-argv secret hardening;
- OA static account-auth discovery and false-green correction;
- OA1b user-facing auth-evidence rendering;
- OA-close;
- R1c Authorization headers out of child argv;
- R2a fail-safe malformed YAML discovery.

OA2 remains **closed/upstream-gated**.

## Current path to first public release

```text
R1c  Authorization-header argv debt                 DONE / PR #42
 -> R2a  malformed YAML fail-safe                    DONE / PR #44
 -> R2c.1  canonical fallback_providers inventory    NOW
 -> RR0  legacy/personal-dependency reduction
 -> RR1  installer/dependency/managed-cron hardening
 -> RR2  runtime i18n (English + Russian)
 -> RR3  clean-install/upgrade/uninstall/release acceptance
 -> v0.1.0-rc.1
 -> soak
 -> v0.1.0
```

After the first RC:

```text
R2c.2 bounded auxiliary-role coverage
 -> low-risk archive/docs cleanup as ordinary maintenance
```

## R2a — completed

PR #44 made discovery fail-safe for malformed/unreadable config:

- preserves last-good inventory;
- marks discovery degraded without false mass removals;
- reports bounded degradation/recovery transitions;
- makes health/deep consumers fail closed on degraded inventory.

Accepted candidate `6241543d...` passed 131/131 probes + 8/8 swap tests.
All six changed blobs match merged main `7b78e936...`.

## R2c.1 — current stage

Supported Hermes stable already defines the canonical fallback chain:

```text
fallback_providers first, preserving order
then legacy fallback_model
dedupe by provider/model/base_url
```

Hermes CLI writes `fallback_providers` and removes the legacy key.

Argus currently inventories only one legacy `fallback_model`, so current
canonical fallback chains can be invisible.

R2c.1 fixes that static inventory gap only. It does not alter runtime fallback
tracking or expand auxiliary/delegation/MoA coverage.

Implementation contract:
[docs/handoffs/r2c-static-discovery-compat-contract.md](handoffs/r2c-static-discovery-compat-contract.md).

## RR0 — pre-release legacy/personal-dependency reduction

The 2026-09-21 audit found release-affecting historical coupling that cannot
wait until after RC.

High-value findings include:

- watchdog calls a non-existent historical `~/scripts/check-integrations.sh`;
- default CORE self-health depends on default-OFF ANALYZER state;
- self-health requires TG bot and Netdata although they are optional/uninstalled
  by the default bootstrap;
- GH heartbeat deploy uses `~/.hermes/gh-heartbeat` while runtime paths still
  use historical `~/.hermes/hermes-infra`;
- personal GitHub/proxy/old-kit defaults remain;
- some deployed code has no live caller or is explicitly superseded.

RR0 is a release gate, but it must be implemented in focused slices rather than
one broad refactor.

Research:
[pre-release legacy audit](research/2026-09-21-pre-release-legacy-audit.md).

## RR1 — public installation contract

After RR0 defines the truthful live module surface:

- managed, idempotent Argus cron block;
- dependency preflight for enabled modules;
- interactive sudo/install ergonomics;
- Hermes/version/home preflight;
- private secret-config permissions;
- version-pinned stable install with explicit edge channel;
- safe update/uninstall;
- migration of any renamed Argus-owned resources.

## RR2 — runtime localization

Public release requires at least:

```text
en
ru
```

The current Russian production experience remains supported. Existing installs
must not silently flip language on upgrade. README/docs remain English-only.

## RR3 — release acceptance

Before `v0.1.0-rc.1`:

- installer/deploy smoke tests run in CI;
- clean Ubuntu 24.04 install from a versioned artifact/tag is rehearsed;
- default module set reaches useful operation without historical hidden state;
- re-run/upgrade is idempotent;
- uninstall removes only Argus-owned resources;
- release notes/changelog/compatibility targets are explicit.

## Hermes upstream policy

Argus targets supported Hermes stable behavior first and treats upstream
`main` as a warning/research source.

2026-09-21 snapshot:

```text
stable = v2026.9.14 / v0.21.3
warning-source main = 64c7da592d43a9f155ea8606865d9ae1eda3222b
main advanced 951 commits since the previous f88c6fc4 watch
```

Relevant convergence:

- stable and main share the same canonical fallback chain semantics used by
  R2c.1;
- the runtime restore marker consumed by Argus is unchanged;
- fresh-main `hermes mcp test` now has useful non-zero failure/missing-server
  exits while retaining current output markers.

Keep current MCP marker parsing until a supported stable bump.

OA2 remains closed: Qwen status still refresh-validates, OAuth status cards
still carry `token_preview`, and `/api/providers/oauth` is not registered on
the generic token-auth route seam.

## Release threshold

```text
monitoring core: proven
R1c: closed
R2a: closed
R2c.1: current
RR0: required before installer hardening
distribution contract: incomplete
public RC: gated by R2c.1 + RR0 + RR1/RR2/RR3
```
