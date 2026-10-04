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

## Future status updates

1. Identify the actual Obsidian vault and its Git remote before diagnosing sync.
2. Preserve newer local/server edits and recover regressed content from history.
3. Commit and push selected note changes through the vault's established flow.
4. Verify the corresponding GitHub and server versions; compare relevant notes.
5. Update the Argus backlog/index and project pointers when state changes.

Do not treat temporary staging directories as vaults or close runtime
deployment gates based on restored documentation. The recovery does not change
RR1b's frozen implementation contract or perform an Argus deployment.
