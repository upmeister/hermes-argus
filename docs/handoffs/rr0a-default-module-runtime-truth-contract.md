# RR0a contract — default module/runtime truth

Status: **NEXT AFTER R2c.1 / IMPLEMENTATION CONTRACT**

This contract is the first bounded slice of RR0. It fixes demonstrated release-
blocking runtime wiring only. It is not a general cleanup/refactor permission.

## 1. Exact authority

Repository baseline for this docs contract:

```text
main at contract creation = 5c38fa2381a11974d5b3691def8b5c7fa7849f81
R2c.1 candidate PR        = #49
R2c.1 candidate head      = c5cc56ec49669ff10660c43aaec8974dfed5a2f0
```

RR0a must start from the merged post-R2c.1 main, not from the baseline above.

Research authority:

- `docs/research/2026-09-21-pre-release-legacy-audit.md`;
- `docs/ROADMAP.md`;
- current module/deploy behavior in `deploy.sh` and
  `config/config.env.template`.

Current default module set remains:

```text
MODULE_CORE=ON
MODULE_INTEGRATIONS=ON
MODULE_TG_BOT=OFF
MODULE_ANALYZER=OFF
MODULE_HEARTBEAT=OFF
MODULE_GH_HEARTBEAT=OFF
MODULE_DISCORD_BOT=OFF
```

Do not change those defaults under RR0a merely to make self-health green.

## 2. Release-blocking defects in scope

RR0a owns exactly four demonstrated wiring defects.

### A1 — historical integration checker path

`scripts/hermes-watchdog.sh` executes:

```text
$HOME_DIR/scripts/check-integrations.sh
```

That file is not deployed by Argus.

The currently owned compatibility checker is deployed as:

```text
~/.hermes/scripts/health-check-integrations.sh --quick
```

`tests/test_watchdog_swap.py` currently creates a synthetic
`~/scripts/check-integrations.sh`, masking the clean-install defect.

### A2 — CORE depends on default-OFF ANALYZER state

`MODULE_CORE=ON` and `MODULE_ANALYZER=OFF` by default, but
`hermes-watchdog.sh` treats missing/stale:

```text
~/.hermes/logs/health-state.json
```

as a CORE problem.

That state is produced by the optional analyzer path. A default install must not
manufacture analyzer health state just to satisfy CORE.

### A3 — self-health requires optional/uninstalled components

`scripts/watchdog-health.sh` unconditionally reports problems when:

- `monitoring-bot-poller.service` is inactive, although TG_BOT defaults OFF;
- `netdata.service` is inactive, although the public bootstrap does not install
  Netdata.

Missing optional components are not evidence of a broken default installation.

### A4 — GitHub heartbeat local path split

GH heartbeat setup creates:

```text
~/.hermes/gh-heartbeat
```

but runtime paths still inspect/use the historical:

```text
~/.hermes/hermes-infra
```

Known affected owners include:

- `scripts/heartbeat.sh`;
- `scripts/watchdog-health.sh`;
- the heartbeat status path in `scripts/webhook.py`.

A historical maintainer directory can therefore hide a clean-install defect.

## 3. Required invariant

After RR0a:

> A clean install using the documented default module set must not report a
> problem solely because an optional or historical component was never
> installed.

At the same time:

> A component that is actually expected/enabled must still fail loud when its
> owned artifact/service/state is missing, inactive or stale.

Do not turn missing evidence into green. Distinguish **disabled/not owned** from
**expected but broken**.

## 4. Module expectation boundary

RR0a may use the smallest explicit predicate needed to decide whether a module
surface is expected.

Acceptable evidence includes:

- an Argus-owned installed artifact/unit that exists only when that module is
  deployed;
- a tiny deploy-time marker/substitution if existing artifacts are not
  sufficient.

Do not introduce a new general module registry, state database or config
framework.

A stale personal file that happens to exist must not silently redefine module
ownership.

## 5. A1 required behavior — integration checker

The historical `~/scripts/check-integrations.sh` path must leave the active
CORE path.

Do **not** fix A1 by recreating a compatibility wrapper at that path.

