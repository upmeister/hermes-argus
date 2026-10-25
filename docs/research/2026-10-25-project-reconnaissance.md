# Project reconnaissance — 2026-10-25

Follow-up: the maintainer accepted the restart scope through RR1c/RR1d.
The [programme](../handoffs/2026-10-25-restart-through-rr1.md) now owns the
selected sequence; this report remains the dated evidence, not task authority.

Status: **research and proposed sequencing, not a selected implementation
contract or deployment authorization.** Production was inspected read-only at
the maintainer's request. No service, schedule, configuration or credentials
were changed. The upstream compatibility findings are in the
[companion watch](2026-10-25-hermes-upstream-watch.md).

## What is actually complete

GitHub was refreshed before this audit. `origin/main` is
`f433c531bff935d869e2dd75beaf2a5bfdd200d8`, the merge of
[PR #75](https://github.com/upmeister/hermes-argus/pull/75) on October 6.
The local branch remains `feat/rr1b-host-readiness` at `0c5ab39`; its tracked
tree is identical to that main tree. Its branch name is not current task
authority. Main's required `argus-ci` job passed in
[run 37502441206](https://github.com/upmeister/hermes-argus/actions/runs/37502441206).
No open GitHub issues or published Argus releases were returned at this audit;
the local backlog is still the work ledger.

| Work | Source status | What remains |
| --- | --- | --- |
| R1c, R2a/R2a.1, R2c.1 | Merged | Preserve secret/evidence invariants; new S1 alias drift is separate |
| RR0a/b/c | Merged through PR #65 | Avoid reopening the legacy cleanup as an omnibus task |
| RR1a managed cron | Merged, PR #68 | Verified production convergence is still missing |
| RR1b module/runtime truth | Merged, PR #71 | Deployment/read-back, not another implementation pass |
| RR1b host readiness | Merged, PR #75 | Deployment/read-back; remaining review debts keep their own scope |
| RR1c versioned install/update | Planned | Focused contract still needed |
| RR1d bounded uninstall/migration | Planned | Focused contract still needed |
| RR2 English/Russian runtime UI | Planned | Preserve existing Russian installations; keep parser schemas neutral |
| RR3 release acceptance | Planned | Clean Ubuntu install, upgrade/rerun, uninstall, CI and truthful docs |
| R2c.2 / multi-profile / OA2 | Deferred / separate / upstream-gated | No automatic admission into RC work |

Sources: [release roadmap](../ROADMAP.md), [handoff index](../handoffs/README.md),
[PR #68](https://github.com/upmeister/hermes-argus/pull/68),
[PR #71](https://github.com/upmeister/hermes-argus/pull/71),
[PR #75](https://github.com/upmeister/hermes-argus/pull/75).

## Production is older and partly customized

Read-only SSH inspection confirmed:

- Hermes checkout is `bf0203a794a07aac3ff764972ab9087baa4e4f4e`, tag
  `v0.22.5`, matching the maintainer's recollection.
- Argus checkout is `2588581a27234b6e0be2b38b29e39f29476d328e`, the PR #65
  baseline; neither inspected repository had tracked modifications.
- Installed `integration-discover.py`, `health-check-v2.py`,
  `fallback-tracker-v2.py` and `hermes-gateway-pids.py` exactly match that
  older Argus checkout. The watchdog, heartbeat, network guard and
  watchdog-health shell copies match its templates when placeholder values
  are ignored. Placeholder values were neither printed nor retained.
- Installed `health-check-integrations.sh` does **not** match that old
  template even after placeholder normalization. Its provenance must be
  reconciled before overwriting it.
- A marked Argus cron block is already present, with one occurrence of each
  selected watchdog/gateway/fallback/health-check/Analyzer/network-guard job.
  This does not prove deployment of RR1a's reconciliation implementation.
  The new `argus-logrotate.conf` artifact is absent; that does not establish
  absence of separately administered host log rotation.
- Gateway, dashboard and both inspected bot services are active; the config
  watcher is waiting. Discovery and health-check report files are recent;
  Analyzer state at `logs/health-state.json` is recent too. The cached
  integration report includes failures, so this is not an all-green receipt.
- Legacy Hermes `venv/bin/python` and `venv/bin/hermes` still exist. The live
  gateway command has the checkout path and the `gateway run`/runpy shape.
  Its systemd service has native watchdog supervision disabled
  (`Type=simple`, `WatchdogUSec=0`).

These are sanitized observations, not saved production payloads. The exact
date of the last complete Argus deployment cannot be recovered from a Git
checkout SHA. The supported conclusion is **old checkout and core payload,
with additional runtime customization**, not a clean single-version install.
No provider probes, MCP subprocesses, alert sends, auth refreshes or restarts
were used to obtain this evidence. A service being active and a report being
recent do not certify end-to-end model or notification health.

## Documentation drift is part of the restart cost

The repository's `AGENTS.md`, roadmap and handoff index still say PR #75 is
awaiting review/merge. The vault project card contains a later
PASS-TO-MAINTAINER receipt for `0c5ab39` but still awaits the merge; its opening
summary and canonical roadmap are older again. GitHub proves that merge has
already happened. The seam list still calls disabled MCP handling a gap,
although PR #59 fixed it. `monitoring-sources.md` still describes some
pre-PR-#71 optional-module behavior.

A factual status-reconciliation change should repair the repository pointers
and vault together, linking this report. Preserve historical receipts as
history, distinguish merged from deployed, and do not convert the latest
observed Hermes release into an accepted compatibility promise without
verification. Follow [VAULT-SYNC](../VAULT-SYNC.md) when publishing that change;
successful MCP transport alone is not proof that all vault copies agree.
This reconnaissance records the discrepancy; it does not select the next
contract or rewrite the accepted authority block.

## Proposed execution order

1. **Reconcile status and establish the compatibility target.** Close the
   stale PR #75 pointers; keep the rollout status explicit. Treat Hermes
   v0.22.5 as the candidate to verify, while preserving the old formal
   authority until the compatibility decision is recorded. The six existing
   seams are too narrow: installation/launcher, process/profile identity,
   registry source and log routing belong in future watch coverage.
2. **Resolve the concrete launch-layout mismatch before RR1c.** Hermes's PM
   selects committed dependency generations; Argus preflight, probes and
   service templates assume an in-tree `venv`. Scope a small installation-bound
   launcher adaptation and test it on a clean supported Linux installation.
   Reuse the upstream launch boundary; do not mirror the package manager or
   build a generic compatibility framework. Inventory aliases are a second,
   smaller contract, not a pretext to expand the launcher task.
3. **Close the most valuable existing reliability debts in separate slices.**
   First [heartbeat token-in-argv](../BACKLOG.md#debt-014), then
   [configured proxy propagation](../BACKLOG.md#debt-013), then
   [stale Analyzer evidence](../BACKLOG.md#debt-019). These directly affect
   secret handling, alert delivery and false-green reporting. The production
   report's existing failures merit a separate bounded diagnosis; their cause
   was not established in this read-only inventory.
4. **Rehearse, then deliberately roll out the accumulated changes.** Compare
   installed copies with the intended templates, resolve the modified quick
   checker, preserve operator cron, and decide the existing network guard's
   explicit opt-in. Its scheduled production use would stop if deployment
   blindly adopted the new default OFF. Use the
   [deployment checklist](../DEPLOY_CHECKLIST.md); rollout and real outage /
   recovery notification tests need separate maintainer authorization.
5. **Finish RR1c and RR1d.** Select Argus stable/edge version behavior and a
   bounded update path, then uninstall only Argus-owned resources. Hermes's
   own release channel and package manager stay Hermes-owned. Settle payload
   ownership and compatibility before freezing installer lifecycle behavior.
6. **Finish the public setup promise and RR2.** Document native Cronping
   Telegram setup and verify delivery separately from ping acceptance;
   publish the external Hermes L3 job/model/destination recipe. Complete
   runtime English/Russian UI without changing parser-facing markers or
   silently changing existing Russian installations.
7. **RR3, then RC.** Rehearse clean Ubuntu 24.04 install from a versioned
   artifact, repeated deployment, upgrade and bounded uninstall; verify
   enabled-module behavior without historical files. Record each remaining
   debt's release disposition before `v0.1.0-rc.1`, then soak before `v0.1.0`.

The short path is: **truthful baseline -> launch compatibility -> critical
alert/evidence fixes -> verified rollout -> RR1c/d -> setup + RR2 -> RR3/RC**.
This is a proposed dependency order, not authorization for one combined PR.

## Which backlog items matter before the release

| Disposition | Items and reason |
| --- | --- |
| Fix before claiming the relevant invariant | [DEBT-014](../BACKLOG.md#debt-014) secret URLs in argv; [DEBT-013](../BACKLOG.md#debt-013) configured delivery transport |
| Decide/fix before RR3 | [DEBT-019](../BACKLOG.md#debt-019) stale green Analyzer; [DEBT-020](../BACKLOG.md#debt-020) Discord-only deepcheck; [DEBT-022](../BACKLOG.md#debt-022) guard reporting unsuccessful rollback as success; [DEBT-023](../BACKLOG.md#debt-023) logrotate activation-path override |
| Setup/product decisions | [DEBT-009](../BACKLOG.md#debt-009) external L3 recipe; [DEBT-012](../BACKLOG.md#debt-012) truthful provisioning claims; [DEBT-016](../BACKLOG.md#debt-016) heartbeat backend selection; [DEBT-017](../BACKLOG.md#debt-017) native Telegram guide; [DEBT-018](../BACKLOG.md#debt-018) public GH workflow behavior |
| Source resolved; deployment evidence outstanding | [DEBT-007](../BACKLOG.md#debt-007), [DEBT-008](../BACKLOG.md#debt-008), [DEBT-010](../BACKLOG.md#debt-010), [DEBT-011](../BACKLOG.md#debt-011), [DEBT-021](../BACKLOG.md#debt-021) |
| Keep out of the critical path unless triggered | [DEBT-001](../BACKLOG.md#debt-001) MCP comment/exit codes; unused substitutions and comments; old full-checker retirement; optional legacy naming cleanup; localized-cron portability |

Deferred does not mean nonexistent. Resolve product choices by either supplying
the promised behavior or explicitly narrowing the supported surface, rather
than treating all backlog cards as mandatory new features.

## Rewrite assessment

**A whole-project rewrite is unsupported by the evidence.** The current
external-observer boundary remains useful even as Hermes gains more native
health reporting. The principal confirmed changes are launcher ownership and
fallback alias normalization; the MCP parser, disabled-server semantics and
fallback log identities still match v0.22.5. The existing registry generator
also successfully parsed v0.22.5 `config_defaults.py` into a temporary file:
153 environment entries plus 9 Argus kit entries. This validates the parser,
not the complete inventory or semantic health of plugin-based integrations.

Worth redesigning narrowly: hardcoded interpreter/CLI paths and, after a
separate research gate, the fragile housekeeping-log hang detector. Native
systemd watchdog support and structured health observations are candidates
for reducing duplicate logic. They are not evidence that a stale
`gateway_state.json.updated_at` proves a hang, nor permission to introduce
competing restart owners. That earlier rejected proposal remains rejected.

Keep external process/host observation, hysteresis, honest evidence states and
independent host-loss alerting. Do not copy Hermes provider resolution,
credential rotation, PM internals or profile routing. Multi-profile coverage,
OAuth live health and full plugin inventory need their own value/scope
decisions; a larger upstream changelog does not automatically make them RC
blockers.

Upstream details and immutable primary-source citations:
[2026-10-25 Hermes watch](2026-10-25-hermes-upstream-watch.md).

## Verification and limits

- GitHub main/merge/CI were checked directly; local tracked content matched
  main. Existing main CI is historical evidence, not a newly rerun test suite.
- Upstream stable and sampled main were inspected at recorded SHAs, not a
  moving branch URL. The generator experiment wrote only a temporary file.
- Production checks were bounded reads of repository identity, selected file
  comparisons, service properties, schedule shape and state freshness. No
  credentials, private addresses, recipient IDs or raw log/response payloads
  are included here.
- No clean-install/update test against v0.22.5 has yet been performed, and no
  current end-to-end alert-delivery proof was obtained. Those are the next
  evidence gaps, not implicit failures or claims of successful compatibility.
