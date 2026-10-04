# Monitoring sources and alert delivery

This describes the shipped source at `ed3661f` after RR1a / PR #68. The
maintainer has not deployed RR1a yet. Source behavior, installation state and
successful alert delivery are separate facts.

## The `WATCHDOG ALERT` message

The message headed `WATCHDOG АЛЕРТ` is assembled by
[`hermes-watchdog.sh`](../scripts/hermes-watchdog.sh), which also sends it to
Telegram using the configured watchdog bot/chat. The optional interactive
poller is not required for this outbound send.

| Message row | Actual source | What it establishes |
| --- | --- | --- |
| Dashboard unavailable / responding | Bounded curl request to the configured dashboard URL | HTTP reachability; not every dashboard capability |
| Gateway process count | `hermes-gateway-pids.py`, delegating process identification to Hermes | Matching gateway processes, not end-to-end model health |
| Disk utilization | `df` on the root filesystem | Current disk occupancy |
| RAM utilization | `free -h` | Current RAM utilization |
| Swap occupancy / memory pressure | `/proc/meminfo`, `/proc/vmstat`, `/proc/pressure/memory`, with Argus sampling/hysteresis | Occupancy and pressure signals; swap occupancy alone does not trigger a pressure alert |
| Health-check fresh | `last_check` in Analyzer's `health-state.json`, when ANALYZER is enabled | State timestamp freshness; not proof that the Hermes L3 agent ran or delivered its analysis |
| Integrations OK | Exit/output of `health-check-integrations.sh --quick` | That quick compatibility check's result; not the complete v2 integration inventory |

No RAM, swap or disk value in this message comes from Netdata. The quick
checker does currently probe Netdata API availability, so a Netdata failure
can reach the watchdog as an integration problem. This remaining optionality
gap is tracked as [DEBT-007](BACKLOG.md#debt-007).

## Where Netdata is used

**Netdata is an optional, operator-provisioned enhancement.** Argus does not
install it and does not require its metrics for the basic watchdog message.
Choosing to retain it provides historical host trends; choosing to omit it
does not remove the native OS disk/memory/process observations above.

Current uses:

- [`health_netdata.py`](../scripts/health_netdata.py) queries
  `/api/v1/data` for RAM, CPU, load, disk I/O and network charts over the last
  hour. It computes min/max/average/latest values from the returned points.
- [`health-analyzer.py`](../scripts/health-analyzer.py) includes these trends
  when active issues or a daily/weekly digest need them. Unavailable chart
  data is reported as unavailable; the Analyzer's raw-metrics collector is a
  separate script dependency ([DEBT-008](BACKLOG.md#debt-008)).
- The legacy quick checker and [`webhook.py`](../scripts/webhook.py) probe
  Netdata `/api/v1/info`. These test availability rather than consume its RAM
  or CPU data. Their present absence-as-failure behavior is not the accepted
  optional-extension policy and needs a bounded runtime correction.
- [`watchdog-health.sh`](../scripts/watchdog-health.sh) checks an installed
  Netdata system service's activity, skipping an absent service.

Native Netdata alert evaluation and delivery are owned by Netdata. Argus
neither consumes a Netdata alarm webhook nor configures its Telegram notifier.
The earlier production audit confirmed metrics/API access, but did not
establish native Telegram delivery. Historical comments describing the old
delivery route are not an installation contract.

Keep a pre-existing Netdata installation when its trends are useful. Its
installation and notification configuration are separate operator steps; the
accepted roadmap must not silently provision it or declare it healthy solely
because a package or API endpoint exists.

## Other monitoring layers

| Layer | Producer / reader | Delivery or ownership |
| --- | --- | --- |
| Gateway/dashboard liveness | The respective liveness shell scripts | Bounded restart/alert paths; separate from the composite watchdog message |
| Integration v2 | Discovery snapshot -> health-check-v2 -> alert wrapper | Structured evidence and existing stateful Telegram alerts |
| Fallback observation | `fallback-tracker-v2.py` reads Hermes runtime logs | Existing Telegram route |
| Local services | Topology snapshot -> configured manifest comparison | Opt-in read-only monitoring of operator-selected services |
| Analyzer / L3 | Argus produces metrics/state; a separately configured Hermes job consumes analysis input | The Hermes job/model/destination are not created by installing ANALYZER |
| External heartbeat | Argus sends a liveness ping/timestamp; an external backend detects its absence | Backend notification setup is independent of local bot polling and must survive monitored-host loss |

See the [dependency audit](research/2026-10-03-production-deployment-dependencies.md)
for deployment prerequisites and the [backlog](BACKLOG.md) for unresolved
behavior. A future public heartbeat setup guide is tracked separately; it has
not been supplied by a successful ping alone.
