# Independent programme assessment and next release plan — 2026-10-26

Follow-up: the maintainer accepted the plan and selected its first task.
The [readiness/observation contract](../handoffs/readiness-observation-correctness-contract.md)
now owns implementation authority. The accompanying docs change closes C's
stale merge pointers and records A's accepted launch form. Findings and test
results below remain the dated audit evidence; the runtime fixes are not yet
implemented, and C has not been deployed.

Status: **retrospective review and proposal, not a new implementation contract,
merge gate, or production authorization**. The maintainer asked for an
independent assessment after completing A/B/C and explicitly confirmed that C
has not been deployed. No runtime code or production configuration was changed
by this review. Findings below are assessed against the accepted programme,
not against a newly expanded threat model.

## Snapshot and evidence boundary

Reviewed source: `fd947a06bccc8af60a9ad90f3515c7d91d9b2ed3`, merge of
[PR #79](https://github.com/upmeister/hermes-argus/pull/79). Baseline:
`f433c531bff935d869e2dd75beaf2a5bfdd200d8`. The local implementation head
`76a48db` has the same tracked tree as the merged head.

| Stage | Source | Deployment evidence |
| --- | --- | --- |
| A: Hermes launch/alias compatibility | Merged [PR #77](https://github.com/upmeister/hermes-argus/pull/77) | October 26 Ops receipt at `17b3975` |
| B: existing delivery/evidence fixes | Merged [PR #78](https://github.com/upmeister/hermes-argus/pull/78) | Same Ops receipt |
| Ops | Completed, separately authorized | Rendered payload, cron, services, host prerequisites and scheduled observations recorded |
| C: versioned lifecycle | Merged PR #79 | **Not deployed**, per maintainer; no production uninstall test |

The current merged [CI run](https://github.com/upmeister/hermes-argus/actions/runs/40267992986)
is green. Existing receipts record 265 regression probes, 29 watchdog tests
and 16 lifecycle tests. These counts do not replace the independent checks
described below. Production statements here rely on the
[Ops receipt](../DEPLOY_CHECKLIST.md#ops-receipt--2026-10-26) and maintainer
confirmation; this review did not repeat live provider probes or re-audit the VPS.

## Outcome and architectural assessment

The three-PR grouping was useful. A removed the most material upstream layout
assumption and fixed static alias identity. B addressed concrete secret,
delivery and false-green defects without adding a transport framework. C gives
Argus an explicit source revision and conservative resource lifecycle, with
an intentional refusal when ownership cannot be established.

The architecture still respects the ownership boundary: Hermes owns runtime
activation, provider routing and credentials; Argus owns external observation,
its schedules, evidence and installed artifacts. A/C each add their one allowed
production entrypoint. No new dependency or persistent installation database
was introduced. The size of the adapter/deploy diff alone does not establish
overengineering: most new behavior is required by the selected contracts,
and C reuses the existing resource lists and renderer.

Review caught real defects before deployment/public use: A's consumer/root
binding issues, B's incomplete test evidence, and C's removal of an adapter
needed by preserved Hermes base services. C's remediation now retains both
adapter copies and exercises the preserved ExecStart chains. Retaining a few
known files is a reasonable bounded uninstall choice, not a requirement to
invent a dependency graph.

This is source completion of the selected programme, **not public-release
acceptance**. Current lifecycle tests use real Git/filesystem/shell behavior
but stub service managers and transports; the full clean-host product remains
RR3 work. Ping acceptance/read-only Telegram API access is not notification
delivery proof, and fresh Analyzer state is not proof of the external L3 job.

## Standards axis

### P2: merge-status drift recurred at C

GitHub confirms PR #79 merged, while `AGENTS.md`, `docs/ROADMAP.md`, the
handoff index, contract C and the latest vault receipt still describe a pending
maintainer gate or no merge. This violates the repository's same-change status
rule. Correct state: **A/B/C source complete; programme STOP reached; C not
deployed**. A new programme requires a new maintainer selection. The occurrence
is recorded under [SYNC-002](../BACKLOG.md#sync-002).

The practical correction is a merge-aware completion record across the existing
status surfaces, rather than another process tool. Before merging, prepare the
post-merge wording in the candidate and have the maintainer's final gate verify
it. This remains the weak part of delivery even though code reviews and CI ran.

### P3: the completed A contract still prescribes the abandoned launch form

Contract A lines 43–47 prescribe executing the argv returned by
`--print-runtime-command --module runpy -- <script>`. The actual adapter uses
the returned interpreter, Hermes bootstrap and `runpy.run_path` instead.
PR #77 records the real-runtime experiment that justified this correction.
The completed contract should record that accepted mechanism, so later work
does not restore a non-working design merely to match the old prose.

This is a design-document discrepancy, not evidence that the current bootstrap
composition is itself wrong. No additional architecture-boundary violation or
substantial independent code-smell finding was established.

## Spec/correctness axis

### P2: managed preflight establishes a path, not working runtime capability

In `scripts/hermes-runtime.py:188`, the managed `check` branch resolves an
executable path and immediately returns success. It never runs the selected
interpreter or bootstrap. `deploy.sh:299` uses this result as the Hermes
runtime capability gate. The legacy branch does execute its interpreter.

An isolated fixture returned a well-formed launcher argv with `/bin/false` as
the executable. Results:

```text
managed check rc = 0
run-script rc = 1
harmless script executed = false
```

The fixture represents an unusable executable despite successful launcher
resolution; it is not a malicious-installation threat model. This leaves the
RR1b H3 capability requirement incomplete for the managed path. The passing
real-runtime rehearsal demonstrates a working installation, not refusal of
this failure case. Track as [DEBT-030](../BACKLOG.md#debt-030).

Smallest proposed correction: a bounded, harmless capability check through the
same managed runtime activation used by consumers, with a failure/timeout
fixture and classified diagnostics. No provider calls, credential refresh,
runtime repair or interpreter-integrity system. Fix before advertising fresh
managed-install readiness. This does not establish a current production outage
or invalidate the existing successful deployed-runtime read-back.

### C failure recovery: an explicit operational limit, not silent success

An extra lifecycle experiment installed fixture revision V1, selected V2,
then made the selected tree's user-manager preflight fail before runtime writes.
The checkout became V2 while the runtime remained V1. After removing the
injected failure, repeating the installer refused old-runtime files as
unmatched against the now-current V2 source:

```text
initial install rc = 1
checkout is target = true
runtime unchanged = true
retry rc = 1; ownership refusal = true
```

C reports the partial state and promises neither automatic rollback nor blind
retry. Therefore this is not presented as an unfulfilled automatic-recovery
requirement. It is a usability/acceptance gap: users need a tested manual
reconciliation procedure for this ordinary interruption. Record the old and
selected revision, preserve custom artifacts and rehearse recovery in an
isolated fixture; do not introduce a persistent transaction system merely to
make retry automatic. Track as [DEBT-031](../BACKLOG.md#debt-031).

## Proposed next sequence

1. **Close the programme truthfully and make readiness honest.** Synchronize
   C's merged/not-deployed state and A's actual launch decision. Select a
   bounded correctness batch: DEBT-030 managed capability, existing
   [DEBT-028](../BACKLOG.md#debt-028) process-observation errors, and
   [DEBT-022](../BACKLOG.md#debt-022) unsuccessful network rollback reported
   as success. All three concern truthful observations; no new monitoring
   platform is needed. Include the C recovery recipe/rehearsal as operator
   acceptance, with implementation limited to what a selected contract admits.
2. **Rehearse C, then separately authorize an update-only production rollout.**
   Use an isolated Linux environment for install/update/uninstall and failure
   recovery. Production deployment should verify selected revision, payload,
   schedules and preserved Hermes services. Never use the production VPS as
   an uninstall test. There is no reason to rush a working A/B production
   installation just to match main's newest SHA.
3. **Complete the public operating promise.** Document and separately verify
   native Cronping Telegram outage/recovery delivery, make external L3 setup
   explicit, and settle supported heartbeat behavior. No Argus webhook/VPS
   bridge is needed. The remaining catalog 401 is an operator/configuration
   task, not justification to rewrite health checking; the removed 404 check
   must not be advertised as healed.
4. **RR2: runtime English/Russian.** Preserve existing Russian installations,
   language-neutral schemas and parser markers; keep public docs English.
   Do this after the visible error/status semantics above are settled, so
   localization does not encode misleading messages twice.
5. **RR3 and the RC.** Run clean Ubuntu 24.04 installation with real service
   manager/cron behavior, repeat/upgrade/uninstall, and the supported optional
   module combinations. Use an explicit RC tag; default stable is intentionally
   unavailable until a non-prerelease exists. Publish only after a separate
   maintainer release decision; then soak before v0.1.0.

Before RR3, give remaining release-relevant cards explicit dispositions:
[DEBT-020](../BACKLOG.md#debt-020) Discord-only deepcheck, the
[DEBT-023](../BACKLOG.md#debt-023) logrotate override and
[DEBT-029](../BACKLOG.md#debt-029) generated registry refresh. A small ownership
fix or honest unsupported-combination message can be sufficient; every card
does not require a new feature. Registry must be regenerated, not hand-edited.

Keep cosmetic substitutions/comments, speculative provider/profile coverage,
OAuth live health, OTLP backend adoption and the larger liveness redesign off
the critical path unless a concrete incident changes their value. No whole
project rewrite is supported by this assessment.

## Independent verification

The reviewed merged tree was exported to an isolated ext4 directory under WSL,
as a non-root user, on **Ubuntu 26.04.1 / Python 3.14.4**; no production config
or credentials were copied. This provides an additional environment check,
not a new rehearsal of the supported Ubuntu 24.04 target. Target-24.04 evidence
comes from the linked CI workflow and earlier reviewed receipts. Syntax,
the repository suites and the two extra scenarios are recorded in the final
verification receipt added below. External GitHub CI evidence remains linked
separately above. This is a new retrospective check, not a claimed replacement
for the earlier exact-head merge reviews.

Independent results on the exported `fd947a0` tree:

- Python compilation and `bash -n deploy.sh install.sh uninstall.sh`: pass.
- `python3 tests/probes.py`: **265 passed, 0 failed**.
- `python3 tests/test_watchdog_swap.py`: **29 tests, OK**.
- `python3 tests/test_lifecycle.py`: **16 tests, OK**.
- Additional managed-capability fixture reproduced DEBT-030; additional
  interrupted-update/retry fixture reproduced the DEBT-031 operational limit.

The extra cases were run outside the repository and changed only temporary
fixture data. No fix, production deployment, merge or new contract selection
was performed. The green existing suite and the new counterexample coexist:
the uncovered managed-capability case needs its own regression assertion in
the eventual selected correction.

The findings were also appended to the connected vault backlog and read back.
At that time the note labelled this report/ledger as a local, unpublished docs
candidate. Publication/sync of the subsequent contract is recorded separately
in `docs/VAULT-SYNC.md`; the audit's MCP write alone proved no Git convergence.
