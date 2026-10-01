# hermes-argus project contract

## Purpose and boundary

`hermes-argus` is an external watchdog and observability layer for Hermes
Agent. It owns discovery orchestration, integration health verification,
fallback observation, watchdog policy/state, alerts and deployment manifests.
Hermes Agent source and user secrets are outside this repository.

Ownership split: Hermes owns interpretation of runtime configuration — provider
routing, profile selection, credential resolution/rotation and
protocol-specific runtime semantics. Argus owns external observation,
independent verification where useful, watchdog state, hysteresis/alerts and
operator reporting.

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

### Delivery roles

Active contracts are role-based, not tied to a particular model, vendor, or
agent product:

- **Builder** — implements exactly the selected contract and supplies evidence.
- **Focused reviewer** — adversarially checks the contract and may request one
  bounded remediation.
- **Maintainer** — selects scope, resolves blockers, performs the final exact-head
  gate, and alone authorizes merge/deploy/release actions.

Changing which tool or model fills a role does not change the contract.

Pytna is the default focused reviewer across projects and is reached through
the Peetna MCP. Unless the task names another reviewer, send Pytna the
implementation PR link and the source handoff from the contract/docs PR, plus
the exact candidate head, scope, acceptance criteria, constraints, and focused
review questions. Check Peetna health first; start the review only after the
handoff is ready, then read the completed result before deciding on remediation.

Reviewer assignment is per-contract and may be changed by the maintainer at any
time. The Pytna default is **not** currently in effect (maintainer is trialing a
new review pipeline); until further notice every contract names its reviewer
explicitly, and a contract that names none has no assigned reviewer.

A task assignment that links a documentation PR as its active contract counts
as acceptance and authorizes merging that contract PR before implementation.
Base implementation work on the resulting `main`. An implementation task
authorizes a task branch, commit, push, and opening or updating its PR by
default, unless the maintainer sets a local-only or no-publication constraint.
Implementation PR merges, deploys, releases, and production actions require
separate authorization.

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

### Work admission and complexity budget

Before a non-trivial implementation task, be able to state:

```text
problem -> evidence -> smallest patch -> owning path -> explicit non-goals
```

If a small-sounding task begins to require multiple new files, a new abstraction
layer, or a large amount of compatibility/security plumbing, treat that as
evidence that the design is wrong and STOP for maintainer review.

## Source of truth and deployment

- Repository scripts, module manifests, `registry.yaml`, `install.sh` and
  `deploy.sh` are source templates.
- `deploy.sh` installs selected modules into the user's Hermes home and scripts
  directory.
- Generated `registry.yaml` comes from `scripts/gen-registry.py`; do not
  hand-edit generated entries.
- Runtime copies must be compared with repository templates after deploy.

Repository layout of authority:

- The GitHub repository is the **source of truth**.
- A local Git checkout is a **working copy**; treat a stale local `main` as a
  hazard and reconcile against `origin/main` before basing work on it.
- The **production deployment** lives on the maintainer's VPS (`peetna-aws`).
  Local agents may reach it over SSH; Linux deploys and runtime tests are
  technically possible from a local agent, but the safer and preferred path is
  to route production deploys through the agent resident on that server (Pytna,
  via the Peetna MCP).
- Deploy, merge and production actions still require explicit, separate
  maintainer authorization regardless of which agent performs them.

### Keep the docs truthful after every change

Any change that alters state — a merged PR, a new release gate, an upstream
authority bump, a changed contract status — must update the documents that
describe that state **in the same change**, not in a follow-up:

- `docs/handoffs/README.md` — current/selected contract and completion status;
- `docs/ROADMAP.md` — release path and upstream authority;
- `AGENTS.md` — release direction and the upstream authority block;
- `CHANGELOG.md` — user-facing change;
- the Obsidian project card (vault) when the change moves project state.

Status surfaces must never lag merged reality: a merged contract is not "NOW",
and a gate that has moved is not the current gate. A change that ships without
its doc update forces the next agent — or the maintainer returning after a pause
— to re-derive the wrong state. This is exactly how R2c.1 looked unfinished for
a week after PR #49 had already merged.

