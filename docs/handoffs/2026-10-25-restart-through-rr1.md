# Restart programme through RR1

Status: **A+B merged and deployed; Ops complete; C implemented in PR #79,
maintainer gate pending; Codex review receipt in that PR**.
The maintainer accepted reconnaissance steps 1–5 on 2026-10-25 and assigned
architecture/docs-PR preparation to Codex, asking for useful-sized PRs.
Contracts A/B landed as PR #77/#78. The separately authorized October 26
[Ops receipt](../DEPLOY_CHECKLIST.md#ops-receipt--2026-10-26) records deployment
of `17b3975`. This document supersedes the stale
RR1b selected-task pointer, not its completed acceptance record.

Production risk: **low for this documentation PR** (no executable/config
changes). Merge authority: **maintainer for this contract publication**.
Builder: maintainer-assigned coder. Focused reviewer: **Codex** for each
implementation PR. No reviewer session is launched by publishing this suite.

## Decisions and their destinations

| ID | Source | Meaning | Destination / acceptance |
| --- | --- | --- | --- |
| D1 | Maintainer, 2026-10-25, acceptance of reconnaissance steps 1–5 | Stop this programme after versioned install/update and bounded uninstall; RR2/RR3 remain later | Three implementation contracts below; no i18n or release publication |
| D2 | Same message: avoid excessively small PRs | Group by outcome, not each debt or each file | A combines upstream compatibility; B combines existing delivery/evidence fixes; C combines RR1c/d |
| D3 | GitHub PR #75 and main CI; read-only VPS inspection | RR1b is merged; production is older and mixed | Status docs/vault repaired in this PR; rollout read-back remains separate |
| D4 | Existing project contract; accepted reconnaissance | Hermes owns routing, credentials and managed runtime; Argus observes externally | A consumes the published launch boundary and static alias data, without implementing a PM or provider resolver |
| D5 | Accepted plan, step 3 | Fix heartbeat argv, configured proxy propagation and stale Analyzer green | B's three measurable acceptance groups; two production failures are diagnosed, not an unlimited repair mandate |
| D6 | Existing separate production-authorization rule; user assigned docs work | Prepare rollout, but do not execute it from this suite alone | Operations checkpoint requires exact-SHA maintainer authorization |
| D7 | Architect choices made concrete for review in this PR | Reuse 7200-second Analyzer freshness boundary; explicit version/channel each install invocation; conservative uninstall | B/C label these choices and contain boundary tests; they are not falsely attributed to an earlier user instruction |

## Sequence and admission

| Step | Deliverable | Risk / merge authority | Start condition |
| --- | --- | --- | --- |
| 0 | This docs PR: status reconciliation, research, contracts | Low / maintainer | Current task |
| A | [Hermes 0.22.5 compatibility](restart-a-hermes-compatibility-contract.md) | Medium / maintainer after Codex PASS | Contract PR merged; refresh `origin/main` |
| B | [Delivery and evidence correctness](restart-b-delivery-evidence-contract.md) | Medium / maintainer after Codex PASS | A merged; base on resulting main |
| Ops | Production reconciliation and separately authorized rollout | High / maintainer | A+B merged; exact target and runtime differences reviewed |
| C | [Versioned lifecycle: RR1c + RR1d](restart-c-versioned-lifecycle-contract.md) | High / maintainer after Codex PASS | A+B merged; Ops receipt or explicit maintainer deferral of rollout |
| Stop | Handoff with source/deployment states and remaining debts | No further implementation admitted | C merged or a scope blocker returned |

The maintainer selected this bounded queue. After each merge, the next admitted
contract becomes the builder pointer; there is no new docs PR for every row.
Only one implementation PR is active at a time. C must not infer rollout
authorization from elapsed time. The maintainer may allow C's isolated work
before rollout by recording a deferral; production stays explicitly pending.
The three PRs are the intended grouping, not permission to force an oversized
implementation through the repository's stop rules.

Baseline at publication: Argus main `f433c531bff935d869e2dd75beaf2a5bfdd200d8`.
Each builder records the actual refreshed main SHA. Research:
[project reconstruction](../research/2026-10-25-project-reconnaissance.md),
[upstream watch](../research/2026-10-25-hermes-upstream-watch.md).
Hermes v0.22.5 at `bf0203a794a07aac3ff764972ab9087baa4e4f4e` became the
accepted stable authority at the contract A merge (PR #77). The October 26
Ops receipt verifies this host's deployed behavior without expanding support.

## Operations checkpoint

**Completed 2026-10-26** after the maintainer authorized deployment and device
tests. Exact deployed source: `17b3975927cec11783a314f68e614e7a4d12bb1c`.
See the [receipt](../DEPLOY_CHECKLIST.md#ops-receipt--2026-10-26), including
diagnosed catalog failures and the non-blocking registry refresh finding.
The requirements below remain the procedure for future rollouts.

Prepare a sanitized before/after plan using [DEPLOY_CHECKLIST](../DEPLOY_CHECKLIST.md).
Resolve installed `health-check-integrations.sh` differences from templates;
record intended handling rather than overwriting an unexplained customization.
Verify the current managed cron block and preserve operator jobs/environment.
Explicitly record whether this host retains `MODULE_NETWORK_GUARD=ON`; the
new default OFF must not silently disable an existing operational dependency.
Record config privacy, user-manager/linger, logrotate activation and the actual
Hermes launch path. Use a temporary protected operator backup if needed, not
a new Argus backup subsystem or repository copy of secrets.

Diagnose the two cached failed checks with sanitized class/reason evidence.
Reading state/source is allowed; any active check that could refresh auth,
send a notification or modify production needs its specific authorization.
Record causes and disposition. If remediation is outside A/B, return a blocker
or explicit deferred finding for the maintainer; do not append work silently.

After separate authorization, deploy only the named merged SHA, read back
installed templates, schedules and service state, and distinguish successful
ping acceptance from actual notification delivery. Failure simulations and
send tests need explicit inclusion in that authorization. A failed read-back
ends in an operator decision, not automatic broad rollback or repeated fixes.

## Builder and reviewer protocol

Read this index, the selected A/B/C file and repository `AGENTS.md`; historical
contracts do not expand that file's surface. Builder supplies exact base/head,
criterion-to-evidence mapping, changed paths, Linux results, source/deployment
status and linked backlog cards. Update status surfaces in the implementation
PR, with truthful conditional merge wording, and synchronize vault pointers.

Reviewer checks the exact candidate against its named acceptance rows,
adversarially inspects secret channels and false-green behavior, and returns
`PASS-TO-MAINTAINER`, `REMEDIATE` or `BLOCKED-FOR-MAINTAINER`. One focused
review, at most one remediation, then one reread of the exact tree. A second
remediation or broader architecture requires a maintainer decision. Required
`argus-ci` must be green on the candidate; maintainer owns the final exact-head
gate and runtime merge. PASS is not production authorization.

Outside this programme: RR2/RR3 implementation, RC/tag publication, Cronping
account/setup automation, L3 job creation, new heartbeat backend semantics,
OAuth health, multi-profile coverage, plugin inventory expansion, OTLP backend,
gateway-liveness redesign, network policy changes and unrelated cleanup.

## Assignment text

Builder: "Implement contract A (then B/C only after their start gates), using
this merged programme as authority. Refresh origin/main, record the base SHA,
implement only its owning surface, supply the criterion/evidence receipt and
open one implementation PR. Stop on the contract's scope blockers. Do not
deploy or proceed to later stages just because tests pass."

Reviewer: "Review the named implementation PR's exact head against its A/B/C
contract and this programme. Check every acceptance row and supplied Linux
evidence, inspect relevant callers, and distinguish source completion from
deployment. Return PASS-TO-MAINTAINER, one bounded REMEDIATE request, or
BLOCKED-FOR-MAINTAINER. Out-of-scope findings go to linked backlog cards;
no automatic new workstream, merge, deploy or second review wave."
