# hermes-argus

**Always-watching guardian for [Hermes Agent](https://github.com/NousResearch/hermes-agent).**

Argus keeps every tool and integration your Hermes relies on in working order —
and tells you the moment something degrades. Hermes itself fails silently: a
provider switches to fallback without a word, an MCP server dies, a self-hosted
service disappears — and the agent keeps running without it. Argus makes those
failures loud.

## What it does

- **Integration discovery** — watches `config.yaml` (systemd.path + cron safety
  net); when you add or remove a key/provider/MCP server, Argus notices and
  alerts. No restart needed.
- **Fallback cascade tracking** — parses agent logs and alerts on the first
  primary-model failure, on reaching a free-tier model, and on recovery.
- **Watchdog & liveness** — binary checks every 2–5 min (systemd units, disk,
  swap, cron integrity) with auto-restart on hangs and Telegram alerts.
- **Memory limits via systemd drop-ins** — MemoryHigh/Max/SwapMax presets so a
  runaway agent never kills the whole VM.
- **Dead-man's switch** — external heartbeat (GitHub Actions / Dead Man's
  Snitch / Cronping) so a dead VM still gets noticed.

## Requirements

- Linux VPS (any size — "weak VPS" is where it shines, but power is irrelevant)
- Hermes Agent installed
- A Telegram bot for alerts (Discord support planned)

## Quick start

```bash
git clone https://github.com/upmeister/hermes-argus.git
cd hermes-argus
cp config/config.env.template config.env   # fill in your values
./deploy.sh
```

See the Modules section below. Deploy installs only what you enable — anything
requiring external services is off by default.

## Modules

`deploy.sh` deploys by explicit manifests, filtered by `MODULE_*` flags in
`config.env` (see `config/config.env.template`):

| Flag | Installs | Default |
|------|----------|---------|
| `MODULE_CORE` | watchdog, liveness checks, auto-remediate, network-guard, ssl-expiry, check-updates | ON |
| `MODULE_INTEGRATIONS` | integration discovery (+ systemd.path watcher), fallback cascade tracker | ON |
| `MODULE_TG_BOT` | interactive Telegram control-plane bot (poller + webhook) | OFF |
| `MODULE_ANALYZER` | L3 health-analyzer ecosystem (LLM log analysis) | OFF |
| `MODULE_HEARTBEAT` | external dead-man's switch (Dead Man's Snitch / GitHub) | OFF |

Cron lines for enabled modules are generated to `/tmp/hermes-argus-crontab.txt`
— merge them into your crontab, deploy never touches it directly.

## Development baseline

Argus is in a stabilization-first phase. C1a runtime-bridge productionization
remains stopped.

Completed:

```text
R1a / PR #29 = DONE
R1b / PR #31 = DONE
OA0 / PR #33 = DONE / STATIC ONLY
OA1 / PR #35 = DONE / MERGED
```

OA1 fixed the demonstrated OpenAI/Codex inventory false negative with generic
static auth-store discovery and also removed the false-green projection that
treated persisted OAuth evidence as "logged in".

The current selected task is **OA1b: OAuth evidence rendering semantics**.
After OA1 deployed successfully, production exposed a presentation bug: the
correct conservative `skipped` verdict is shown to users as bare
`⏸ ... — пропущено`, losing the distinction that credentials were actually
found but runtime login/health was intentionally not verified.

```text
OA1b NOW
 -> OA-close
 -> OA PHASE COMPLETE
 -> R1c Authorization-header argv debt

OA2 = CLOSED / UPSTREAM-GATED
```

Current Argus main:

```text
cfa6c535518e3d3ad9b78c20d442335f48e84fd6
```

OA1 reviewed PR head:

```text
abb7ceecd805fe4c4ffc1f90248a562be88de051
```

All four OA1 changed blobs are identical between that reviewed head and merged
main. PR-head CI run #61 passed static checks and regression probes.

The OA semantic boundary remains:

```text
persisted credential evidence present
!= logged in
!= healthy
```

Latest supported Hermes stable remains v0.21.3 / `v2026.9.14`. Fresh upstream
`main` moved to `03c9fc892f5cf3f2e02aa4a4888a30ae292d256d`,
but the account-status/auth surfaces relevant to the OA2 reopen gate have not
changed since the previous watch. OA2 remains closed.

Before contributing work, read:

1. `AGENTS.md`;
2. `docs/handoffs/README.md`;
3. `docs/handoffs/2026-09-17-next-steps-execution-baseline.md`;
4. exactly one maintainer-selected task contract.

Current contract:

```text
docs/handoffs/oa1b-oauth-evidence-rendering-contract.md
```

Multi-profile remains a separate track.

## Status

Pre-release, under active development. Breaking changes expected before v0.1.

## License

MIT — see LICENSE. Independent community project, not affiliated with or
endorsed by Nous Research.
