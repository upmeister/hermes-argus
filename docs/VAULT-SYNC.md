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

## Future status-update procedure

1. Identify the actual Obsidian vault and its Git remote before diagnosing sync.
2. Preserve newer local/server edits and recover regressed content from history.
3. Commit and push selected note changes through the vault's established flow.
4. Verify the corresponding GitHub and server versions; compare relevant notes.
5. Update the Argus backlog/index and project pointers when state changes.

Do not treat temporary staging directories as vaults or close runtime
deployment gates based on restored documentation. The recovery does not change
RR1b's frozen implementation contract or perform an Argus deployment.
