# OA2 gate — Hermes account-status shadow

Status: **CLOSED / UPSTREAM-GATED — NO IMPLEMENTATION PR AUTHORIZED**

Baseline decision:

```text
OA0 / PR #33 = DONE
decision = STATIC ONLY
supported Hermes stable = v2026.9.14 / v0.21.3
stable commit = 345cd2b057a452236de401d3534b8502a7465e8d
```

Latest upstream watch recorded 2026-09-19:

```text
latest stable = v2026.9.14 / v0.21.3
Hermes main = 1e4952ddba1bc585416ad43438d60183380035cd
OA0-observed main = d177b119e9c56c9ddc0b7379ffce52341ec06584
drift = +602 commits
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

- status resolution can refresh credentials and access the network;
- the exact-tag degraded/expired Codex path was empirically reproduced writing
  credential cooldown state into `auth.json`;
- Qwen status refresh-validates by design;
- response cards contain `token_preview`;
- the production-style public-bind auth gate has no supported headless machine
  route registered for `/api/providers/oauth`.

A monitor must not mutate or refresh the credential state it is observing.

## 2026-09-19 upstream watch

Fresh `main` partially improves one OA0 blocker.

Current `_pool_first_oauth_status` now documents and uses pool `peek()` as an
observation instead of credential `select()`. Upstream explicitly notes that
speculative status refresh/benching previously caused persisted cooldown
problems and moves that behavior away from the pool observation path.

This is useful upstream progress, but it does **not** reopen OA2:

1. `get_codex_auth_status()` still falls through to
   `resolve_codex_runtime_credentials()` when pool observation cannot return a
   usable entry;
2. the resolver still defaults to `refresh_if_expiring=True`;
3. successful Codex refresh still writes the rotated credential pair;
4. `get_qwen_auth_status()` still calls its runtime resolver with
   `refresh_if_expiring=True`;
5. OAuth response cards still include `token_preview`;
6. the generic dashboard bearer-token seam exists, but
   `/api/providers/oauth` is not registered as a token-authable route;
7. the latest stable release remains v0.21.3, so the supported Argus target has
   none of the fresh-main improvement anyway.

Therefore the OA0 production decision remains `STATIC ONLY`.

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

This must hold for every provider surfaced by the endpoint, not just Nous or
Codex.

A helper explicitly analogous to the current local/refresh-free Nous snapshot
for all relevant account providers would satisfy the architectural direction.

### 2. Supported headless authentication

A local/non-interactive Argus process must have an upstream-supported machine
authentication path on the production public-bind deployment shape.

Acceptable examples:

- the route is explicitly registered on Hermes' machine-token auth seam;
- a documented local control-socket/machine endpoint exposes the same
  refresh-free data.

Not acceptable:

- scraping/holding dashboard cookies;
- borrowing an interactive browser session;
- reading a dashboard session token that the public-bind gate ignores;
- weakening the dashboard gate;
- adding an Argus patch inside Hermes.

### 3. No-secret response contract

A dedicated machine/status response should not include token material or token
previews.

If the general dashboard response still carries those fields, OA2 must have an
upstream-provided narrower response or prove that the Argus caller cannot
receive/retain them.

Minimum useful fields would be:

```text
provider id
logged_in / connected boolean
stable source class, if useful
profile identity, when requested
```

No access token, refresh token, preview, fingerprint, account email or
credential id is needed by Argus.

### 4. Isolated regression proof

Before OA2 implementation is authorized, run a small supported-version probe
with synthetic credentials proving repeated reads across:

- healthy/non-expiring state;
- expired credential state;
- provider/network failure;
- pool-only credential state;

cause:

```text
0 auth-store writes
0 credential refresh/exchange attempts
0 provider-network requests
0 subprocess/external CLI materialization
```

Unknown is not sufficient for a polling dependency.

### 5. Stable provider-universe semantics

The endpoint must have a documented account-provider universe useful to Argus.

If plugin/account providers remain excluded by upstream picker/catalog rules,
that limitation must be explicit. OA2 must not claim universal provider
coverage.

## Upstream-watch triggers

Revisit this gate when any of these change in a stable release:

- `get_codex_auth_status` / `_pool_first_oauth_status`;
- Qwen account-status behavior;
- `GET /api/providers/oauth`;
- dashboard token-route registration for the OAuth status endpoint;
- a new machine-readable refresh-free auth/account endpoint.

Fresh `main` changes are warning signals only.

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

Finish OA1 static discovery.

After OA1 passes final acceptance, close the OA phase and return to the queued
stabilization track.
