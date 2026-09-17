# R2b contract — gateway liveness research record

Status: **DEFERRED / NOT AUTHORIZED FOR IMPLEMENTATION**

> Superseded on 2026-09-18 by production/upstream evidence. The earlier proposal
> to treat `gateway_state.json.updated_at` as an always-advancing event-loop
> heartbeat is incorrect for the currently supported Hermes deployment.

## Why this contract is deferred

`scripts/gateway-liveness.sh` currently infers event-loop liveness from the Hermes housekeeping/memory-trim log marker:

```text
memory trim: reason=messaging gateway housekeeping
```

The earlier R2b proposal attempted to replace that signal with freshness of:

```text
gateway_state.json.updated_at
```

That migration is **not safe** on the currently supported production Hermes.

Evidence gathered on 2026-09-18 established:

- a healthy idle gateway may leave `gateway_state.json.updated_at` unchanged for many hours;
- current upstream explicitly notes that an idle gateway does not advance that field;
- upstream stale-status handling combines persisted state with process/pid state as tombstone logic rather than treating timestamp age alone as proof of a frozen event loop;
- production showed an old `updated_at` while the gateway remained healthy and the current housekeeping marker remained fresh.

Using timestamp freshness as specified by the original contract would therefore create false-positive hang detection and could cause a restart loop on a healthy idle gateway.

## Current decision

For the current stabilization line:

```text
keep existing memory-trim/housekeeping liveness signal
DO NOT migrate to gateway_state.json.updated_at freshness
DO NOT implement the old acceptance matrix
```

This file remains only as a record of the disproven direction and its stop decision.

## What may reopen R2b

A new implementation contract requires one of:

1. a future Hermes release exposes and documents a stable external event-loop heartbeat/liveness endpoint or persisted field, and production evidence confirms its behavior; or
2. a separate research-first task demonstrates a safe externally observable HTTP/event-loop probe with acceptable false-positive/side-effect characteristics.

A new research task must begin with evidence. It must not assume the old design is valid merely because this file exists.

## Current owner behavior

`scripts/gateway-liveness.sh` is **not an active implementation owner under R2b** right now.

Ordinary bug fixes to the current liveness script still require their own concrete incident/evidence and separately selected task.

## Non-goals while deferred

Do not:

- reinterpret file mtime as a substitute heartbeat without evidence;
- import `gateway.status` or Hermes internals;
- invent a new heartbeat daemon;
- broaden into multi-profile gateway supervision;
- change memory trimming merely to manufacture a monitoring signal;
- bundle gateway-liveness experimentation into R1b/R2a/R2c.

## Stop rule

If an agent reaches this document from an old roadmap/handoff, STOP and return to the active execution baseline. No R2b implementation is authorized until the maintainer explicitly selects a new research/implementation contract.
