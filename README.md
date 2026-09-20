# hermes-argus

**External watchdog and observability layer for [Hermes Agent](https://github.com/NousResearch/hermes-agent).**

Hermes can keep running while part of its environment has silently degraded: a
provider falls back, an MCP server disappears, an API key stops working, a
gateway becomes unhealthy, or a dependency starts returning the wrong thing.
Argus exists to make those failures visible.

It discovers the integrations a Hermes deployment depends on, verifies what can
be checked safely from the outside, tracks fallback/runtime failures, watches
the host and Hermes services, and reports operator-facing degradation without
trying to become a second Hermes runtime.

> **Project status:** pre-release, actively used in maintainer production. The
> monitoring core and clean-VM bootstrap have both been exercised, but the
> public distribution contract is still being hardened. The current release
> path targets a GitHub `v0.1.0-rc.1` after the remaining security,
> fail-safe, installer and localization gates are closed.

## Why this exists

Hermes already owns the hard runtime decisions:

- provider/model routing;
- credential resolution and rotation;
- fallback selection;
- profile/session state;
- protocol-specific runtime behavior.

Argus deliberately does not duplicate those internals. Instead it answers the
operator questions Hermes runtime success alone cannot answer:

- Did an integration disappear from configuration?
- Is the credential present but not actually verified?
- Did the primary model fall back without the operator noticing?
- Is the gateway/service alive but operationally stuck?
- Did a self-hosted dependency stop serving the expected route/schema?
- Is the host approaching a memory/swap failure mode?
- Did the monitoring host itself disappear?

The boundary is:

```text
Hermes owns runtime truth.
Argus observes externally, verifies independently where useful, and makes failures loud.
```

## Architecture

```text
                    Hermes Agent
        config / auth state / logs / services
                       |
                       v
                 hermes-argus
        +--------------+---------------+
        |              |               |
        v              v               v
    discovery       health          watchdog
    + change        + evidence       + liveness
      tracking        checks           + remediation
        |              |               |
        +--------------+---------------+
                       |
                       v
              operator surfaces
          Telegram / reports / alerts
                       |
                       +--> optional external heartbeat
```

Argus reads stable external artifacts and performs bounded independent checks.
It does not import Hermes runtime provider logic in production, refresh OAuth
credentials, execute plugin discovery to build inventory, or claim complete
knowledge of every upstream plugin/provider.

## Current capabilities

### Integration discovery

Argus builds an inventory from the deployment surfaces that are safe to inspect
statically and tracks added/removed/changed entities.

Current coverage includes:

- configured providers and model routes;
- environment-backed integrations;
- MCP servers;
- selected auxiliary/runtime dependencies;
- static persisted account-auth evidence, including modern OpenAI/Codex nested
  and credential-pool storage.

Static credential evidence is intentionally **not** reported as runtime login
health:

```text
credential evidence present
!= logged in
!= healthy
```

### Integration health

The health engine keeps evidence classes separate instead of collapsing
everything into green/red.

Canonical outcomes include:

- healthy;
- failed;
- unknown;
- unconfigured;
- skipped / policy-blocked.

Checks can verify HTTP status, authenticated routes, response content
type/schema, local service state and selected MCP behavior. Deep model checks
are separate from the regular low-side-effect monitoring path.

### Fallback observation

Argus watches Hermes runtime logs for provider/model fallback transitions and
primary recovery. It makes silent fallback cascades visible without trying to
reimplement Hermes' own fallback engine.

### Host and service watchdog

The core watchdog covers areas such as:

- Hermes gateway/dashboard liveness;
- process/systemd state;
- network reachability;
- disk and memory/swap pressure;
- cron integrity;
- bounded auto-remediation;
- SSL expiry and update checks.

Systemd memory-limit drop-ins can protect small VPS deployments from runaway
memory pressure.

### Operator control plane

The optional Telegram module provides interactive monitoring/status commands
and alert delivery.

A Discord module exists as an optional/experimental control-plane surface, but
Telegram is the maintained reference operator UI today.

### External dead-man heartbeat

Optional backends can detect the failure mode Argus cannot report from the dead
host itself.

Current integrations include:

- Cronping;
- Dead Man's Snitch;
- an optional GitHub Actions heartbeat workflow.

## Modules

`deploy.sh` uses explicit manifests and installs only enabled modules.

| Flag | Purpose | Default |
| --- | --- | --- |
| `MODULE_CORE` | watchdog, liveness, remediation, resource/network checks | ON |
| `MODULE_INTEGRATIONS` | discovery, fallback tracking, health-check v2 | ON |
| `MODULE_TG_BOT` | Telegram monitoring/control bot | OFF |
| `MODULE_ANALYZER` | L3/LLM-assisted health analysis | OFF |
| `MODULE_HEARTBEAT` | external dead-man heartbeat client | OFF |
| `MODULE_GH_HEARTBEAT` | GitHub heartbeat repo/workflow provisioning | OFF |
| `MODULE_DISCORD_BOT` | Discord control plane | OFF |

External-service modules are off by default.

## Installation today

The current bootstrap targets **Ubuntu 24.04** and expects Hermes Agent to
already be installed for the same user.

```bash
git clone https://github.com/upmeister/hermes-argus.git
cd hermes-argus
bash install.sh
```

`install.sh` installs the current base dependencies, creates `config.env`,
runs the module-aware deploy, enables the config watcher and performs
post-deploy checks.

This is still a **pre-release installation path**. In the current tree, the
generated Argus cron entries still require a manual merge step, and dependency /
upgrade / uninstall ownership is being hardened before the first public RC.
Do not treat today's `main` bootstrap as the final one-command release
installer.

For manual/development deployment, see `config/config.env.template` and
`deploy.sh`.

## Safety and evidence rules

Argus is conservative by design.

- Secret values must not be committed, logged, rendered into reports or placed
  in child process argv.
- A configured key is not proof that an external API works.
- An anonymous `200`, API-root `404`, rate limit or transport success is not
  silently promoted into authentication/semantic success.
- Unknown/unconfigured/skipped checks do not reset failure hysteresis.
- Regular monitoring avoids credential refresh/mutation.
- Static auth inventory does not pretend to validate OAuth sessions.
- Runtime copies are deployed from explicit repository manifests rather than
  wildcard-copying a user's Hermes directories.

The local OS account and intentionally installed Hermes code are trusted.
Argus is designed to catch operational mistakes and silent degradation, not to
sandbox a malicious same-user Hermes installation.

## Localization

The maintainer production deployment currently uses a Russian operator UI and
that experience will remain supported.

The public-release target is:

```text
runtime/operator UI: English + Russian
machine-readable schema/markers: language-neutral
README and project documentation: English only
```

Existing Russian installations must not silently switch language during an
upgrade. The localization work belongs to the release-readiness phase; it is not
implemented by duplicating the documentation tree.

## Compatibility and Hermes upstream

Argus follows supported Hermes releases first and watches upstream `main` for
drift.

Current supported research baseline:

- Hermes Agent v0.21.3 / `v2026.9.14`;
- Linux/systemd-oriented personal-server deployment;
- Ubuntu 24.04 is the current installer test target.

Hermes upstream is moving toward safer read-only account-status surfaces, but
Argus still keeps OAuth runtime-status integration upstream-gated: some provider
status paths can still refresh, the dashboard OAuth response still exposes
token previews, and there is not yet a suitable stable machine-authenticated
no-secret endpoint for Argus.

That is intentional. Argus prefers a stable upstream observation seam over
becoming a second credential resolver.

## Roadmap

The current path to the first public release is intentionally bounded:

```text
R1c  Authorization headers out of child argv — DONE
 -> R2a  malformed YAML fail-safe — DONE
 -> R2c.1  canonical fallback_providers inventory — NOW
 -> legacy/personal-dependency reduction
 -> installer/dependency/managed-cron hardening
 -> runtime i18n: English + Russian
 -> clean install / upgrade / uninstall acceptance
 -> v0.1.0-rc.1
 -> soak
 -> v0.1.0
```

Broader auxiliary discovery, cleanup/reduction and multi-profile monitoring are
separate follow-up tracks.

See [docs/ROADMAP.md](docs/ROADMAP.md) for the detailed public plan.

## Tests and development

The repository has a required GitHub Actions `argus-ci` check plus local
regression probes.

Typical gates:

```bash
python3 -m py_compile scripts/health-check-v2.py scripts/gen-registry.py tests/probes.py
bash -n deploy.sh
python3 tests/probes.py
python3 tests/test_watchdog_swap.py
git diff --check
```

Behavioral/security fixes should add focused regression coverage, preferably a
test that demonstrably fails on the prior implementation and passes on the
candidate.

Before changing behavior, read [AGENTS.md](AGENTS.md) and the single active
contract under [docs/handoffs/](docs/handoffs/).

## Documentation

- [Public roadmap](docs/ROADMAP.md)
- [Pre-release legacy/personal-dependency audit](docs/research/2026-09-21-pre-release-legacy-audit.md)
- [Project/agent contract](AGENTS.md)
- [Integration evidence policy](docs/adr/0001-integration-evidence-policy.md)
- [Hermes discovery boundary ADR](docs/adr/0002-hermes-discovery-sync-boundary.md)
- [Implementation handoffs](docs/handoffs/README.md)
- [Changelog](CHANGELOG.md)

Historical handoffs remain useful research records, but their presence does not
make them current implementation authority.

## Release model

The planned public distribution is a **versioned GitHub Release** with an
installer pinned to the release tag.

`main` will remain the development/edge channel rather than silently changing
what an existing release installer downloads.

The first public artifact is expected to be a pre-release (`v0.1.0-rc.1`),
followed by stable `v0.1.0` after a short real-world soak.

## License

MIT. Independent community project; not affiliated with or endorsed by Nous
Research.
