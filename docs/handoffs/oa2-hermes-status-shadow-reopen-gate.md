# OA2 gate — Hermes account-status shadow

Status: **CLOSED / UPSTREAM-GATED — NO IMPLEMENTATION PR AUTHORIZED**

Baseline decision:

```text
OA0 / PR #33 = DONE
decision = STATIC ONLY
supported Hermes stable = v2026.9.14 / v0.21.3
stable commit = 345cd2b057a452236de401d3534b8502a7465e8d
```

Latest upstream watch recorded 2026-09-21:

```text
latest stable = v2026.9.14 / v0.21.3
Hermes main = 64c7da592d43a9f155ea8606865d9ae1eda3222b
stable unchanged
```

## Decision

Do not implement OA2 against the current supported stable release.

Do not poll `GET /api/providers/oauth` from Argus.

OA2 may be reconsidered only after an upstream-owned stable/tagged seam satisfies
the reopen conditions below.

## Why OA0 closed OA2

OA0 proved that the endpoint is attractive semantically but unsafe as an Argus
monitoring dependency on v0.21.3:

- pool-only Codex is represented correctly;
- the endpoint exposes Hermes-owned account/login semantics;
- it is profile-aware;

but:

- provider status behavior was not uniformly refresh-free;
- Qwen refresh-validates by design;
- response cards contain `token_preview`;
- the production-style public-bind auth gate has no supported headless machine
  route registered for `/api/providers/oauth`.

A monitor must not mutate or refresh the credential state it is observing.

## 2026-09-20 upstream convergence

Fresh `main` has moved materially toward the seam Argus wants.

### Codex

`get_codex_auth_status()` is now explicitly documented:

```text
Read-only by contract: status/doctor must never adopt, refresh or persist a credential.
```

It calls the Codex resolver with `read_only=True`.

This closes a major **fresh-main** concern from the original OA0 experiment.

### Nous

Hermes now exposes `get_nous_auth_status_local()`, explicitly described as a
refresh-free snapshot for read-only display surfaces.

### xAI

The current xAI status path resolves with
`refresh_if_expiring=False`.

These are meaningful architectural convergence signals.

## Why OA2 is still closed

The full gate is not satisfied.

1. **Stable authority has not moved.**
   The supported stable release is still v0.21.3 / `v2026.9.14`.

2. **Qwen still refresh-validates.**
   `get_qwen_auth_status()` calls its runtime resolver with
   `refresh_if_expiring=True`.

3. **The OAuth response still contains token previews.**
   `/api/providers/oauth` builds status cards containing `token_preview`.

4. **The required machine-auth route is still absent.**
   The generic machine/dashboard bearer-token machinery does not currently
   register `/api/providers/oauth` as the narrow supported machine status
   endpoint Argus needs.

5. **Provider-wide no-side-effect proof is incomplete.**
   Progress on Codex/Nous/xAI does not establish the required invariant for
   every surfaced account provider.

Therefore:

```text
OA2 remains CLOSED.
Fresh-main convergence is tracked as upstream progress, not implementation authority.
```

## 2026-09-21 follow-up watch

From the prior `f88c6fc4...` watch to `64c7da59...`, fresh main advanced
951 commits. The gate still does not reopen.

Verified on the refreshed head:

- `get_codex_auth_status()` remains explicitly read-only and uses
  `read_only=True`;
- Qwen `get_qwen_auth_status()` still calls
  `resolve_qwen_runtime_credentials(refresh_if_expiring=True)`;
- OAuth provider cards still carry `token_preview`;
- repository registration search for the generic `register_token_route` seam
  still shows no `/api/providers/oauth` registration (the live production
  registration is the drain plugin route).

Stable remains v0.21.3. Therefore OA2 stays **CLOSED / UPSTREAM-GATED**.

## Reopen conditions

OA2 may be reopened only when a **stable/tagged Hermes version** provides all of
the following or an equivalent explicitly documented contract.

### 1. Refresh-free account-status semantics

The account-status read used by Argus must not:

- refresh access/refresh tokens;
- exchange credentials;
- call provider quota/auth endpoints;
- materialize credentials from external stores;
- change cooldown/dead/exhausted state;
- write `auth.json` or provider-owned credential files.

This must hold for every provider surfaced by the endpoint.

### 2. Supported headless authentication

A local/non-interactive Argus process must have an upstream-supported machine
authentication path for the status surface.

Acceptable examples:

- the route is explicitly registered on Hermes' machine-token auth seam;
- a documented local control socket/machine endpoint exposes the same
  refresh-free data.

Not acceptable:

- dashboard-cookie automation;
- borrowing an interactive browser session;
- weakening the dashboard gate;
- an Argus patch inside Hermes.

### 3. No-secret response contract

The machine/status response must not include token material or token previews.

Minimum useful fields:

```text
provider id
logged_in / connected boolean
stable source class, if useful
profile identity, when requested
```

Argus does not need access/refresh tokens, previews, fingerprints, account email
or credential IDs.

### 4. Isolated regression proof

Before OA2 implementation is authorized, repeated synthetic reads across:

- healthy/non-expiring;
- expired;
- provider/network failure;
- pool-only credential state;

must prove:

```text
0 auth-store writes
0 credential refresh/exchange attempts
0 provider-network requests
0 subprocess/external CLI materialization
```

### 5. Stable provider-universe semantics

The endpoint must have a documented account-provider universe useful to Argus.
Plugin/provider limitations must be explicit.

## Upstream-watch triggers

Revisit this gate when a stable release changes:

- `get_codex_auth_status` / `_pool_first_oauth_status`;
- Nous/Qwen/xAI account-status behavior;
- `GET /api/providers/oauth`;
- machine token-route registration;
- a new machine-readable refresh-free auth/account endpoint.

Fresh `main` changes are warning/research signals only.

## Non-goals

This gate does not authorize:

- an OA2 shadow PR today;
- a Hermes fork/patch;
- a runtime-import bridge;
- polling `hermes auth list`;
- polling `/api/credentials/pool`;
- dashboard-cookie automation;
- multi-profile implementation.

## Current action

OA phase is complete. Continue the release-oriented stabilization path beginning
with R1c. OA2 remains a passive upstream watch.
