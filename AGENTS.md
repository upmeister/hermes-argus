# hermes-argus project contract

## Purpose and boundary

`hermes-argus` is the registry-driven monitoring and watchdog kit for Hermes
Agent integrations. It owns discovery, integration health checks, fallback
tracking, watchdog modules, and their deployment manifests. Hermes Agent source
and user secrets are outside this repository.

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
  `skipped`. Presence of a key is not proof that an external API works.
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

- `README.md` — user-facing product and module overview.
- `CHANGELOG.md` — user-facing changes in Keep a Changelog format.
- `scripts/gen-registry.py` — registry generation contract.
- `tests/probes.py` — fixture-driven regression and security probes.
- Hermes integration-monitoring conventions and the project research notes in
  the canonical Obsidian vault.
