# hermes-argus project contract

## Purpose and boundary

`hermes-argus` is the registry-driven monitoring and watchdog kit for Hermes
Agent integrations. It owns discovery, integration health checks, fallback
tracking, watchdog modules, and their deployment manifests. Hermes Agent source
and user secrets are outside this repository.

Ownership split: Hermes owns interpretation of its runtime configuration —
provider routing, profile selection, credential resolution, and
protocol-specific runtime semantics. Argus owns discovery orchestration,
independent external verification policy, watchdog state, hysteresis/alerts,
and reporting.

Argus is not a second Hermes runtime, a generic Hermes compatibility layer, or
an application-level sandbox around a trusted local Hermes installation.

## Scope control — mandatory

The requested scope is a **maximum**, not a minimum.

Do only the behavior explicitly requested by the task and its acceptance
criteria. Do not add adjacent features, generalized abstractions,
defense-in-depth subsystems, new configuration knobs, new persistent state,
migration machinery, integrity verification, compatibility frameworks, or
unrelated cleanup unless the maintainer explicitly approves them.

A blocker outside the approved scope is a finding to report, not permission to
fix it.

### Stop instead of expanding

STOP implementation and return a concise scope/blocker report if resolving a
finding would require any of:

- a new subsystem or security boundary;
- changes outside the named functional surface;
- more than one new production entrypoint;
- a new dependency;
- a new persistent state format;
- pinning an upstream historical revision;
- sandboxing, interpreter/worktree integrity verification, supply-chain
  verification, or OS-security emulation in application code;
- changing legacy behavior that the task says to preserve;
- hundreds of new lines for a bug expected to be local;
- a second remediation cycle.

These are not forbidden forever. They require an explicit maintainer scope/value
decision before implementation continues.

### Reviewer authority

A reviewer may fix only a defect that directly violates an explicit acceptance
criterion and can be corrected locally without expanding architecture.

A reviewer MUST NOT:

- implement wishlist items discovered during review;
- broaden the threat model on its own;
- redesign adjacent code;
- add generic hardening "while here";
- create or delegate new workstreams without maintainer approval;
- launch repeated independent review waves automatically.

Default review loop:

```text
one implementation pass
-> one focused review
-> at most one remediation pass
-> re-read the exact committed/staged tree once
-> merge decision OR stop and return blockers to maintainer
```

Do not use instructions such as "remediate through as many loops as needed".

### Threat model

Assume the local OS account, intentionally installed Hermes checkout/venv, and
code intentionally installed for Hermes are trusted to the degree required to
run Hermes itself.

Protect against accidental secret disclosure, malformed/unexpected data,
upstream drift, hangs, false-green classifications, unintended network/process
activity, and ordinary programming/deployment mistakes.

Do not attempt to defend Argus against a malicious same-user Hermes
installation, hostile native extensions, deliberate filesystem tampering by an
actor with write access to the user's home, or compromised local dependencies.
Those require OS-level isolation under a separately approved project.

### Work admission and complexity budget

Before a non-trivial implementation task, be able to state:

```text
problem -> evidence -> smallest patch -> owning path -> explicit non-goals
```

If a small-sounding task begins to require multiple new files, a new abstraction
layer, or a large amount of compatibility/security plumbing, treat that as
evidence that the design is wrong and STOP for maintainer review.

## Source of truth and deployment

- Repository scripts, module manifests, `registry.yaml`, and `deploy.sh` are
  the source templates.
- `deploy.sh` installs the selected modules into the user's Hermes home and
  scripts directory (`$HOME/.hermes/` and `$HOME/scripts/`).
- Generated `registry.yaml` is produced by `scripts/gen-registry.py`; do not
  hand-edit generated entries.
- Runtime copies must be compared with the repository templates after a deploy.

## Invariants

- Secrets stay in protected runtime environment/secret files. Never commit,
  print, or persist credential values, Authorization headers, or provider
  response bodies.
- Integration statuses remain distinct: `ok`, `fail`, `unconfigured`, and
  `skipped` (legacy projection), with canonical verdicts `healthy`, `failed`,
  `unknown`, `unconfigured`, `skipped` per ADR 0001. Presence of a key is not
  proof that an external API works. A passing check must state which evidence
  claims it proved; transport, key presence, anonymous responses, `404`s, or
  rate limits are never promoted into authentication or semantic success
  without an explicit contract. `unknown`, `unconfigured`, and `skipped` never
  reset a failure counter.
- Authenticated semantic checks must declare their method, expected status,
  content type/schema, and safe side-effect boundary. Regular checks are
  read-only; deep/active checks are separate.
- Honcho checks use the configured workspace queue route and must reject path
  injection, non-JSON success responses, invalid credentials, and rate limits.
- Deployment templates must not leave unresolved `@MARKER@` placeholders.

## Verification commands

```bash
python3 -m py_compile scripts/health-check-v2.py scripts/gen-registry.py tests/probes.py
bash -n deploy.sh
python3 tests/probes.py
git diff --check
```

The GitHub Actions `argus-ci` job is the required remote regression check for
`main` and pull requests.

## Secret and operational boundary

`config.env` and Hermes `.env` files are local/runtime configuration, not
repository configuration. Do not place API keys, bot tokens, chat IDs, private
hostnames, or production response data in source, tests, changelog, PR text, or
reports. Production deployment and branch-protection changes require explicit
maintainer authorization and read-back verification.

## Known traps

- `hermes mcp test` can return exit code zero for a failed connection; parse
  its output markers.
- API roots may return `404` by design; use an authenticated semantic route
  rather than treating an API-root response as a health proof.
- Systemd `.path` units need an explicit `Unit=` when the triggered service
  name differs from the path unit name.
- After deployment, inspect installed files and service state; a successful
  shell command alone is not deployment evidence.

## References

- `docs/adr/0001-integration-evidence-policy.md` — evidence claims, canonical
  verdicts, and side-effect policy.
- `docs/adr/0002-hermes-discovery-sync-boundary.md` — historical Hermes
  discovery/sync architecture record. Its production bridge migration is
  superseded by the 2026-09-17 stabilization plan unless explicitly reopened.
- `README.md` — user-facing product and module overview.
- `CHANGELOG.md` — user-facing changes in Keep a Changelog format.
- `scripts/gen-registry.py` — registry generation contract.
- `tests/probes.py` — fixture-driven regression and security probes.
- Canonical active roadmap in the Obsidian vault:
  `projects/hermes-argus/plans/2026-09-17-architecture-reset-and-stabilization-plan.md`.
