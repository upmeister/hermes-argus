# RR1b contract — module dependency truth and payload completeness

Status: **IN PROGRESS / BUILDER IMPLEMENTING**

Maintainer confirmed work in progress on 2026-10-04. Acceptance scope is frozen;
no implementation review PASS, merge or deployment is implied by this status.

This is the selected next task after RR1a. The documentation PR containing this
contract may merge; implementation still requires a builder task branch/PR and
separate maintainer merge authority.

## Authority and delivery

Implementation baseline after RR1a and its status sync:

```text
ed3661f (PR #69 status sync; resolve fresh main before coding)
RR1a implementation = PR #68 / 9aaf0a5
```

Research authority:

- [`docs/research/2026-10-03-production-deployment-dependencies.md`](../research/2026-10-03-production-deployment-dependencies.md);
- [`docs/monitoring-sources.md`](../monitoring-sources.md);
- [`docs/BACKLOG.md`](../BACKLOG.md), DEBT-007 and DEBT-008;
- current source templates and manifests at implementation time.

Focused reviewer: **Codex**.

Production risk: **high** — the patch changes health classification and
optional-module deployment behavior.

Merge authority: **maintainer merge after reviewer PASS**. Production deploy
remains separately authorized.

## Decision table

| ID | Evidence | Required behavior | Acceptance scenario |
| --- | --- | --- | --- |
| B1 | Quick compatibility check and watchdog UI treat missing Netdata/GitHub as a failure even when no optional surface is configured | Absence is neutral/unconfigured; an explicitly present/expected dependency that fails remains visible | Clean CORE+INTEGRATIONS fixture with no Netdata/GitHub does not emit a false failure; configured broken fixtures do |
| B2 | `health-analyzer.py` reads `~/.hermes/scripts/collect-metrics.sh`, while the current manifest installs the source collector elsewhere | Analyzer owns one real collector path and distinguishes collector failure from a clean scan | ANALYZER-only fixture runs from a fresh deploy; missing/nonzero collector cannot update a falsely healthy state |
| B3 | Discord imports `webhook.py`, while that shared file is currently deployed through TG_BOT; its isolated interpreter has separate imports | Discord-only install receives its shared handler and every import it actually uses, with a clear missing-prerequisite result | `MODULE_DISCORD_BOT=ON`, `MODULE_TG_BOT=OFF` fixture imports/starts handler surface without relying on an old production copy |
| B4 | `install.sh` has a CORE-specific post-deploy syntax gate that runs even when CORE is OFF | Bootstrap/post-deploy checks are module-neutral and only inspect enabled/deployed surfaces | CORE=OFF fresh install reaches its selected modules without looking for a missing watchdog |

The acceptance target is truthful module behavior, not installing every
optional service on every host.

## Scope

### B1 — optional Netdata/GitHub expectation truth

Make the existing quick-check and watchdog status path distinguish:

- not configured / absent optional surface — neutral `unconfigured`/informational
  output, with no false incident;
- configured or otherwise explicitly expected surface — its transport/semantic
  failure remains reportable;
- configured healthy surface — existing success output is preserved.

Use existing configuration, module state and installed-service evidence where
it is unambiguous. Do not invent a generic dependency registry or silently
make Netdata mandatory. If a correct expectation predicate cannot be derived
without a new config knob, stop and report that decision instead of adding it
in the implementation pass.

Preserve the watchdog's OS/procfs disk, RAM, swap and process evidence. Netdata
trend reads remain Analyzer-only and optional.

### B2 — Analyzer collector ownership

Choose one canonical owner path for the existing `collect-metrics.sh` and make
the Analyzer manifest/consumer agree. Do not deploy two silently competing
copies. On missing, non-executable or nonzero collector execution, the
Analyzer must produce explicit failure evidence or refuse the state update;
empty output must not become a clean issue scan.

Keep the existing `health-state.json` schema unless a schema change is
unavoidable; if it is unavoidable, stop for maintainer scope review. This
contract does not create the Hermes L3 agent job, choose a model, or configure
delivery.

### B3 — Discord-only payload and interpreter

Make shared handler ownership explicit so `MODULE_DISCORD_BOT=ON` does not
depend on `MODULE_TG_BOT=ON` or on a stale installed file. Check the actual
interpreter used by the Discord unit for imports required by the exercised
handlers. Treat `python3-venv` as a preflight/install prerequisite if the
existing venv creation path needs it; do not add a second Python environment.

Do not redesign the handler library or Discord command surface. Preserve
Telegram behavior and the existing opt-in/default-off policy.

### B4 — module-neutral bootstrap gate

The install post-deploy syntax/marker checks must follow the selected module
manifests. A disabled CORE cannot make a clean install fail because its
watchdog is absent. Enabled modules still receive their required syntax and
marker checks; a missing enabled artifact remains a loud failure.

## Explicit non-goals

- installing Netdata, smart-proxy/tunnel infrastructure, Docker, Fail2ban or
  Hermes itself;
- native Netdata alert configuration or Cronping/DMS/GitHub heartbeat delivery;
- the Cronping -> bot Argus receiver;
- Hermes L3 job/model/prompt/destination setup;
- versioned release/update, uninstall or resource migration;
- full-mode `health-check-integrations.sh` disposition (DEBT-004);
- Telegram proxy propagation (DEBT-013);
- heartbeat token-in-argv correction (DEBT-014);
- runtime i18n, R2c.2 or OA2;
- a general dependency registry/plugin framework.

## Required red-capable probes

1. Quick check: absent Netdata and absent GitHub token are neutral; configured
   broken Netdata/GitHub remain visible; healthy configured paths remain healthy.
2. Watchdog status: missing Netdata is informational; an expected broken
   Netdata service/API remains visible.
3. Analyzer fresh deploy: collector is present at the chosen path and runs;
   collector missing/nonzero cannot update a clean `health-state.json`.
4. Discord-only fresh deploy: `webhook.py` and all exercised imports resolve
   under the unit interpreter with TG_BOT disabled.
5. CORE=OFF installer: no CORE-only file is required by the post-deploy gate;
   enabled module files still receive checks.
6. Existing default module behavior and secret/marker/argv probes remain green.

Prove B1, B2, B3 and B4 regressions RED against the pre-contract baseline,
then GREEN on the candidate. Use isolated fixtures; do not read production
secrets, send live notifications or rely on old installed copies.

## Receipt and review

Builder receipt must include exact baseline/head, decision table mapping,
chosen expectation predicates, canonical collector/shared-file owners, RED
evidence, fixture results, standard checks/CI, changed files, out-of-scope
findings and `Production actions: None`.

Reviewer prioritizes false-green optional dependency handling, stale-copy
masking, Discord-only import failures, Analyzer empty-output success, disabled
CORE gate assumptions, new configuration/dependency sprawl and heartbeat/RR1c
scope creep. Return `PASS-TO-MAINTAINER`, `REMEDIATE` or
`BLOCKED-FOR-MAINTAINER`; at most one remediation pass.
