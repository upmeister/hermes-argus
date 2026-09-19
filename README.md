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
OA1b / PR #39 = DONE / MERGED
OA-close = DONE — OA PHASE COMPLETE
```

OA1 fixed the demonstrated OpenAI/Codex inventory false negative with generic
static auth-store discovery and also removed the false-green projection that
treated persisted OAuth evidence as "logged in". OA1b renders that static
evidence as informational ("credentials found; runtime status not verified")
instead of generic skipped, without changing canonical verdicts or schema.

The next queued task is **R1c: Authorization-header argv debt**. No contract is
currently selected: per `AGENTS.md` the maintainer selects the task, and its
contract is authored/activated at that point.

```text
OA PHASE COMPLETE
 -> R1c Authorization-header argv debt
 -> R2a malformed YAML
 -> R2c bounded static compatibility
 -> R3 cleanup/stabilization

OA2 = CLOSED / UPSTREAM-GATED
```

Current Argus main:

```text
12739f8c4fbd597606653281a6c4b1898a2b00a4
```

OA1b reviewed PR head:

```text
a58075f7cbf21dc2b629e71749dadbe2b3e8972f (PASS-TO-MERGE)
```

The OA semantic boundary remains:

```text
persisted credential evidence present
!= logged in
!= healthy
```

Latest supported Hermes stable remains v0.21.3 / `v2026.9.14`. Fresh upstream
`main` moved to `00570550f37e9082676955d50f65c7d9ba846cc9` and changed
`auth_codex.py` / `web_routers/oauth.py` (partial refresh-free improvement for
nous listing), but `token_preview`, refresh and persist paths remain and no
stable release satisfies the OA2 reopen gate. OA2 remains closed.

Before contributing work, read:

1. `AGENTS.md`;
2. `docs/handoffs/README.md`;
3. `docs/handoffs/2026-09-17-next-steps-execution-baseline.md`;
4. exactly one maintainer-selected task contract.

Current contract:

```text
R1c contract (to be selected/added by the maintainer)
```

Multi-profile remains a separate track.

## Status

Pre-release, under active development. Breaking changes expected before v0.1.

## License

MIT — see LICENSE. Independent community project, not affiliated with or
endorsed by Nous Research.