## Invariants

- Secrets stay in protected runtime environment/secret files. Never commit,
  print, persist, or place credential values/Authorization headers in child
  process argv.
- Integration statuses remain distinct: `ok`, `fail`, `unconfigured`,
  `skipped` with canonical schema-v2 verdicts. Presence of a key is not proof
  that an external API works.
- Authenticated semantic checks declare their method, expected status,
  content/schema and safe side-effect boundary.
- Regular monitoring is read-only with respect to credential state.
- Static account-auth evidence is inventory evidence, not runtime login health.
- Unknown/unconfigured/skipped never reset a failure counter.
- Deployment templates must not leave unresolved `@MARKER@` placeholders.

## Verification commands

At minimum:

```bash
python3 -m py_compile scripts/health-check-v2.py scripts/gen-registry.py tests/probes.py
bash -n deploy.sh
python3 tests/probes.py
python3 tests/test_watchdog_swap.py
git diff --check
```

Task contracts may require additional syntax/proc/installer checks.

The GitHub Actions `argus-ci` job is required for pull requests and `main`.

## Secret and operational boundary

`config.env` and Hermes `.env` are local/runtime configuration. Do not place
API keys, bot tokens, chat IDs, private hostnames, or production response data
in source, tests, changelog, PR text, or reports.

Production deployment, service restart, public release/tag publication and
branch-protection changes require explicit maintainer authorization.

## Known traps

- Supported Hermes stable v0.21.4 gives `hermes mcp test` useful exit codes:
  0 connected, 1 connection failed, 3 server missing. Argus still parses the
  established output markers for backward compatibility; do not assume the old
  "always zero" behavior or remove marker parsing inside an unrelated task.
- API roots may return `404` by design; use authenticated semantic routes.
- Systemd `.path` units need explicit `Unit=` when the service name differs.
- After deployment, inspect installed files and service state; successful shell
  exit alone is not deployment evidence.
- `health-check-integrations.sh` already uses stdin for secret-bearing curl
  config; R1c must not create competing stdin consumers and regress R1b.

## Current release direction

Public release path:

```text
R1c DONE
 -> R2a/R2a.1 DONE
 -> R2c.1 DONE / PR #49
 -> RR0 legacy/personal-dependency reduction   <-- CURRENT GATE
 -> RR1 installer/dependency/managed-cron hardening
 -> RR2 runtime i18n (en + ru)
 -> RR3 release acceptance
 -> v0.1.0-rc.1
```

Public docs remain English-only. Runtime English/Russian localization is a
release-readiness task, not permission to duplicate documentation.

## References

- `README.md` — public product/status overview.
- `docs/ROADMAP.md` — public release roadmap.
- `docs/handoffs/README.md` — active implementation authority.
- `docs/adr/0001-integration-evidence-policy.md` — evidence/verdict policy.
- `docs/adr/0002-hermes-discovery-sync-boundary.md` — historical bridge record.
- `CHANGELOG.md` — Keep a Changelog user-facing history.
- `scripts/gen-registry.py` — registry generation contract.
- `tests/probes.py` — regression/security probes.
- Canonical planning roadmap in the Obsidian vault:
  `projects/hermes-argus/plans/2026-09-20-public-release-roadmap.md`.


## Current upstream authority — 2026-10-01

```text
Hermes stable = v2026.9.24 / v0.21.5
stable tag commit = f97608f178d1ffeca59860195ab7da295f7c8e5f
previous warning-source main = 35b14ad5e24137b836d5c47c21a50c6ea7aeb785
```

Stable authority wins. Upstream `main` is a warning/research source only.

Upstream watches: `docs/research/2026-10-01-hermes-upstream-watch.md` (current).
Argus' dependency-on-Hermes list: `docs/research/hermes-argus-seams.md` — an
upstream watch re-verifies that list rather than reading the whole changelog.