When the integration module is expected, the watchdog compatibility check must
use the owned command:

```text
~/.hermes/scripts/health-check-integrations.sh --quick
```

The existing quick-output parsing/incident behavior remains the compatibility
contract.

When integrations are intentionally not installed, CORE must not emit a false
integration-check failure merely because the checker is absent.

When integrations are expected but the owned checker is unexpectedly missing,
that absence must be explicit rather than silently green.

## 6. A2 required behavior — analyzer state

`health-state.json` freshness belongs to ANALYZER, not unconditional CORE
truth.

Required semantics:

- ANALYZER not expected -> missing `health-state.json` is not a problem;
- ANALYZER expected -> missing, unreadable or stale state remains a problem;
- enabling CORE must not create or refresh fake analyzer state;
- existing analyzer state schema and analyzer scheduling are unchanged.

Use an owned analyzer expectation signal; do not infer enablement merely from a
leftover `health-state.json`.

## 7. A3 required behavior — optional TG bot and Netdata

### Telegram monitoring bot

When TG_BOT is not expected, absence/inactivity of
`monitoring-bot-poller.service` is not a self-health problem.

When TG_BOT is expected, inactive/missing owned service state remains a problem.

### Netdata

A clean public install does not own Netdata installation.

Required semantics:

- Netdata absent/unmanaged -> no default self-health failure;
- Netdata present/explicitly expected -> broken/inactive state may still be
  reported.

Do not add Netdata installation to RR0a.

Do not enable TG_BOT by default.

## 8. A4 required behavior — GitHub heartbeat directory

The canonical new-install local repository directory is:

```text
~/.hermes/gh-heartbeat
```

All active GH heartbeat writer/status/self-health paths must agree on that
canonical location.

Production compatibility is required:

- if the canonical directory exists, it wins;
- a bounded legacy fallback to an existing `~/.hermes/hermes-infra` Git
  heartbeat checkout is allowed only to preserve an already-deployed
  installation;
- do not write to both directories;
- do not create the legacy directory on a clean install;
- do not delete or auto-move legacy production state in RR0a.

A full naming/resource migration belongs to RR0c/RR1.

Cronping and Dead Man's Snitch behavior is not part of this path correction.

## 9. Owner surface

Primary owners:

- `scripts/hermes-watchdog.sh`;
- `scripts/watchdog-health.sh`;
- `scripts/heartbeat.sh`;
- `tests/test_watchdog_swap.py`;
- `tests/probes.py`.

Allowed adjacent owners when required by the smallest correct patch:

- `scripts/webhook.py` — GH heartbeat status path only;
- `deploy.sh` — module expectation/path wiring only;
- `config/config.env.template` — comments/explicit wiring only, no default
  changes;
- `CHANGELOG.md`.

Not owners under RR0a:

- `scripts/send-monitoring-report.sh` deletion;
- legacy fallback tracker removal;
- old deploy substitutions/settings cleanup;
- smart-proxy defaults;
- personal `GITHUB_REPO` default;
- `hermes-vps-kit-*` unit renaming;
- installer/cron ownership redesign;
- runtime i18n.

Those belong to RR0b, RR0c, RR1 or RR2.

## 10. Required red-capable probes

The implementation must add focused probes that fail on the pre-RR0a baseline.

At minimum:

1. **owned integration checker path**
   - no `~/scripts/check-integrations.sh` fixture;
   - canonical `~/.hermes/scripts/health-check-integrations.sh --quick` is
     invoked when expected.

2. **integration module absent**
   - intentionally absent INTEGRATIONS does not create a false CORE incident.

3. **integration checker unexpectedly missing**
   - expected INTEGRATIONS with missing owned checker is not false-green.

4. **analyzer disabled**
   - no analyzer installed/expected and no `health-state.json` produces no
     analyzer-state incident.

5. **analyzer expected**
   - missing/stale analyzer state still produces the existing bounded problem.

6. **TG bot disabled**
   - absent `monitoring-bot-poller.service` under default modules is not a
     problem.

7. **TG bot expected but inactive**
   - the inactive service remains reportable.

8. **Netdata absent**
   - a clean host with no Netdata unit does not fail self-health.

