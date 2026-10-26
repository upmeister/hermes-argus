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
 -> R2c.1 canonical fallback_providers inventory    DONE / PR #49
 -> RR0a default-module/runtime truth               DONE / PR #51
 -> RR0b dead/duplicate runtime removal             DONE / PR #63
 -> RR0c public defaults/naming migration            DONE / PR #65
 -> RR1a managed cron ownership                     DONE / PR #68
 -> RR1b module/runtime truth                         DONE / PR #71
 -> RR1b host readiness                          DONE / PR #75
 -> A Hermes 0.22.5 compatibility        DONE / PR #77
 -> B delivery/evidence correctness        DONE / PR #78
 -> production reconciliation / authorized rollout    DONE / 2026-10-26
 -> C RR1c + RR1d versioned lifecycle            IMPLEMENTED / maintainer gate pending
 -> RR2 runtime i18n (English + Russian)
 -> RR3 clean-install/upgrade/uninstall acceptance
 -> v0.1.0-rc.1
 -> soak
 -> v0.1.0
```

R2c.1 is confirmed against Hermes stable `v0.21.5 / v2026.9.24` — see the
2026-10-01 upstream watch.

After the first RC:

```text
R2c.2 bounded scoped/auxiliary fallback coverage
 -> low-risk archive/docs cleanup as ordinary maintenance
