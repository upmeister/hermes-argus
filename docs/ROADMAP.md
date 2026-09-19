# Roadmap

This is the public, product-facing roadmap for hermes-argus.

Detailed implementation contracts live under `docs/handoffs/`. A roadmap item
is not permission to pull adjacent work into the same PR.

## Design principles

1. **Hermes owns runtime truth.** Argus observes externally and independently;
   it does not become a second provider/credential/runtime resolver.
2. **Failures must be loud without becoming false-green.** Missing evidence,
   unknown state and static credential presence are not silently promoted to
   health.
3. **Secret handling is part of correctness.** Monitoring must not expose the
   credentials it is trying to verify.
4. **Public installation is a product surface.** Installer, cron/systemd
   ownership, upgrade and uninstall behavior need tests just like monitoring
   code.
5. **Prefer bounded compatibility to mirroring Hermes internals.** Track
   stable external seams and documented config where useful; do not chase every
   upstream implementation detail.
6. **Runtime localization and documentation are separate concerns.** Runtime
   operator UI will support English and Russian; project documentation remains
   English-only.

## Completed foundation

### Monitoring core

- integration discovery from Hermes config/environment/static auth evidence;
- schema-v2 health reports with explicit evidence/verdict semantics;
- external HTTP/MCP/integration checks;
- fallback cascade observation and recovery tracking;
- systemd/process/network/resource watchdogs;
- bounded auto-remediation and memory-limit drop-ins;
- Telegram alert/control-plane integration;
- optional external dead-man heartbeat backends.

### Stabilization and account-auth phase

Completed work includes:

- deployment/GitHub heartbeat secret-in-argv hardening;
- Telegram child-argv secret hardening;
- generic static account-auth discovery including nested/pool-only Codex;
- elimination of false-green "logged in" semantics for static OAuth evidence;
- user-facing OAuth evidence rendering;
- final OA acceptance.

OA2 — consuming Hermes-owned account status dynamically — remains
**closed/upstream-gated** until Hermes exposes a stable machine-readable,
refresh-free, no-secret status seam suitable for monitoring.

## Current path to the first public release

```text
R1c  Authorization-header argv debt
 -> R2a  malformed YAML fail-safe
 -> R2c.1  canonical fallback_providers inventory
 -> RR1  installer/dependency/managed-cron hardening
 -> RR2  runtime i18n (English + Russian)
 -> RR3  clean-install/upgrade/uninstall/release acceptance
 -> v0.1.0-rc.1
 -> soak
 -> v0.1.0
```

## R1c — Authorization headers out of child argv

Current stage.

Known active authenticated curl paths must deliver Authorization values without
putting them in child process arguments. Existing Telegram secret-URL handling
must remain safe.

Implementation contract:
[docs/handoffs/r1c-authorization-header-argv-contract.md](handoffs/r1c-authorization-header-argv-contract.md).

## R2a — malformed YAML fail-safe

A malformed Hermes `config.yaml` must become explicit degraded/partial
observation, not a traceback, silently empty healthy inventory, or stale state
that looks fresh.

## R2c.1 — canonical fallback chain compatibility

Before the RC, update only the demonstrated static config drift:

- prefer ordered `fallback_providers`;
- retain bounded legacy `fallback_model` compatibility;
- keep static config distinct from actual runtime route truth.

Broader auxiliary-role expansion moves after the RC unless a concrete incident
promotes it.

## RR1 — public installation contract

The repository already has a clean-Ubuntu bootstrap, but the public install path
still needs product-grade ownership semantics.

Release goals:

- managed, idempotent Argus cron block;
- dependency preflight for enabled modules;
- ordinary sudo/install ergonomics;
- Hermes/version/home preflight;
- private secret-config permissions;
- no shell mismatch in cron jobs;
- version-pinned stable install with an explicit edge channel;
- safe update and uninstall that remove only Argus-owned resources.

The likely distribution is a versioned GitHub Release rather than a Python/apt
package.

## RR2 — runtime localization

Public release requires at least:

```text
en
ru
```

The maintainer production deployment currently uses Russian and must remain
supported without a surprise language flip on upgrade.

Localization applies to human-facing runtime/operator surfaces such as bot
messages, alerts and status text. Machine-readable schemas and parser-facing
markers remain language-neutral.

The README and project documentation remain English-only. There is no plan for
a duplicated Russian documentation tree.

## RR3 — release acceptance

Before `v0.1.0-rc.1`:

- installer/deploy syntax and smoke tests run in CI;
- clean Ubuntu 24.04 install from a versioned artifact/tag is rehearsed;
- re-run/upgrade is idempotent;
- uninstall is bounded to Argus-owned state;
- default modules reach useful operation without undocumented manual dependency
  steps;
- release notes/changelog/compatibility target are explicit.

The first public tag should be a GitHub pre-release. Stable `v0.1.0` follows
after a short real-world soak.

## After the first RC

### R2c.2 — bounded auxiliary-role coverage

Add auxiliary configuration only when it materially improves operator
understanding or a real incident demonstrates the gap.

### R3 — reduction and stabilization

Delete stale compatibility/dead paths, simplify accumulated personal-era
assumptions, and tighten the public v0.1 surface.

### Separate tracks

- multi-profile monitoring remains its own MP0-MP5 track;
- gateway-liveness redesign remains deferred;
- OA2 remains upstream-gated research.

## Hermes upstream policy

Argus targets supported Hermes stable behavior first and treats upstream
`main` as a warning/research source.

As of the 2026-09-20 watch:

- supported stable remains Hermes Agent v0.21.3 / `v2026.9.14`;
- fresh upstream is increasingly separating read-only account observation from
  credential mutation;
- Codex status is now explicitly read-only, Nous has a refresh-free local
  snapshot and xAI avoids refresh-on-status;
- Qwen still refresh-validates;
- the OAuth dashboard response still exposes token previews and lacks the
  suitable machine-authenticated no-secret endpoint required by OA2;
- credential-pool logic continues to grow substantially more complex.

That direction reinforces the core boundary: Argus should consume stable
observation seams when they exist, not duplicate Hermes credential logic.

## Release threshold

A public RC is ready when known blockers are ordinary post-release feature work,
not known installation, secret-boundary or fail-safe correctness defects.

Current posture:

```text
monitoring core: proven in maintainer production
clean-VM bootstrap: previously rehearsed
distribution contract: incomplete
public RC: close, gated by the stages above
```
