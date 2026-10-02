# RR0c contract — public defaults and naming migration

Status: **QUEUED AFTER RR0b / IMPLEMENTATION-READY**

RR0c removes maintainer-specific assumptions from a public installation while
keeping the existing maintainer deployment migratable and explicit. It is the
last RR0 slice before RR1 installer hardening.

## 1. Sequence and authority

RR0c starts from the merged `main` after RR0b. It must not be implemented on
top of a stale local branch or an unmerged RR0b candidate.

Research authority:

- [`docs/research/2026-09-21-pre-release-legacy-audit.md`](../research/2026-09-21-pre-release-legacy-audit.md), sections B1–B4;
- current `deploy.sh`, `config/config.env.template`, systemd templates,
  registry generation, and runtime readers.

Focused reviewer: **Codex**, the current project architect/reviewer.

Production risk: **high**. This slice changes defaults and may affect existing
runtime resources.

Merge authority: **maintainer merge after reviewer PASS**. The reviewer may
prepare the exact merge command but may not merge this contract's implementation
PR automatically.

## 2. Required public-install outcome

A new installation must not silently assume the maintainer's proxy, GitHub
repository, historical project name, bot identity, or provenance strings.
Existing maintainer production must retain an explicit migration path and must
not be silently flipped by a clean reinstall or an ordinary upgrade.

The implementation must begin with a migration receipt that records, without
secrets:

- the current public default for each surface;
- the current maintainer production value and whether it is implicit;
- the new explicit configuration or resource name;
- the read-back and rollback path.

## 3. Required implementation pass

### B1 — Telegram smart-proxy assumption

Find every runtime path that falls back to `127.0.0.1:8444`. Make proxy use an
explicit configuration choice at the public boundary. A host with no proxy
configured must follow the documented direct/disabled behavior for that path;
it must not silently target a personal local service.

Preserve the maintainer deployment by making its current proxy choice explicit
before changing the effective production behavior. Do not add a new proxy
implementation or a second configuration system.

Completion criterion: a clean public configuration has no undeclared proxy
dependency, every remaining proxy consumer has one documented source, and the
maintainer migration path is tested without exposing its value.

### B2 — GitHub heartbeat ownership

Remove the personal `upmeister/hermes-infra` default. The GitHub heartbeat
backend must be disabled or require an explicit repository when no repository
is configured. Preserve the existing secret-safe heartbeat behavior when the
operator supplies a repository and token.

Completion criterion: no public default points at the maintainer repository;
enabled heartbeat setup fails clearly or remains disabled without an explicit
repository, and the configured-repository path remains covered by a probe.

### B3 — project/resource naming migration

Choose Argus-owned canonical names for new installs and update the templates,
runtime lookups, and operator instructions consistently. Preserve existing
`hermes-vps-kit-*` units and `~/hermes-vps-kit/config.env` long enough for a
bounded compatibility handoff; do not delete or auto-move live state.

The migration must avoid two active producers for the same function. If safe
unit/config migration requires RR1 installer machinery, stop at that boundary
and return the concrete prerequisite instead of redesigning RR1 inside RR0c.

Completion criterion: new-install names are Argus-owned, an existing legacy
installation has a documented detection and operator-controlled handoff, and
the tests prove that the two names cannot both become active owners silently.

### B4 — personal bot/provenance strings

Remove behavior-bearing personal bot handles and maintainer-specific defaults
from public runtime behavior. Keep operator-configured values and historical
provenance that explains a compatibility decision. Cosmetic archival cleanup is
out of scope.

Completion criterion: a public install contains no personal behavior default,
and every retained user-visible identity comes from explicit configuration or
an intentional product label.

## 4. Invariants and non-goals

- Do not place credentials, private hostnames, production response data, or
  current maintainer values in source, tests, changelog, PR text, or receipts.
- Do not silently change the existing Russian production behavior.
- Do not add an installer/cron/dependency framework; RR1 owns that contract.
- Do not remove legacy resources or perform production migration in the PR.
- Do not redesign Telegram, heartbeat, gateway, or health semantics unrelated
  to the four surfaces above.

Stop and return the migration receipt if preserving production requires a
one-off destructive migration, an unbounded compatibility layer, or a second
production entrypoint.

## 5. Required evidence

The implementation receipt must include:

- exact baseline and candidate head;
- the migration receipt for B1–B4;
- clean-install and existing-install fixture results;
- proof that generated registry/settings output has no unresolved markers;
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

1. a personal default still reachable through a fallback path;
2. a clean install that silently depends on a proxy or GitHub repository;
3. a maintainer installation changed without an explicit migration step;
4. both legacy and canonical units becoming active owners;
5. secrets or private production values leaking into the migration receipt;
6. RR1 installer hardening entering the patch;
7. missing backlog entries for deferred findings.

Return `PASS-TO-MAINTAINER`, `REMEDIATE`, or `BLOCKED-FOR-MAINTAINER`, with at
most one bounded remediation pass.
