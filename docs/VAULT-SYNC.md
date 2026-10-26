# Vault mirrors and recovered documentation sync

Argus source/contract authority is its GitHub code repository. The vault is a
separate Git repository mirrored between the connected server Obsidian vault,
the actual local Obsidian vault, and its GitHub remote. These three vault copies
must not be confused with the Argus checkout or a temporary staging folder.

| Surface | Ownership | How it was identified |
| --- | --- | --- |
| Argus repository | Code, contracts and release status | GitHub `hermes-argus` and current `origin/main` |
| Local vault | Human project context; synchronized working copy | Obsidian's registered open-vault path and that directory's Git remote |
| GitHub vault | Shared versioned vault history | The local/server vault Git remote; separate from the Argus repository |
| Server vault | MCP-accessible project notes | Connected Obsidian MCP vault and its Git checkout |

An Obsidian MCP write edits the server vault. Its arrival in the other vault
copies is established by commit/push/pull and read-back, not by a successful
MCP response alone. Repository backlog `docs/BACKLOG.md` and vault index
`projects/hermes-argus/docs/BACKLOG.md` are different documents.

## Recovery — 2026-10-04

The October 4 and October 6 sections below are historical receipts. The current
restart state and synchronization receipt are recorded after them.

The maintainer repaired vault synchronization. Inspection found that the prior
audit had incorrectly treated a temporary `vault-stage` directory as the local
Obsidian vault. That directory is not an authoritative mirror, and its missing
Argus tree cannot prove that vault sync is broken.

A separate real regression was present: desktop backup `2d76b33` reverted the
Argus project card, release roadmap and heartbeat audit to older versions.
Server-side updates were recovered from pre-regression vault commit `4e835c3`
into the actual local vault. Current decisions were reapplied: RR1a merged but not deployed; RR1b
module/runtime truth merged as PR #71 but not deployed; RR1b host readiness is
the selected next contract; optional Netdata; native Cronping Telegram delivery
without an Argus webhook or an external-VPS prerequisite.

SYNC-001 records the repair/restoration receipt rather than an ongoing blocker.
The recovery was published as vault commit `bbc7571`; the server received it by
fast-forward. Normalized SHA-256 comparisons (LF/CRLF ignored) matched all six
changed Argus notes between local and server copies; the GitHub vault remote
contained the same commit. This verifies those restored notes, not every vault
file or an Argus deployment.
Use the vault Git history and changed-note parity to establish convergence;
a successful transport/sync process alone does not prove that the content is
the newest accepted project state.

The 2026-10-04 RR1b status update was published as vault commit `baa6648`.
Local vault, GitHub vault and server vault all point to that commit; normalized
SHA-256 values match for the four updated Argus notes. The receipt records PR
#71 as merged/not deployed, PR #73 as the selected host-readiness contract and
DEBT-021 in the readable vault backlog.

## Historical 2026-10-04 — RR1b implementation status before merge

