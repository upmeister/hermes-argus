# RR0b contract — dead and duplicate runtime removal

Status: **SELECTED AFTER RR0a / IMPLEMENTATION-READY**

RR0b is the second bounded slice of the pre-release legacy reduction gate. It
removes or explicitly retains the candidate runtime surfaces identified by the
legacy audit. It is an ownership exercise with evidence, not permission for a
repository-wide cleanup.

## 1. Sequence and authority

RR0b starts from the merged `main` containing RR0a, MCP disabled-server
handling, and the canonical gateway matcher fix:

```text
origin/main at contract preparation = b39b25646c9fa9473fbe30be9cf9357fc909df
RR0a implementation                 = PR #51 / f1f9a776
MCP disabled-server implementation  = PR #59 / 3551b08 merge
gateway matcher fix                 = PR #60 / b39b2564
```

Research authority:

- [`docs/research/2026-09-21-pre-release-legacy-audit.md`](../research/2026-09-21-pre-release-legacy-audit.md);
- current `deploy.sh`, module manifests, scripts, registry generation, and
  tests at the implementation baseline.

Focused reviewer: **Codex**, the current project architect/reviewer.

Production risk: **medium**. Removing or de-scheduling a deployed path can
change monitoring coverage.

Merge authority: **maintainer merge after reviewer PASS**. The reviewer may
prepare the exact merge command but may not merge this contract's implementation
PR automatically.

## 2. Problem and required result

The audit found deployed or retained surfaces with no demonstrated live owner:

- the full-mode portion of `health-check-integrations.sh` after v2 health-check
  superseded it;
- `send-monitoring-report.sh`, which has no demonstrated live caller;
- `scripts/legacy/model-fallback-tracker.py`, replaced by
  `fallback-tracker-v2.py`;
- stale deploy substitutions and settings whose runtime consumers are unclear.

After RR0b, every deployed script, scheduled command, generated setting, and
retained legacy file in this candidate set has one of two outcomes:

1. a named live owner and an evidence-backed purpose; or
2. it is removed from the active deployment surface and deleted/archived only
   when the contract permits that exact path.

An item with uncertain ownership stays in place and is recorded as a bounded
backlog item with its evidence. Uncertainty is not a deletion signal.

## 3. Required implementation pass

### Step 1 — build the owner matrix

For each C1–C4 candidate, record:

- repository path and whether `deploy.sh` installs it;
- every runtime caller, cron/systemd owner, generated registry entry, and
  documented operator entry point found by search;
- the intended replacement, if the audit names one;
- the decision: retain, remove from deployment, archive/delete, or stop for
  maintainer decision.

Completion criterion: no candidate is changed before its matrix row contains
the search evidence and decision.

### Step 2 — resolve C1 through C4

#### C1 — full integration-check surface

Keep the owned `--quick` compatibility path used by the watchdog and any
other proven caller. Resolve the full-mode path only from caller/deploy
evidence. The v2 health-check remains the owner of the structured full check.

Completion criterion: the deployed integration path has one demonstrated owner,
and the chosen full-mode disposition has a regression probe or an explicit
backlog entry explaining why it remains.

#### C2 — `send-monitoring-report.sh`

Perform a final repository, manifest, service, cron, and documentation caller
search. If no live owner exists, remove it from the active deployment and
remove the dead source only within this contract. Preserve the established
secret-safe delivery path used by live callers.

Completion criterion: either a live owner is demonstrated, or the file is no
longer deployed and a probe proves that no active manifest/schedule expects it.

#### C3 — legacy fallback tracker

`fallback-tracker-v2.py` remains the active tracker. The legacy tracker may be
archived/deleted only after the same caller and deployment search proves that
no supported path invokes it.

Completion criterion: no active schedule, manifest, test, or documentation
invokes the legacy tracker, and the v2 schedule remains intact.

#### C4 — dead deploy substitutions and settings

Audit `HERMES_BOT_TOKEN`, `HERMES_BOT_UID`, `DMS_API_KEY`, and the historical
webhook/Netdata secret remnants against `deploy.sh`, generated `registry.yaml`,
templates, and runtime readers. Remove a substitution or setting only when its
absence from the owner matrix is proven. Keep a setting that still has a live
consumer, even if it is not part of the default module set.

Completion criterion: every retained setting has a consumer and every removed
setting has no generated or runtime reference in the tested deployment.

## 4. Invariants and non-goals

- Preserve RR0a module expectation behavior and the PR #60 canonical gateway
  matcher.
- Preserve secret handling and the v2 health-check/report contract.
- Do not rename systemd resources or migrate public defaults; those belong to
  RR0c/RR1.
- Do not redesign installer, cron ownership, registry generation, or i18n.
- Do not remove historical handoffs or research merely because they are old.
- Do not delete a production resource or migrate live state in this PR.

Stop and return the owner matrix if a correct disposition requires a new
subsystem, a migration, a new persistent state format, or a change to a live
production resource.

## 5. Required evidence

The implementation receipt must include:

- exact baseline and candidate head;
- the C1–C4 owner matrix with commands/results or file references;
- changed deployment entries and proof that generated registry output remains
  consistent;
- red-capable probes for each removal or de-scheduling decision;
- standard syntax/probe gates and CI;
- explicit out-of-scope findings added to `docs/BACKLOG.md`;
- production actions: `None`.

Minimum checks:

```bash
python3 -m py_compile scripts/health-check-v2.py scripts/gen-registry.py tests/probes.py
bash -n deploy.sh
python3 tests/probes.py
python3 tests/test_watchdog_swap.py
git diff --check
```

## 6. Review gate

The focused reviewer prioritizes:

1. deletion without caller/deploy evidence;
2. removal of a path still used by cron, systemd, or a generated registry;
3. accidental loss of quick integration compatibility or fallback tracking;
4. secret-bearing settings removed without checking all readers;
5. RR0c/RR1 cleanup entering the patch;
6. a missing backlog entry for a deferred finding.

Return `PASS-TO-MAINTAINER`, `REMEDIATE`, or `BLOCKED-FOR-MAINTAINER`, with at
most one bounded remediation pass.
