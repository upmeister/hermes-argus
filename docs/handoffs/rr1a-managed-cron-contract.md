# RR1a contract — managed Argus cron ownership

Status: **SELECTED / READY FOR BUILDER**

## Authority and delivery

Preparation baseline:
`2588581a27234b6e0be2b38b29e39f29476d328e` (RR0c / PR #65 merged).
Implement from the fresh `origin/main` after this contract's docs PR is merged.
Read the [production dependency audit](../research/2026-10-03-production-deployment-dependencies.md)
for the observed existing-install boundary.

Focused reviewer: **Codex**.

Production risk: **high** — the patch changes the live scheduling surface.

Merge authority: **maintainer merge after reviewer PASS**. The reviewer prepares
an exact-head merge command; merge never authorizes production deployment.

Use one implementation PR, one focused review, at most one remediation, then
the exact-head decision. Read [AGENTS.md](../../AGENTS.md) for shared scope and
verification rules. Return deferred findings to [BACKLOG.md](../BACKLOG.md).

## Problem -> evidence -> smallest patch -> owner -> non-goals

Most modules produce a cron proposal requiring manual installation; only
LOCAL_SERVICES currently mutates live cron. Module OFF does not reconcile older
manually installed jobs. Production also contains independent backup/sync jobs
and a legacy quick-check wrapper outside Argus manifests.

The quick checker assumes at least seven global jobs, and auto-remediation may
restore the entire crontab from an old snapshot. Both violate module-based
scheduling and operator ownership.

Smallest patch: let `deploy.sh` reconcile one marked Argus block from the
existing schedule generator; unify LOCAL_SERVICES with that writer; remove
the global count heuristic and whole-crontab restoration. Preserve all other
runtime checks and schedules outside the approved ownership set.

This contract is schedule ownership only. Dependency installation, Netdata,
proxy/network provisioning, Analyzer collector wiring, Hermes L3 jobs,
versioned updates, full-mode deletion, uninstall and i18n are later contracts.

## 1. Single schedule and writer

- Existing `MODULE_*` flags and `CRON_PROFILE=full|minimal` retain their
  meanings and defaults. Generate only jobs enabled by those settings.
- Use the current generator in `deploy.sh` as the schedule authority. Keep
  `CRON_FILE` as a useful proposal/diagnostic artifact; it is not proof that
  live cron was installed.
- The block delimiters are exactly `# BEGIN HERMES-ARGUS` and
  `# END HERMES-ARGUS`. Own at most one well-formed block in the invoking
  user's crontab. An empty selected schedule may remove the block completely.
- Read the current crontab, replace only that block, and write the complete
  preserved result through one reconciliation path. Running deploy twice with
  the same config must leave the installed result unchanged.
- LOCAL_SERVICES must use this same writer while preserving its single
  sequential snapshot/check job and bounded initial collection behavior.
  Complete reconciliation before its initial collection.
- Cron uses `/bin/sh`; any generated command requiring Bash must explicitly
  invoke Bash. Preserve the existing runtime `.env` loading and module gating.
  Credential values may never enter cron lines or command arguments.

Completion criterion: enabled modules have exactly one scheduled job per
current generator entry; disabled modules have none in the managed block;
LOCAL_SERVICES has no second independent schedule writer.

## 2. Existing-install ownership and preservation

- Preserve unrelated comments, blank lines, environment declarations and
  commands outside the owned block. Do not globally sort/deduplicate cron.
- On first adoption, recognize only an explicit finite set of previously
  generated Argus jobs at the current installation's canonical script paths
  (including their established tilde spellings). Use the known schedule,
  executable, arguments and redirection shape; basename substring matching is
  insufficient ownership evidence.
- Recognize prior LOCAL_SERVICES generated/producer-only forms covered by its
  existing migration probes. Replace those with the managed entry on ON and
  remove them on OFF without matching unrelated mentions of their basenames.
- A custom operator job invoking the same script with different arguments,
  paths or command structure is preserved. Report ambiguous legacy ownership
  by count/generic description without logging raw command text.
- Preserve external `check-integrations.sh`, infrastructure-sync and backup
  jobs. Their presence in production does not authorize adopting/deleting them.
- Do not modify root cron, `/etc/cron.d`, systemd units/timers or Hermes cron
  jobs, including saved disabled `no_agent` jobs.

Completion criterion: both fresh-install and mixed legacy/operator fixtures
have no duplicate jobs from the approved generated forms, and unrelated/custom
rows survive with their original content and order.

## 3. Fail closed and use a bounded transaction

- Check `crontab` availability before attempting reconciliation. Treat a
  confirmed empty/no-crontab state separately from a failed read; a generic
  nonzero `crontab -l` must not be interpreted as an empty operator schedule.
- Reject duplicate, nested, unmatched or reversed block markers before writing.
  Leave the installed crontab unchanged and return a clear error.
- A failed read or write is a nonzero deploy result. Do not report a disabled
  module or installed schedule as successful when reconciliation failed.
- Use an existing nonblocking lock pattern to serialize the read/compose/write
  cycle for concurrent Argus deploys. The lock is a transient operational file,
  not a new module-state database. Lock contention returns a clear result.
- Tests must shim every crontab invocation and isolate HOME. Never use a real
  developer/production crontab as a regression fixture.

External manual edits during this small transaction remain an operator
coordination boundary; a general multi-writer scheduler is out of scope.

## 4. Retire conflicting global recovery assumptions

- Remove the unconditional `<7 jobs` quick-check criterion. Do not replace it
  with another whole-user job count or let unrelated jobs prove Argus healthy.
  Existing named watchdog schedule/freshness checks remain reportable.
- Remove the whole-user crontab restore branch in `auto-remediate.sh`; it must
  never install `crontab-known-good.txt` because a module/profile reduced the
  schedule. Leave the saved backup file intact for operator use.
- Deploy is the sole scheduler writer introduced by this contract. Do not add
  a recovery daemon, recurring reinstall job or a new persistent schedule
  format. Existing process/disk/pressure remediation behavior is unchanged.
- Update install/deploy completion text and installation docs so a successful
  deploy no longer asks the operator to append the generated lines manually.

Completion criterion: a valid small module schedule is not reported broken by
the old count rule, and a stale full-crontab backup cannot resurrect disabled
Argus or unrelated operator jobs.

## 5. Owning paths

- `deploy.sh` — generator and one reconciliation path;
- `install.sh` — obsolete manual-append instructions only;
- `scripts/health-check-integrations.sh` — cron-count criterion only;
- `scripts/auto-remediate.sh` — whole-crontab restore branch only;
- `tests/probes.py`, `tests/test_watchdog_swap.py` — isolated scheduler probes;
- README, roadmap/handoff status, changelog, backlog and deployment checklist —
  documentation describing the resulting schedule ownership.

At most one small production helper may be extracted if keeping the existing
generator/writer readable requires it; it must reuse this ownership contract
and introduce no dependencies or separate state. Do not redesign watchdog
health or Telegram UI as a prerequisite for this slice.

## 6. Required red-capable probes

1. Fresh default install creates one block with the enabled-module jobs;
   rerun is byte-stable and does not duplicate schedules.
2. CORE, INTEGRATIONS, ANALYZER, HEARTBEAT and LOCAL_SERVICES ON->OFF transitions
   remove only their generated schedules. TG/Discord service activation is
   not a cron operation. All scheduling modules OFF removes only the block.
3. `minimal` profile remains quiet, while selected integration/local-services
   jobs keep the documented generator semantics.
4. Mixed user cron preserves unrelated jobs/comments/env declarations,
   including a lookalike basename and a custom same-script command.
5. Known legacy generated forms are adopted once; external wrappers and saved
   Hermes jobs are unchanged.
6. Missing crontab utility, unexpected read failure and write failure are loud;
   the prior fixture is not replaced by an empty schedule.
7. Every malformed marker layout is rejected without a write.
8. Simultaneous deploys serialize reconciliation or return explicit contention;
   no lost unrelated fixture rows or duplicate block.
9. LOCAL_SERVICES retains single-job sequencing, immediate activation and
   ON->OFF behavior under the common writer, including legacy collector cron.
10. A valid small cron does not fail the removed seven-job condition; an old
    full backup never triggers a `crontab <backup>` write from remediation.
11. Cron commands parse under their explicit shell, preserve runtime credential
    loading, and contain no credential canaries. Tests cannot escape their
    shims even during error/remediation cases.

Prove at least the scheduler ownership/ON->OFF and whole-crontab restoration
regressions RED against the pre-RR1a baseline, then GREEN on the candidate.
Do not add tests mirroring helper internals instead of the crontab effects.

## 7. Receipt and exact-head gate

Builder receipt: baseline/head, changed owners, adopted legacy forms, preserved
operator forms, red evidence, fixture scheduling results, syntax/regression
checks, exact-head `argus-ci`, deferred findings, and production actions `None`.

Run the shared minimum checks plus:

```bash
bash -n install.sh scripts/health-check-integrations.sh scripts/auto-remediate.sh
```

Compile any new Python helper. Linux behavioral verification belongs in
isolated fixtures or CI; test failures must be explained and cannot be replaced
by an unrelated green production smoke.

Reviewer prioritizes unrelated-cron deletion, failed-read-as-empty, stale
backup restoration, wildcard adoption, secret-bearing cron, duplicate
LOCAL_SERVICES writers, module/profile regressions, and scope expansion into
RR1b/Netdata/network/L3 provisioning. Return `PASS-TO-MAINTAINER`, `REMEDIATE`
or `BLOCKED-FOR-MAINTAINER`; at most one remediation pass.

Production rollout uses [DEPLOY_CHECKLIST.md](../DEPLOY_CHECKLIST.md) only after
separate maintainer authorization, with read-back of the preserved operator
schedule and installed Argus block. No production changes are authorized here.
