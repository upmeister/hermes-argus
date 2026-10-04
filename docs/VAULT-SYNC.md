# Project documentation surfaces and vault sync

The project deliberately has three documentation surfaces with different
ownership:

| Surface | Canonical role | Current location/evidence |
| --- | --- | --- |
| GitHub repository | Code, contracts, roadmap, backlog and release status | `upmeister/hermes-argus`; repository `main` is authoritative |
| Server Obsidian vault | Project navigation, decisions and readable receipts | Connected Obsidian MCP vault; note URIs resolve under `/home/ubuntu/obsidian-vault` |
| Windows vault stage / local Obsidian view | Maintainer's local working mirror | `C:\Users\covhnw\vault-stage\files` is currently a partial stage, not a complete Argus mirror |

The repository is the source of truth. Vault notes mirror project state for
human navigation; they do not override merged repository documents. A vault
write through the Obsidian MCP writes the connected server vault. It does not
automatically create a Windows `vault-stage` file or a repository file.

## Current Argus sync finding вЂ” 2026-10-04

The server vault contains:

- `projects/hermes-argus/README.md`;
- `projects/hermes-argus/docs/BACKLOG.md`;
- the release roadmap and heartbeat audit.

The inspected Windows stage contains other project notes but no
`projects/hermes-argus/` tree. Therefore the expected three-way propagation is
**not currently verified**. This is a synchronization/infrastructure finding,
not evidence that the backlog write failed: the note is readable from the
connected server vault.

Until the sync path is repaired, use these rules:

1. Read GitHub `main` for implementation and status truth.
2. Read the connected server vault for the current readable project index.
3. Treat the Windows stage as stale/missing when the project tree is absent;
   do not infer that a note was never written.
4. Do not manually copy a server note into the repository. The repository
   backlog remains `docs/BACKLOG.md`; the vault index remains
   `projects/hermes-argus/docs/BACKLOG.md`.

## Required sync repair

The sync owner must identify the process that populates `vault-stage` and make
it perform a deterministic project-tree check. At minimum, a successful sync
must prove that these paths exist and have matching current state links:

- project card / README;
- project roadmap;
- project backlog index;
- latest research and selected-contract pointer.

The repair needs its own small operational task. It is outside RR1b and no
agent should claim three-way synchronization until the local stage contains
the Argus tree and the check records which source revision/date it mirrors.