9. **Netdata present but broken**
   - the chosen expectation predicate still catches a present/owned inactive
     Netdata surface.

10. **GH heartbeat canonical path**
    - writer/status/self-health agree on `~/.hermes/gh-heartbeat`.

11. **GH heartbeat legacy compatibility**
    - legacy-only existing checkout remains usable if the compatibility fallback
      is retained;
    - canonical path wins when both exist.

12. **default-module truth**
    - a synthetic clean/default installation does not require ANALYZER, TG bot,
      Netdata or a historical heartbeat directory to reach a non-false-failing
      self-health state.

Record at least one baseline RED receipt before applying the fix.

## 11. Regression gates

At minimum:

```bash
python3 tests/probes.py
python3 tests/test_watchdog_swap.py
python3 -m py_compile scripts/webhook.py
bash -n deploy.sh
bash -n scripts/hermes-watchdog.sh
bash -n scripts/watchdog-health.sh
bash -n scripts/heartbeat.sh
git diff --check
```

If an allowed adjacent Python owner is not touched, its compile check may remain
as a no-op gate.

Exact candidate-head `argus-ci` must be green.

The focused reviewer must review the exact candidate head, not an earlier
implementation commit.

## 12. Production safety

RR0a changes live monitoring wiring and therefore requires post-merge deployment
evidence.

After merge:

- compare changed blobs against the reviewed candidate;
- deploy from merged `main`;
- inspect installed watchdog/self-health/heartbeat files;
- verify relevant cron/systemd state;
- run one bounded watchdog/self-health smoke;
- confirm expected optional-module skips do not hide an enabled-module failure.

Do not delete legacy heartbeat state during this deployment.

## 13. Non-goals

RR0a does not authorize:

- general shell cleanup;
- dead/duplicate runtime deletion (RR0b);
- public/personal default cleanup or naming migration (RR0c);
- installer/dependency/managed-cron redesign (RR1);
- runtime localization (RR2);
- R2c.2 scoped fallback work;
- OA2;
- gateway-liveness redesign;
- multi-profile monitoring;
- changes to module defaults merely to satisfy tests.

## 14. Stop condition

Stop and report the concrete dependency if a correct RR0a patch begins to
require:

- a new module state framework;
- broad installer redesign;
- changing default module enablement;
- automatic destructive migration of legacy production state;
- deleting unrelated historical surfaces;
- redesigning watchdog incident semantics beyond these four defects.

Do not expand RR0a to absorb that work.

## 15. Role-based delivery

### Builder

Perform one implementation pass against this contract and return:

```markdown
# RR0a implementation receipt

## Exact baseline/head

## A1 integration checker
- expectation predicate:
- canonical command:
- disabled behavior:
- expected-missing behavior:

## A2 analyzer-state ownership
- expectation predicate:
- disabled behavior:
- enabled missing/stale behavior:

## A3 optional self-health
- TG predicate/result:
- Netdata predicate/result:

## A4 GH heartbeat path
- canonical path:
- legacy compatibility:
- both-path precedence:

## Baseline RED evidence

## Tests / CI

## Changed files

## Out-of-scope findings

## Production actions
None.

## Recommendation
READY FOR FOCUSED REVIEW | BLOCKED
```

### Focused reviewer

Prioritize:

1. legacy wrapper recreated instead of caller fixed;
2. disabled optional components still reported as broken;
3. enabled components silently skipped;
4. analyzer state made unconditional/faked;
5. Netdata accidentally becomes an install dependency;
6. TG bot default changes;
7. canonical/legacy GH heartbeat directories are both written;
8. personal defaults or RR0b/RR0c cleanup enters the patch;
9. tests still synthesize historical state that masks clean-install truth.

Return:

```text
PASS-TO-MAINTAINER | REMEDIATE | BLOCKED-FOR-MAINTAINER
```

At most one bounded remediation pass.

### Maintainer

After review/remediation:

- reread the exact candidate head;
- verify CI/receipt match that head;
- reject scope creep into RR0b/RR0c/RR1;
- authorize merge;
- compare merged blobs;
- authorize production deploy separately.