Repository state moved on from the receipt above without a vault publication
yet. The host-readiness contract is implemented on branch
`feat/rr1b-host-readiness` from baseline `7245cf9` (PR #75); Linux `argus-ci`
is green at the recorded head, and the reviewer verdict is pending. Neither
merge nor deployment has happened. This note is the repository-side receipt
that the vault backlog and project card still show the older
"contract selected, builder ready" state.

## 2026-10-25 — restart programme through RR1

GitHub PR #75 merged on October 6 at `f433c53`; the old selected/review-pending
pointers were stale. This docs candidate reconciles source status and selects
A (Hermes compatibility), B (delivery/evidence), the authorized Ops checkpoint,
then C (RR1c/d). No runtime work or production deployment is claimed.

Before editing, the real local vault `D:/agenda` and MCP server versions of
the project card, canonical release roadmap and backlog index had matching
normalized bodies. The local vault was even with `origin/master`; unrelated
working changes for another project are excluded from this synchronization.
The three selected Argus notes were published as vault commit
`adf9228c54925ff2ae0d083f4580e16907534271`, with a link to
[contract PR #76](https://github.com/upmeister/hermes-argus/pull/76).
GitHub's commit API confirms exactly those three paths. The clean server vault
was fast-forwarded to that exact commit after checking that no other paths
would change. Local and server Git heads matched; MCP read-back confirmed
matching normalized bodies and `updated: 2026-10-25` for the project card,
canonical release roadmap and backlog index. Unrelated local work stayed
uncommitted and was neither included nor overwritten.

This verifies the selected notes, not the entire vault. The notes explicitly
say PR #76 is open, A starts after its merge, and production convergence is
unverified. The repository docs candidate records the same state; no deployment
or independent architecture-review PASS is implied by this sync receipt.

## 2026-10-26 — contract A implemented, PR #77 review pending

Contract A is implemented on branch `feat/restart-a-hermes-compat` from
baseline `11c7bcd` (main after the PR #76 merge) and opened as
[implementation PR #77](https://github.com/upmeister/hermes-argus/pull/77);
head `1b01ce1` carries the implementation plus this receipt. The reviewer
verdict is pending; neither merge nor deployment has happened. The vault
project card, release roadmap and backlog index were updated to this state.

Vault publication: local vault commit
`12357b0071901a51fa5298fc19e9e3fa98c4db75` ("hermes-argus: contract A
implemented as PR #77, Codex review pending") changes exactly the three Argus
notes (project card, `plans/2026-09-20-public-release-roadmap.md`,
`docs/BACKLOG.md`) and is pushed to the GitHub vault remote. The server vault
(`~/obsidian-vault`) reported the same commit as both HEAD and `origin/master`
with a clean tree (run `run_04eac362fc624fa98ed156871f403aed`, lane
`vault-sync`), so all three vault copies point at `12357b0`. This verifies the
selected notes, not the entire vault. The notes say review is pending and
production convergence remains unverified; no deployment or merge is implied.

## 2026-10-26 — contract A merged (PR #77), authority promoted to v0.22.5

PR #77 merged by maintainer authorization on 2026-10-26 (merge commit
`4adcd8f27532ece9c0bb49f8b897f41d4148b99b`, exact reviewed head `64eca82b`,
Codex final verdict GO/PASS-TO-MAINTAINER; one REMEDIATE remediation round
plus one maintainer-authorized targeted fix for the dashboard-unit
HERMES_HOME pin). Repository status surfaces were updated in the same change:
AGENTS.md authority block now names `v0.22.5 / bf0203a` as the accepted
stable authority, handoffs mark A DONE and B current, ROADMAP and both
backlog dispositions moved to "resolved in source, merged".

Vault publication: local vault commit
`0a864dc9c6d9b36e28bcc304ed31ba8cb537cb93` ("hermes-argus: контракт A
смержен (PR #77)") changes exactly the three Argus notes (project card,
`plans/2026-09-20-public-release-roadmap.md`, `docs/BACKLOG.md`) and is
pushed to the GitHub vault remote. The server vault was fast-forwarded
`274d0b8..0a864dc` (run `run_1ed16ad0aa4c4b2dbe8b2f1784435853`, lane
`vault-sync`); HEAD and `origin/master` both report `0a864dc` with a clean
tree. All three vault copies point at `0a864dc`. This verifies the selected
notes, not the entire vault. The notes keep production convergence
unverified: merged source is not a deployment, and the Ops checkpoint stays
separately authorized. An unrelated nail-bot note modified in the local
vault was left uncommitted, out of this synchronization.

## 2026-10-26 — contract B implemented, review pending

Contract B (delivery/evidence correctness) is implemented on task branch
`feat/restart-b-delivery-evidence` from base `f30ef67` (main after the PR #77
merge): heartbeat ping tokens moved to the stdin curl config, the configured
`TELEGRAM_PROXY` applied by the liveness senders and the weekly report, and
the `/watchdog` Analyzer freshness decision (7200 s). New probes b1/b2/b4 are
green on the candidate and RED on the baseline scripts; full suite 263 pass /
2 fail (the two known drvfs artifacts). Neither merge nor deployment has
happened.

Vault publication: local vault commit
`900fdca0c9bf749b5e393051679423217e1aee59` ("hermes-argus: контракт B
реализован на ветке") changes exactly the three Argus notes and is pushed to
the GitHub vault remote. The connected-server fast-forward is NOT yet
verified for this receipt — the Peetna MCP lane was unreachable at sync
time; the server copy must catch up at the next vault-sync before any
production work assumes vault convergence. The notes keep review pending and
production convergence unverified.

## 2026-10-26 — contract B merged (PR #78)

PR #78 merged by maintainer authorization on 2026-10-26 (merge commit
`e16ec0b9c3caeef467bedf644b806d0542069a54`, exact reviewed head `d396399`,
Codex final verdict GO/PASS-TO-MAINTAINER after one bounded remediation of
the two P2 probe gaps). Repository status surfaces were updated in the same
change: handoffs and ROADMAP mark B DONE, AGENTS.md names C as the next
gate (Ops checkpoint or explicit maintainer rollout deferral), and the
backlog records DEBT-013/014/019 as resolved-and-merged with deployment
verification staying at the Ops checkpoint.

Vault publication: the three Argus notes (project card,
`plans/2026-09-20-public-release-roadmap.md`, `docs/BACKLOG.md`) were edited
through the Obsidian MCP, which writes the server vault; the server's
auto-commit captured exactly those three files as vault commit
`83642afdcc642a112974851fa0ebd6c805f710e9` (+45/-15, verified by the server
agent over run lane `vault-sync-b-merge`: `PR #78` present in all three
notes, `DEBT-028` added to the backlog index, `git diff --stat
900fdca..HEAD` limited to the three Argus paths, `git status` clean). The
commit was already pushed to the GitHub vault remote; the local vault
(`D:/agenda`) was fast-forwarded `900fdca..83642af`. All three vault copies
now point at `83642af`. This also closes the previous receipt's unverified
server fast-forward: the server has caught up past `900fdca`, and the
900fdca..83642af delta contains only Argus notes. This verifies the
selected notes, not the entire vault; production convergence remains
unverified and separately authorized. Unrelated uncommitted changes in the
local vault (other projects) were left untouched.

## 2026-10-26 — authorized production rollout and Ops checkpoint complete

Maintainer-authorized deploy/device tests installed source
`17b3975927cec11783a314f68e614e7a4d12bb1c` at 02:05:10 UTC. The
[Ops receipt](DEPLOY_CHECKLIST.md#ops-receipt--2026-10-26) records template,
cron, host and service read-back plus real schedule survival. Repository status
surfaces name C as next eligible, not started. Mixed artifacts
[DEBT-026](BACKLOG.md#debt-026) are closed; catalog failures
[DEBT-027](BACKLOG.md#debt-027) are diagnosed/deferred, not healthy: 401 remains;
the earlier 404 check left the plan after a concurrent Hermes config update.
The 02:20 scheduled report contains 38 healthy / 1 failed / 2 unconfigured /
5 skipped, including three healthy MCP process checks. New
[DEBT-029](BACKLOG.md#debt-029) records stale bundled registry metadata/content
without changing either the 52 initial or the 46 later check plans.

Exactly three vault notes were updated through Obsidian MCP: project card,
canonical release roadmap and backlog index. Server commits `7907faf`,
`62c9f62` and `f39e1cfd82a17d16b01a8d11f2d08e958a5db16f` contain only these
paths; the server tree is clean and its HEAD equals GitHub `origin/master`
at `f39e1cf`.
MCP read-back matches all three intended note bodies. The local vault fetched
and merged those changes; `git diff origin/master -- <the three paths>` is
empty, confirming the same selected notes in all three copies.

Local vault HEAD is `6099f143d2854ba69e1cd6825a22a624322f2ad9`, not the
server SHA: a pre-existing unrelated local commit was retained, and three normal
merges imported the Argus updates. That unrelated commit/merge history was not
pushed. Three unrelated dirty files retained their exact before hashes. This
receipt establishes selected-note equality, not whole-vault history equality.

## 2026-10-26 — contract C implemented, focused review pending

The maintainer started C after the completed Ops checkpoint. Implementation is
on `feat/restart-c-versioned-lifecycle` from `5551579`: exact stable/edge/tag
selection, selected-tree bootstrap, old-source ownership checks and a bounded
uninstall plan/apply. Reviewer remains **Codex**, merge is maintainer-owned.
No C deployment, uninstall, tag or release was performed. The existing Ops
runtime source remains `17b3975`; this is source work, not a new rollout.

The project card, canonical release roadmap and backlog index were updated
through Obsidian MCP and published as server vault commit
`95c5613972f481eee72e07536bf3dc54ab176a6f`. The commit changes exactly those
three Argus notes and is pushed to GitHub. MCP read-back matches the intended
note bodies; the local vault fetched/merged that commit and its selected-note
diff against `origin/master` is empty. Unrelated local commits and dirty files
were retained (dirty-file before/after hashes matched), and their history was
not pushed. As with the Ops receipt, selected-note equality does not imply
equal whole-vault heads.

## Historical 2026-10-26 — C6 remediation before the maintainer merge

Codex reviewed exact C head `9ee3531` (PR #79) and returned REMEDIATE for one
P1/C6 blocker: uninstall removed an adapter referenced by preserved Hermes
fallback base units. The one local remediation retains both shared adapter
copies and adds a fixture executing both retained units' actual ExecStart argv
through a stub CLI after plan/apply/repeat. No new out-of-scope finding was
reported. Final focused-review evidence belongs to PR #79; the maintainer gate
remains pending, with no C merge/deployment/uninstall/release claim.

The same three selected vault notes now name PR #79, the pending maintainer
gate and this retention rule. Server publication
`95865db1e0b523c87f6b44862b5d4c1eb598c007` changes only those notes and is pushed
to GitHub. MCP read-back matches intended bodies; the local vault fetched and
merged it, and its three-note diff against `origin/master` is empty. Unrelated
local commits and dirty content were retained without publication; tracked
dirty-file hashes matched before/after. Whole-vault heads need not be equal.

## 2026-10-26 — readiness/observation contract selected

PR #79 merged at `fd947a0`; C is source-complete and not deployed, and the
A/B/C programme reached STOP. The maintainer accepted the independent review
and selected its first follow-up: DEBT-030/028/022 plus the DEBT-031 manual
recovery recipe, in one implementation PR. Local Ubuntu 24.04 WSL/VMware comes
first; any final production trial needs its own exact-SHA/action authorization.

This docs candidate corrects the repository's stale C pointers, records A's
accepted bootstrap/run_path refinement and links the new selected contract.
The project card, canonical roadmap and backlog index will be synchronized
with the same merged-versus-deployed distinction. The earlier sections above
are dated history, not current task pointers. A publication/read-back receipt
will be added before the docs PR handoff; no runtime/deployment claim follows
from documentation sync.

## Future status-update procedure

1. Identify the actual Obsidian vault and its Git remote before diagnosing sync.
2. Preserve newer local/server edits and recover regressed content from history.
3. Commit and push selected note changes through the vault's established flow.
4. Verify the corresponding GitHub and server versions; compare relevant notes.
5. Update the Argus backlog/index and project pointers when state changes.

Do not treat temporary staging directories as vaults or close runtime
deployment gates based on restored documentation. The recovery does not change
RR1b's frozen implementation contract or perform an Argus deployment.