```

R2c.2's scope rationale changed on 2026-10-01: `scoped_fallback_chain()` is now
a **stable** Hermes seam (introduced by `e7bff4b6d831`, #120312), not
warning-source main only. It remains post-RC, but it is now bounded stable
compatibility work rather than unstable-main mirroring.

Separate/deferred:

- R2b gateway-liveness redesign;
- MP0-MP5 multi-profile monitoring;
- OA2 dynamic account-status shadow.

## R2c.1 — complete

Hermes stable `v0.21.4 / v2026.9.21` (and unchanged in `v0.21.5 / v2026.9.24`)
directly defines the canonical top-level fallback-chain semantics Argus
inventories:

```text
fallback_providers first, preserving order
+ legacy fallback_model afterwards
+ dedupe by provider/model/normalized base_url
```

The stable CLI writes only `fallback_providers` and removes the legacy key.

R2c.1 was deliberately static and top-level only:

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

Landing: **PR #49**, merged 2026-09-24 into `main`
(`7d6fcf8940c26625103c78004fe69ba65fab4ccb`). The 2026-10-01 upstream watch
re-verified `get_fallback_chain()` at stable `v0.21.5`: semantics are
unchanged, so the shipped inventory needs no rework.

## RR0 — pre-release legacy/personal-dependency reduction

The pre-release audit found release-affecting historical coupling that should be
removed before installer hardening.

Historical audit findings included:

- watchdog calls a non-existent historical `~/scripts/check-integrations.sh`;
- default CORE self-health depends on default-OFF ANALYZER state;
- self-health requires TG bot + Netdata although they are optional/uninstalled
  by the default bootstrap;
- GH heartbeat deploy uses `~/.hermes/gh-heartbeat` while runtime paths still
  inspect historical `~/.hermes/hermes-infra`;
- personal GitHub/proxy/old-kit defaults remain;
- some deployed code/settings have no demonstrated live owner.

RR0 is a release gate split into three focused contracts rather than an
omnibus refactor:

1. **RR0a — default-module/runtime truth — DONE / PR #51.** The default
   watchdog no longer requires optional Analyzer, Telegram bot, unmanaged
   Netdata, historical integration-checker paths, or a legacy heartbeat
   directory. Existing legacy heartbeat compatibility remains bounded.
2. **RR0b — dead/duplicate runtime removal — DONE / PR #63.** C2/C3/C4
   resolved: the unused CORE report sender, the legacy fallback tracker, and
   the dead `HERMES_BOT_*`/`DMS_API_KEY` substitutions are gone; retained
   settings have proven live consumers. C1 (full integration-check mode) is
   retained by the contract's uncertainty rule and recorded as backlog
   DEBT-004 pending maintainer verification of the live crontab.
3. **RR0c — public defaults and naming migration — DONE / PR #65.** Proxy
   choice and GitHub ownership are explicit; canonical resource names preserve
   a bounded operator-controlled legacy handoff. Maintainer reports deployment;
   the current checkout and installed wiring were inspected on 2026-10-03.

RR0 completion does not prove that the full production monitoring environment
is reproducible from a clean install. The remaining external dependencies and
masked module-wiring gaps are recorded by the
[production dependency audit](research/2026-10-03-production-deployment-dependencies.md)
and admitted through RR1, not an unbounded reopening of RR0.

Research:
[pre-release legacy audit](research/2026-09-21-pre-release-legacy-audit.md).

Contracts:

- [RR0a default-module/runtime truth](handoffs/rr0a-default-module-runtime-truth-contract.md) — complete;
- [RR0b dead/duplicate runtime removal](handoffs/rr0b-dead-runtime-removal-contract.md) — complete (PR #63);
- [RR0c public defaults/naming migration](handoffs/rr0c-public-defaults-naming-migration-contract.md) — complete (PR #65).

The canonical gateway matcher fix in **PR #60** is merged maintenance that
keeps watchdog and gateway liveness aligned with the current Hermes startup
shape. The broader R2b gateway-liveness redesign remains deferred.

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

The maintainer-selected sequence is:

1. **RR1a — managed cron ownership — DONE / PR #68.** One owned block,
   in-place replacement preserving operator cron and cron environment
   variables, adoption of previously generated lines, and retirement of
   the whole-user count heuristic and backup restore.
   [Builder contract](handoffs/rr1a-managed-cron-contract.md).
2. **RR1b — dependency/preflight/config — first slice DONE / PR #71.** The
   module-runtime truth contract
   (handoffs/rr1b-module-runtime-truth-contract.md) merged
   expectation-aware optional Netdata/GitHub reporting, one canonical Analyzer
   collector with honest failure semantics, shared bot handler payload owned
   independently of TG_BOT with an interpreter import check, and a
   module-neutral installer post-deploy gate. Deployed and read back October 26.
3. **RR1b host readiness — DONE / PR #75**, merged October 6. Private
   config, user-manager/Hermes preflight, explicit network guard and bounded
   Argus log rotation are deployed and read back October 26. The older PR #65
   checkout/customized artifacts found October 25 have been reconciled.
4. **A/B restart compatibility and reliability.** The maintainer selected
   [the programme through RR1](handoffs/2026-10-25-restart-through-rr1.md):
   A adapts Hermes launching and fallback aliases for v0.22.5; B fixes existing
   heartbeat secret channels, proxy propagation and stale Analyzer evidence.
5. **Production checkpoint — DONE, October 26**, separately authorized at
   `17b3975`. [Receipt](DEPLOY_CHECKLIST.md#ops-receipt--2026-10-26): payload,
   cron, guard, rotation, host and service read-back; catalog 401 remains,
   earlier 404 is no longer planned after a config update (not recovered),
   and registry refresh is recorded separately.
6. **C — RR1c/RR1d combined**, versioned install/update and bounded uninstall.
   Implemented in PR #79 from `5551579`, pending the maintainer gate; the Codex
   review receipt is in the PR. The installer selects exact stable/edge/tag
   source and checks old rendered ownership before switching; uninstall plans
   first and retains ambiguous/external resources. No C deployment occurred.
   Its authorized merge is the selected programme's stopping point.

Netdata, operator proxy infrastructure, Telegram/Discord accounts, external
heartbeat policy and the Hermes L3 job have independent setup owners. The
current public baseline must not silently require the maintainer's complete
host stack. These later choices need focused contracts; RR1a installs none of
that infrastructure.

RR1a is merged and deployed at the authorized October 26 target `17b3975`.
Outside-block operator cron was preserved and the managed block read back.
The earlier October 25 marked block alone was not deployment evidence.

Accepted clarification: **Netdata remains an optional external enhancement**
for Analyzer trends, not the source of native watchdog resource metrics.
[Monitoring-source map](monitoring-sources.md). PR #71 resolved the known
quick-check/UI optionality assumptions in source; [DEBT-007](BACKLOG.md#debt-007)
has deployment read-back in the October 26 Ops receipt.

### Restart scope selected on 2026-10-25

The [programme](handoffs/2026-10-25-restart-through-rr1.md) owns the next
three implementation contracts and their sequencing. The old RR1b task pointer
is closed. Public setup, L3 recipe, RR2 and RR3 remain later; no public release
or production operation is authorized by this documentation decision.

Native Cronping Telegram through the provider bot remains selected, without
an Argus receiver or external-VPS prerequisite. Setup/delivery verification
and backend policy remain separate from the existing-sender fixes in B.
See [heartbeat decisions](research/2026-10-03-heartbeat-delivery-roadmap.md).

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

Supported stable behavior wins; upstream main is warning/research only.
The accepted historical authority is `v2026.9.24 / v0.21.5` at
`f97608f178d1ffeca59860195ab7da295f7c8e5f`.

The October 25 watch found published and installed Hermes `v0.22.5` at
`bf0203a794a07aac3ff764972ab9087baa4e4f4e`. Contract A passed and promoted
this target at PR #77 merge; its launcher and alias changes were deployed
October 26. MCP markers, disabled-server semantics and fallback log identities
remain supported. OA2 remains upstream-gated.

[Current watch](research/2026-10-25-hermes-upstream-watch.md),
[seam inventory](research/hermes-argus-seams.md), and
[previous authority receipt](research/2026-10-01-hermes-upstream-watch.md).
R2c.2 remains post-RC and multi-profile support is not admitted by A.

## Release threshold

```text
monitoring core: proven in maintainer production
R1c: closed
R2a/R2a.1: closed and deployed
R2c.1: closed (PR #49) and confirmed against stable v0.21.5
RR0a/RR0b: closed (PR #51 / PR #63)
RR0c: closed (PR #65); maintainer reports deployment
RR1: current distribution gate; RR1a closed (PR #68)
RR1b module/runtime truth: merged PR #71; deployed/read back 2026-10-26
RR1b host readiness: merged PR #75; deployed/read back 2026-10-26
selected programme: A+B+Ops complete -> C (RR1c/d) maintainer gate pending, then stop
distribution contract: incomplete
public RC: gated by RR1/RR2/RR3
```

Deferred findings are tracked in [BACKLOG.md](BACKLOG.md). Production changes
use the [deployment checklist](DEPLOY_CHECKLIST.md).
