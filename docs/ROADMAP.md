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
5. **Prefer bounded stable compatibility to mirroring Hermes internals.**
6. **Runtime localization and documentation are separate concerns.** Runtime UI
   will support English and Russian; project documentation remains English-only.
7. **Default modules must be internally truthful.** A clean default install
   must not depend on optional or historical components that were not installed.

## Completed release gates

Completed work includes:

- R1a deploy/GitHub-heartbeat secret-in-argv hardening;
- R1b Telegram child-argv secret hardening;
- OA static account-auth discovery and false-green correction;
- OA1b user-facing auth-evidence rendering;
- OA-close;
- R1c Authorization headers out of child argv;
- R2a fail-safe malformed authoritative config discovery;
- R2a.1 community plugin metadata shape hardening and the baseline-transition
  follow-up.

R2a/R2a.1 final batch:

```text
PR #47 reviewed candidate = 25601493e9bd2986b09f55a82dbe9837843bf30c
merged main              = 5c38fa2381a11974d5b3691def8b5c7fa7849f81
CI #92                    = success
probes                    = 133/133
watchdog swap tests       = 8/8
changed blobs             = exact candidate -> merged match
```

OA2 remains **closed/upstream-gated**.

## Current path to first public release

```text
R1c  Authorization-header argv debt                 DONE / PR #42
 -> R2a/R2a.1 fail-safe discovery hardening         DONE / PR #44 + #47
 -> R2c.1 canonical fallback_providers inventory    NOW
 -> RR0 legacy/personal-dependency reduction
 -> RR1 installer/dependency/managed-cron hardening
 -> RR2 runtime i18n (English + Russian)
 -> RR3 clean-install/upgrade/uninstall acceptance
 -> v0.1.0-rc.1
 -> soak
 -> v0.1.0
```

After the first RC:

```text
R2c.2 bounded scoped/auxiliary fallback coverage
 -> low-risk archive/docs cleanup as ordinary maintenance
```

Separate/deferred:

- R2b gateway-liveness redesign;
- MP0-MP5 multi-profile monitoring;
- OA2 dynamic account-status shadow.

## R2c.1 — current stage

Hermes stable `v0.21.4 / v2026.9.21` now directly defines the canonical
top-level fallback-chain semantics Argus needs to inventory:

```text
fallback_providers first, preserving order
+ legacy fallback_model afterwards
+ dedupe by provider/model/normalized base_url
```

The stable CLI writes only `fallback_providers` and removes the legacy key.

Argus currently inventories only one legacy `fallback_model`, so a normal
current Hermes fallback chain can remain invisible.

R2c.1 is deliberately static and top-level only:

- preserve canonical chain order;
- retain bounded legacy compatibility;
- preserve enough route identity for deterministic change detection;
- never serialize inline credentials or secret URL material;
- no Hermes imports, provider/plugin execution, auth resolution, network or
  subprocess work;
- no runtime fallback-tracker rewrite;
- no main-only scoped/delegation/cron fallback mirroring.

Implementation contract:
[docs/handoffs/r2c-static-discovery-compat-contract.md](handoffs/r2c-static-discovery-compat-contract.md).

## RR0 — pre-release legacy/personal-dependency reduction

The pre-release audit found release-affecting historical coupling that should be
removed before installer hardening.

High-value findings include:

- watchdog calls a non-existent historical `~/scripts/check-integrations.sh`;
- default CORE self-health depends on default-OFF ANALYZER state;
- self-health requires TG bot + Netdata although they are optional/uninstalled
  by the default bootstrap;
- GH heartbeat deploy uses `~/.hermes/gh-heartbeat` while runtime paths still
  inspect historical `~/.hermes/hermes-infra`;
- personal GitHub/proxy/old-kit defaults remain;
- some deployed code/settings have no demonstrated live owner.

RR0 is a release gate but must be split into focused contracts rather than an
omnibus refactor.

Research:
[pre-release legacy audit](research/2026-09-21-pre-release-legacy-audit.md).

## RR1 — public installation contract

After RR0 defines the truthful live module surface:

- managed, idempotent Argus cron block;
- dependency preflight for enabled modules;
- interactive sudo/install ergonomics or an explicit noninteractive contract;
- Hermes/version/home preflight;
- private permissions for secret-bearing config;
- version-pinned stable install with explicit edge channel;
- safe update/uninstall;
- migration of any renamed Argus-owned resources.

## RR2 — runtime localization

Runtime/operator UI must support at least:

```text
en
ru
```

Existing Russian production must not silently change language on upgrade.
Machine-readable schemas and parser-facing markers remain language-neutral.
README/docs remain English-only.

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

2026-09-24 authority:

```text
stable = v2026.9.21 / v0.21.4
stable tag commit = d337b736aa1e8ebecfab043842d13e4a2d2f48a3
warning-source main = 35b14ad5e24137b836d5c47c21a50c6ea7aeb785
main is ~1413 commits ahead of the stable tag at this watch
```

Stable findings relevant to Argus:

- canonical top-level fallback-chain semantics are now supported stable;
- `hermes mcp test` now returns 0 on connect, 1 on connection failure and 3
  when the server is absent, while retaining the output markers Argus parses;
- the runtime restore marker consumed by Argus remains
  `Primary runtime restored for new turn: ...`.

Warning-source main keeps the same `get_fallback_chain()` behavior but adds a
new `scoped_fallback_chain()` policy for pinned/unpinned route owners such as
delegated children and cron jobs. That is not R2c.1 authority and remains
post-RC R2c.2 research.

OA2 remains closed in both stable and the watched main:

- Qwen status still refresh-validates;
- OAuth status cards still include `token_preview`;
- the read-only `/api/providers/oauth` listing still lacks the required
  machine-authenticated no-secret monitoring seam.

Full watch:
[2026-09-24 Hermes upstream watch](research/2026-09-24-hermes-upstream-watch.md).

## Release threshold

```text
monitoring core: proven in maintainer production
R1c: closed
R2a/R2a.1: closed and deployed
R2c.1: current compatibility gate
RR0: required before installer hardening
distribution contract: incomplete
public RC: gated by R2c.1 + RR0 + RR1/RR2/RR3
```
