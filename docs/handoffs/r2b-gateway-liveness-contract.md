# R2b contract — gateway liveness from Hermes runtime status

Status: **READY FOR IMPLEMENTATION AFTER R1/R2a**

## Problem

`scripts/gateway-liveness.sh` currently infers event-loop liveness from a log line produced by Hermes periodic memory trimming:

```text
memory trim: reason=messaging gateway housekeeping
```

That signal is incidental. Fresh Hermes exposes a more direct external contract: `gateway_state.json` is periodically refreshed by the gateway event loop, and upstream itself uses `updated_at` / status freshness to distinguish a live process from stale runtime state.

Argus should consume the direct persisted status signal rather than allocator-maintenance logging.

## Owner

Primary owner: `scripts/gateway-liveness.sh`.

Allowed adjacent path: tests only.

## Target behavior

Keep the existing high-level watchdog policy:

1. if the gateway process/service is not running, do not compete with the service manager's normal crash restart path;
2. if the process is running, inspect the Hermes-owned runtime status file for liveness freshness;
3. stale/missing/unparseable status is suspicious, not immediate proof of a hang;
4. perform the existing second-check delay before restart;
5. restart and alert only after the second observation still proves the event loop stale;
6. preserve dedup and quiet recovery behavior.

## Source of truth

For default-profile v0.1, read the default Hermes home's `gateway_state.json` directly. Use the persisted `updated_at` (or file mtime only as a documented compatibility fallback if the exact deployed Hermes format requires it).

Do not import `gateway.status` or other Hermes Python modules.

The threshold may remain conservative around the existing 180-second Argus policy even if upstream currently uses a 120-second stale TTL. The contract is about changing the signal, not aggressively changing restart policy.

## Fail-safe rules

- malformed JSON -> log diagnostic, do not blindly restart on the first observation;
- missing `updated_at` -> treat as unknown/suspicious and require second observation;
- future timestamp or nonsensical timestamp -> unknown/suspicious, not healthy;
- stale status with a dead process -> let service-manager crash handling own recovery;
- fresh status -> clear incident state and emit existing quiet recovery if one was active.

## Acceptance criteria

Fixtures/tests cover at least:

- running process + fresh `updated_at` -> no restart;
- running process + stale `updated_at`, then fresh on second check -> no restart;
- running process + stale on both observations -> restart path selected;
- malformed/missing runtime status does not produce a one-shot destructive false positive;
- dead process remains outside the hang-restart path;
- dedup/recovery semantics preserved;
- no dependency on the `memory trim` log marker remains in liveness decision logic.

## Non-goals

- multi-profile gateway supervision;
- multiplexed gateway routing;
- replacing systemd/service-manager responsibilities;
- changing memory trimming;
- importing Hermes internals;
- adding a generic status adapter layer.

## Stop condition

If the deployed Hermes runtime status cannot provide a stable timestamp/state contract on the supported installation, stop and return exact evidence before inventing a new heartbeat mechanism.
