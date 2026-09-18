# OA0 outcome — account-auth discovery research

Status: **RESEARCH COMPLETE — decision recorded below. No production code in this PR.**

Contract: `docs/handoffs/oa0-account-auth-discovery-research-contract.md`.

## Exact baselines

- Argus main researched against: `48188b88d04be4cc823d92b42036231b7a2fb993`
  (PR #32 merge; code identical to the contract baseline `2238928` — PR #32 is docs-only).
- Hermes stable tag (compatibility authority): `v0.21.3` (`v2026.9.14`) =
  `345cd2b057a452236de401d3534b8502a7465e8d` — verified on the production
  checkout: the commit subject at that SHA is literally
  `chore(release): v0.21.3 (v2026.9.14)`.
- Hermes main observed SHA (warning only, what production actually runs, editable
  install): `d177b119e9c56c9ddc0b7379ffce52341ec06584` — 2096 commits ahead of
  the supported tag. Tag→main drift is **substantive** in the exact modules
  that own refresh/persistence side effects (`hermes_cli/auth.py`,
  `agent/credential_pool.py`); the `GET /api/providers/oauth` handler itself is
  unchanged apart from two additional fields (`retryable`, `retry_after`) on
  the OAuth session **poll** endpoint. Therefore:
  side-effect semantics were **source-verified at the tag** (authority), the
  empirical probes were **captured on main@prod** (labeled per claim), and the
  reviewer (Pytna) **independently reproduced all probe results at the exact
  tag** — see "Probe provenance" in Appendix B.
- All source citations below are from the tag unless explicitly marked `main@prod`.

Evidence classes are labeled per contract §8: **[source]** = tag source read,
**[prod]** = read-only production observation, **[empirical]** = isolated
throwaway-home probe with synthetic credentials only.

## Demonstrated Argus gap

### Current parser assumption [source]

`scripts/integration-discover.py`:

- `OAUTH_FLOWS = ("nous", "openai-codex", "xai-oauth", "qwen-oauth", "minimax-oauth")` — fixed list;
- layer 4 reads `auth.json` and creates an `oauth:<flow>` entity only when
  `providers.<flow>.access_token` is present and non-empty (a **flat** field on
  the provider object);
- `credential_pool` is never read (no reference to it anywhere in the file);
- Copilot is a separate `.env`-key channel.

### Codex actual supported-tag shapes [source]

- Singleton state: `_read_codex_tokens` (`hermes_cli/auth_codex.py`) requires
  `providers["openai-codex"]["tokens"]` — a **nested** dict with `access_token`
  and `refresh_token` — plus `last_refresh` on the provider state. The flat
  `providers.openai-codex.access_token` that Argus checks does not exist for
  Codex.
- Pool state: `credential_pool.openai-codex[]` rows (`agent/credential_pool.py`,
  `PooledCredential`) with `auth_type`, `source`, `access_token`,
  `refresh_token`, cooldown fields. Re-auth mirrors the singleton into the pool
  (`_sync_codex_pool_entries`); pool-only operation is explicitly supported
  (`resolve_codex_runtime_credentials` falls back to the pool, issue #32992).
- Status preference: `get_codex_auth_status` is documented "pool first, then
  legacy provider state"; pool-only credentials **are** considered logged in
  (see seam probe below).

### Why current detection misses it [prod] + [empirical]

- Production `~/.hermes/auth.json` (structure only, values never read or
  printed): `providers.openai-codex` = `{tokens: {access_token, refresh_token},
  last_refresh, auth_mode}` — nested only. `providers.nous` is the one provider
  in the flat shape.
- Production Argus snapshot (`~/.hermes/state/integration-snapshot.json`)
  contains exactly `oauth:nous` and `oauth:copilot (pat-only)`.
  **`oauth:openai-codex` is absent although a live Codex account is configured** —
  the user-visible false negative.
- Empirical reproduction (Probe A, local synthetic fixtures, `HERMES_DIR`
  override; Appendix A): with a nested Codex singleton (future-`exp` JWT) and
  a pool-only Codex entry, `integration-discover.py` emits only
  `["oauth:nous"]`; with a pool row **only**, it emits zero oauth entities and
  exits silently. Both shapes invisible, pool-only case isolated.

## Scope definition

- **Model/account auth in scope**: nous, openai-codex, xai-oauth, minimax-oauth,
  qwen-oauth, anthropic (Hermes-managed PKCE + pool), copilot-acp, claude-code
  (external CLI store), and any provider whose evidence lives in the persisted
  auth store (`providers`/`credential_pool` sections) that Argus can read
  statically. Credentials held **only** in external CLI files or ambient cloud
  SDK chains (Codex CLI `~/.codex/auth.json`, Vertex ADC/OAuth2, Bedrock IAM
  chain, Azure Foundry Entra ID, Copilot OS keychain) are **bounded known
  misses**, not coverage claims — see taxonomy.
- **Excluded OAuth domains** (per contract): MCP OAuth, Spotify/tool OAuth,
  memory-provider OAuth, dashboard/user identity, connector/session auth,
  arbitrary third-party OAuth files, multi-profile implementation.
- Distinguish `logged_in/connected` (Hermes runtime claim) from
  `credential evidence present` (what static data can honestly assert) from
  health (independent checks). OAuth-as-acquisition-flow vs
  OAuth-as-persisted-credential-type are classified separately (e.g. an
  OAuth/PKCE-acquired key that Hermes persists as an `api_key` pool row is
  reported by its persisted `auth_type`, not its acquisition history).

## Hermes auth storage taxonomy

Store: `$HERMES_HOME/auth.json` (0600, parent 0700, atomic writes, flock;
`hermes_cli/auth.py`). Top-level sections: `version`, `providers{}`,
`credential_pool{}`, `active_provider`, `updated_at`.

| provider/class | singleton shape (`providers.<id>`) | pool shape (`credential_pool.<id>[]`) | external source | generic static rule possible? | notes |
|---|---|---|---|---|---|
| nous | `access_token`, `refresh_token`, `agent_key`, expiry/scope fields — **flat** | oauth rows carry token material | — | yes (flat) | the only flat-shape provider in production today |
| openai-codex | `tokens.{access_token, refresh_token}`, `last_refresh`, `auth_mode` — **nested** | oauth rows carry token material | Codex CLI `$CODEX_HOME`/`~/.codex/auth.json` (`_import_codex_cli_tokens` reads it; `_recover_codex_tokens_from_cli` adopts the pair into the Hermes store) — runtime-visible **before** any Hermes-store state exists | yes (nested + pool); CLI-file state is a known miss | the demonstrated false negative |
| xai-oauth | tag: xai writes via `_save_xai_oauth_tokens` with write-through to global root | prod pool key is `xai` (alias drift vs provider id `xai-oauth`) | — | yes, with id-alias caution | same single-use refresh family as codex |
| minimax-oauth | flat `access_token` + `expires_at`/`region` (oauth state) | possible | — | yes | status path is local-only at tag |
| qwen-oauth | none (Hermes keeps none) | possible | Qwen CLI auth file (`_qwen_cli_auth_path()`) | pool yes; CLI file = external, opt-in read | status refresh-validates (see seam section) |
| anthropic | none (PKCE file instead) | rows (incl. `sk-ant-oat*` tokens auto-typed `oauth` by `_normalize_pool_auth_type`) | `$HERMES_HOME/.anthropic_oauth.json` (Hermes-owned) | yes (pool + Hermes-owned file) | dashboard card reads PKCE file + env vars |
| claude-code | none | possible (borrowed) | `~/.claude/.credentials.json` | external file, opt-in read | borrowed sources are metadata-only at rest |
| copilot-acp | none | possible | `~/.copilot/config.json`, `~/.config/github-copilot/*` (JSONC/JSON), `COPILOT_*` env | external files, opt-in read | CLI may hold session in an OS keychain Hermes cannot read — absence is not logged-out |
| api-key pool rows (gemini, openrouter, clinepass, cline, cline-pass, opencode-go, …) | — | **source-qualified storage**: borrowed env/CLI sources persist **metadata + `secret_fingerprint` only** (secret stripped at the disk boundary, hydrated at load); `manual`/`manual:*` rows and rows whose `(provider, source)` is in `_PERSISTABLE_PROVIDER_SOURCES` (e.g. `anthropic/hermes_pkce`) **can carry the raw credential at rest** (`agent/credential_persistence.py`: "Owned sources pass through unchanged") | env / gh CLI / provider CLI | yes, as credential-evidence rows | `secret_fingerprint` is derived key material; raw values in owned rows must never be read or emitted by Argus |
| vertex | none in auth.json (GCP OAuth2 service account / ADC chain) | possible | GCP ADC / service-account chain (`gcloud` state, workload identity) | no — ambient cloud chain, **known miss** | canonical description: "OAuth2 service account or ADC" |
| bedrock | none in auth.json (AWS SDK credential chain) | possible | AWS IAM env/profile/IMDS chain | no — ambient cloud chain, **known miss** | canonical description: "IAM or API key" |
| plugin-added account providers | whatever the plugin writes via Hermes' own store APIs (`providers`/`credential_pool` sections are generic) | possible | plugin-owned | store rows: yes; **the seam: no, with one typed exception** | plugin extension skips auth_types `{oauth_device_code, oauth_external, external_process, aws_sdk, copilot, vertex}`; the sole `_ACCOUNTS_AUTH_TYPES` member outside the skip-set is `oauth_minimax`, so only a plugin explicitly typed `oauth_minimax` reaches the seam — `models_catalog_static.py` + `provider_catalog.py`; the `oauth.py` docstring claiming automatic appearance is inaccurate at the tag |
| azure-foundry | none in auth.json for `auth_mode: entra_id` (no store tokens) | possible | Microsoft Entra ID via `azure-identity` (ambient credential chain); `api_key` mode = `AZURE_FOUNDRY_API_KEY` env | api_key mode: yes (env presence); entra_id mode: no — ambient chain, **known miss** | status helper deliberately never probes the chain (`credential_probe: not_run`) — `hermes_cli/auth.py` |

Key structural facts [source]:

- `auth_type` persisted values: `oauth` | `api_key`; **legacy rows missing
  `auth_type` default to `api_key`** on load (`PooledCredential.from_dict`
  accepts the persisted value unchecked). The `_normalize_pool_auth_type`
  re-typing of `anthropic` `sk-ant-oat*` tokens to `oauth` happens **only at
  runtime, after reading the secret value** — a static reader cannot replicate
  it without violating the secret boundary and must not try; persisted
  `auth_type` is used as-is.
- `source` values include `device_code`, `loopback_pkce`, `hermes_pkce`,
  `manual`, `manual:*`, `env:<VAR>`, `gh_cli`-style borrowed sources.
  `_EXPLICIT_POOL_SOURCES` = `{device_code, loopback_pkce, hermes_pkce, manual}`
  (+ `manual:` prefixes); borrowed/ambient sources are deliberately **not**
  "explicit" for Hermes' own configured-ness logic.
- `env:<VAR>`-sourced rows **persist after the referenced env var disappears**
  (ordinary `load_pool()` keeps them; only the runtime explicit-configuredness
  check re-tests the env live). A static reader sees the row without being
  able to re-check the var without evaluating the environment — a standing
  false-positive source for any stronger-than-evidence claim.
- Cooldown/health state on rows: `last_status` (`ok|exhausted|dead`),
  `last_status_at`, `last_error_*`, `last_error_reset_at`. **These are
  mutated by Hermes' own runtime — a static reader must treat them as
  descriptive, never as Argus-owned verdicts.**
- Logout clears both sections (`clear_provider_auth` iterates
  `("providers", "credential_pool")`), so logout is the clean exit path.
  Residual stale evidence nevertheless arises **without** any manual edit —
  `env:<VAR>`-sourced pool rows persist after their env var disappears (kept
  by ordinary `load_pool()`; see the note below) — and manual file edits are
  by definition unmediated. `logged_in` is never claimable from static data.
- An unparsable/expired-claim-free JWT reads as **not expiring**
  (`_codex_access_token_is_expiring`: no `exp` claim → `False`). Confirms the
  contract's warning: static data cannot claim health, only evidence.

## `/api/providers/oauth` seam

- **Supported tag**: present, `GET /api/providers/oauth`
  (`hermes_cli/web_routers/oauth.py`), plus token-protected
  `DELETE /{provider_id}`, `POST /{provider_id}/start|submit`,
  `GET /{provider_id}/poll/{session_id}`, `DELETE /sessions/{id}`.
- **Provider-universe construction**: curated `_OAUTH_PROVIDER_CATALOG` first,
  then `provider_catalog()` entries with `tab == "accounts"` appended. The
  catalog is built **solely from the static `CANONICAL_PROVIDERS` list**: the
  plugin auto-extension in `models_catalog_static.py` skips plugin entries
  whose `auth_type` is in the literal skip-set `{oauth_device_code,
  oauth_external, external_process, aws_sdk, copilot, vertex}` ("non-api-key
  flows need bespoke picker UX"). One `_ACCOUNTS_AUTH_TYPES` member is **not**
  in that set: a plugin typed `oauth_minimax` passes the filter and would
  reach the seam. Net effect [source-verified at the tag]: **plugin-added
  account providers do not reach the seam, with that single typed exception** —
  the universe is otherwise bounded by the curated list plus static canonical
  account-type entries; the `oauth.py` docstring claiming plugins "appear
  automatically" is inaccurate.
- **Status dispatch**: hand-written per-provider cards (`nous`,
  `openai-codex`, `qwen-oauth`, `minimax-oauth`, `xai-oauth`) wrapping
  `get_*_auth_status` helpers; everything else (plugin entries) falls through
  to the slug-driven `get_auth_status(provider_id)` generic dispatcher, then
  `auth_type`-keyed fallbacks (`api_key`, `external_process`, `aws_sdk`) [source].
- **Access/auth requirements**: `/api/providers/oauth` is **not** in
  `PUBLIC_API_PATHS`. Two regimes:
  - loopback bind (`auth_required == False`): `X-Hermes-Session-Token`
    (per-process token, `HERMES_DASHBOARD_SESSION_TOKEN` or random at start)
    required — probe returned **401 without it** [empirical];
  - public bind (`auth_required == True`, production: `hermes serve` bound to
    a non-loopback (Tailscale) host): `gated_auth_middleware` accepts **only** dashboard
    cookie sessions (with IdP-backed refresh), an RFC 8252 native-app bearer
    (provider-minted token), or the token-auth seam for **routes explicitly
    registered via `register_token_route()` — and nothing is registered at the
    tag** [source]. The session-token header path is skipped entirely in
    gated mode. `--insecure`/`allow_public` is ignored upstream (June 2026
    hardening). **A headless local Argus caller therefore has no supported
    authentication path to this endpoint on a production-style public-bind
    deployment**; borrowing `HERMES_DASHBOARD_SESSION_TOKEN` from `.env`
    would both materialize a credential in Argus and still be ignored by the
    gate.
- **Profile behavior**: `?profile=` query param; `scoped_to_thread` wraps the
  handler in `_profile_scope(profile)`; profile auth store shadows the global
  root per provider (profile pool wins when it has any entries, else global
  fallback). Recorded as MP-relevant only — no profile implementation here.
- **Response fields**: `{id, name, flow, cli_command, docs_url,
  disconnect_hint, disconnect_command, disconnectable, status{logged_in,
  source, source_label, token_preview, expires_at, has_refresh_token,
  last_refresh?}}`. `token_preview` carries the **last 6 characters of the
  real token** for nous/codex/xai/qwen and anthropic/claude-code — partial
  secret material that a monitor must not retain, log, or emit.

### Side-effect analysis

#### Source audit (tag)

- `nous` → `get_nous_auth_status_local`: documented and implemented
  **refresh-free local snapshot** — "NEVER calls `resolve_nous_runtime_credentials()`
  (no refresh POST / single-use token spent)" [source].
- `minimax-oauth` → local store read + expiry parse, no network [source].
- `anthropic`, `claude-code`, `copilot-acp` → local file/env evidence;
  `_external_process_auth_evidence` is explicitly "deliberately subprocess-free"
  [source].
- `qwen-oauth` → `get_qwen_auth_status` calls
  `resolve_qwen_runtime_credentials(refresh_if_expiring=True)` — **performs
  refresh validation: network call + write to the Qwen CLI auth file** whenever
  the token is expiring [source].
- `openai-codex` / `xai-oauth` → `_pool_first_oauth_status`:
  - pool present with a non-expiring token → local return (no effects);
  - pool token expiring → `CredentialPool.select()` treats single-use-token
    providers (`openai-codex`, `xai-oauth`) as *pending refresh* and calls
    `_refresh_entry` → **OAuth network refresh + auth-store write-back**;
  - pool miss → `resolve_codex_runtime_credentials()` (default
    `refresh_if_expiring=True`) → **refresh + `_save_codex_tokens(...,
    write_through=True)`**; on persisted quota cooldown it may additionally
    run a live quota-restored probe (`_probe_codex_quota_restored`, network,
    5-min throttled) [source].
- Catalog construction imports `hermes_cli.provider_catalog` (plugin
  metadata) — plugin *loading* for catalog entries; status for plugin entries
  goes through `get_auth_status` (registry/env/local evidence; subprocess-free
  at tag) [source].

#### Isolated empirical probe [empirical]

Throwaway `HERMES_HOME`, synthetic credentials only, production venv (main
code, labeled as such), FastAPI TestClient, deny-by-construction networking
(dead local proxy). Script in Appendix B.

1. **Pool-only Codex is visible**: non-expiring pool row → `200`,
   `openai-codex` card `logged_in: true`, `source: "pool:probe"` — the seam
   solves the exact gap Argus misses.
2. **Steady state is clean**: three consecutive GETs → `auth.json` byte-identical
   (sha256), 0.03 s total.
3. **Unauthenticated GET → 401** (loopback regime).
4. **Expired tokens → demonstrated side effects**: one GET with expired
   synthetic Codex tokens (network denied by construction):
   - the handler attempted the OAuth refresh (error surfaced:
     `[Errno 111] Connection refused`);
   - **`auth.json` was persistently rewritten**: the pool row gained
     `last_status: "exhausted"` + `last_status_at` (a durable cooldown the
     runtime honors), and store `updated_at` changed (field-level diff in
     Appendix B). A monitoring poller calling this endpoint during a provider
     incident would actively freeze Hermes' own credentials.

#### Unknowns

- Exact upstream behavior when the refresh *succeeds* during a status GET
  (write shape, rotation cadence) — intentionally not probed against real
  OpenAI; the failed-refresh write is sufficient to disqualify polling.
- Whether `qwen` refresh-validation writes on every expiring GET or only on
  successful refresh — bounded check not performed (qwen absent in
  production); classified "side-effectful by design" from source.
- Plugin-provider status helpers under `get_auth_status` for arbitrary future
  plugins (subprocess-free at tag, but not contractually guaranteed).

## Candidate comparison

| Candidate | Completeness | Side-effect risk | Secret exposure | Plugin/future provider coverage | Profile fit | Maintenance cost | Verdict |
|---|---|---|---|---|---|---|---|
| current hard-coded static list | misses nested singleton + all pool state (demonstrated) | none | none (field names only) | none — new providers need Argus edits | none | low but already wrong | reject as-is |
| generic static auth.json structure | full for `providers` + `credential_pool` (the persisted auth-store universe); external CLI files opt-in; ambient cloud chains (Vertex ADC, Bedrock IAM, Azure Foundry Entra ID, Copilot keychain) remain misses | none (read-only, no Hermes execution) | none if only presence/metadata is read (never values, never `secret_fingerprint`) | pool/`providers` sections are generic and store-keyed; account-type **plugins** surface only if they write store rows | reads the same store the seam scopes (MP-compatible later) | low — structural rules, not a provider roster | **recommended** |
| `GET /api/providers/oauth` | best runtime truth (pool-only codex `logged_in`) | **demonstrated persistent writes + network refresh on expiring/failed paths; qwen refresh-validates by design** | `token_preview` = partial real token in every response | no for new account-type plugins, single typed exception `oauth_minimax` (universe otherwise bounded by the static catalog) | yes (`?profile=`) | medium — HTTP client, auth, schema drift | reject for polling now; record as future upstream-gated enrichment (OA2 gate below) |
| `hermes auth list` | pool + registry universe | `load_pool()` per provider seeds/heals the store (writes); CLI cold start | none in output (labels/ids only) | pool-driven | no profile flag at tag | high — human-readable text, no JSON schema | reject |
| `GET /api/credentials/pool` | pool only | `load_pool()` "may hit the network synchronously (Copilot token exchange)"; borrowed-source hydration may spawn `gh` | redacted views only | pool only | no profile param | medium | reject — strictly worse than reading the same pool statically |
| importing Hermes auth/provider internals | best | runtime coupling; forbidden by architecture invariant (C1a dropped) | n/a | n/a | n/a | n/a | forbidden — do not revive |

## Proposed OA1 semantics

- **What static discovery may claim**: `persisted credential evidence present`
  for an identity — **never** `healthy`, never `logged_in`, and — for pool
  rows of borrowed/ambient origin — not even `configured` (rows persist after
  their source disappears; only "evidence exists on disk" is provable). The
  distinction `evidence present` vs Hermes' `logged_in` vs independent health
  is mandatory in any OA1 output schema.
- **Structural rules** (evaluate, do not widen):
  1. `providers.<id>` object containing a non-empty credential structure —
     flat `access_token`/`refresh_token` **or** a `tokens` sub-object with a
     non-empty `access_token`/`refresh_token` → identity `<id>`. Presence
     alone does not classify the auth kind: a flat block on an API-key-style
     provider is key evidence, not OAuth evidence.
  2. `credential_pool.<id>[]` rows with persisted `auth_type == "oauth"` →
     identity `<id>`. This is **unvalidated persisted metadata** (the loader
     accepts the stored value unchecked), i.e. evidence of what the store
     claims, not a verified account-auth type; a mislabeled row remains a
     possible false positive that OA1 output should surface as such.
     Bounded legacy fallback: rows with **no persisted `auth_type`** and a
     non-empty `refresh_token` → identity `<id>` flagged `evidence: weak`
     (possible false positive on stale/manual/plugin rows). The runtime-only
     `anthropic sk-ant-oat*` re-typing is NOT replicated (it requires reading
     the secret value).
  3. `auth_type == "api_key"` pool rows → `persisted credential evidence`
     with `auth_type: api_key` (presently invisible to Argus too). Stale
     `env:*` rows survive their env var — no validity or configuredness claim
     may be attached. Whether these surface as `oauth:*` entities or a
     distinct class is an OA1 schema decision — the existing `oauth` entity
     name is semantically imperfect; recorded as schema debt, no rename
     authorized by OA0.
  4. provider ids come from the store keys themselves (including aliases such
     as pool key `xai` vs provider id `xai-oauth`) — no new hard-coded roster.
- **Secret fields explicitly discarded**: `access_token`, `refresh_token`,
  `agent_key`, `secret_fingerprint`, credential `id`/`label`,
  `expires_at`/expiry-class timestamps (rotation noise, lesson 2026-09-07).
  Safe metadata: key/section names, `auth_type`, `source` class,
  row count, boolean has-refresh, presence of cooldown markers
  (`last_status` value is runtime-owned; at most surfaced as `runtime_cooldown: true`).
- **Known misses** (documented, acceptable): credentials held only in external
  CLI stores/keychains or ambient cloud chains (Codex CLI `~/.codex/auth.json`
  before adoption, Copilot OS keychain, qwen CLI file, Vertex ADC/OAuth2,
  Bedrock IAM chain, Azure Foundry Entra ID) remain invisible unless
  OA1 adds opt-in file readers; that extension needs its own evidence (the
  files contain secret material at rest) and is not part of the minimum rule.
  Account-auth **plugins** that never write `providers`/`credential_pool`
  rows are likewise invisible.

## OA2 gate

- **Safe enough for shadow?** **No** — on the current supported tag and
  production deployment shape:
  1. no headless authentication path exists on public-bind (gated) deployments
     (`register_token_route()` is called by nothing at tag; cookie sessions
     require interactive IdP login);
  2. polling demonstrably writes durable cooldown state into the credential
     store on the failed-refresh path and refreshes tokens on the happy path
     (qwen unconditionally when expiring) — a monitor must not be able to
     mutate what it watches.
- **Exact whitelisted fields** (if the gate is ever reopened upstream): `id`,
  `status.logged_in`, `status.source` — never `token_preview`, never
  `expires_at`. `disconnect_command`/`cli_command` must not be executed by Argus.
- **Polling/usage constraints** (future, only after an upstream change):
  a registered token route with a machine credential provider, documented
  refresh-free status semantics mirroring `get_nous_auth_status_local` for all
  providers, and an explicit upstream no-write guarantee for GET — each is an
  upstream (Hermes-owned) decision, not an Argus patch.
- **Stop conditions**: any requirement to hold dashboard cookies/session
  tokens, to spawn `hermes` per poll, or to accept `token_preview` into Argus
  state → STOP.

## Decision

**STATIC ONLY**

Generic static structure of `auth.json` (`providers` + `credential_pool`
sections) covers the **persisted auth-store universe** — which is exactly the
demonstrated product need: the false negative is a Codex account whose
credentials *are* in the store (nested singleton + pool) and become visible.
It does so with zero execution, zero side effects, zero secret exposure, and
no new dependency. The Hermes-owned seam is architecturally attractive (it
even saw pool-only Codex in the probe) but is disqualified for Argus polling
today by demonstrated write side effects, the absent headless auth path, and
a plugin-hostile universe bounded by a static catalog; all three blockers are
upstream-owned. Credentials held only in external CLI files or ambient cloud
chains (Codex CLI file, Vertex ADC, Bedrock IAM, Azure Foundry Entra ID,
Copilot keychain) remain
documented known misses — they are not the demonstrated gap, and extending to
them would be a separate, separately-evidenced decision. Per the contract this
is not a runtime-bridge proposal and no OA1 code is submitted here.

## Out-of-scope findings (recorded, not acted on)

1. Production runs an editable Hermes **main** (`d177b119`) 2096 commits ahead
   of the supported release tag (`345cd2b0`). Deployment/version-pin hygiene is
   a maintainer question outside OA0.
2. Production pool keys include aliased/duplicated ids (`cline`, `cline-pass`,
   `clinepass`; `xai` vs `xai-oauth`) — worth normalizing in R2c's registry
   wording, not here.
3. `get_qwen_auth_status` refresh-validating inside a read-only dashboard card
   is an upstream design smell (surprising network + external-file write from
   a GET) — record for any future upstream conversation.
4. `auth.json` store `version` was downgraded 2 → 1 by the probe's write path
   (`AUTH_STORE_VERSION` at main). Cosmetic, upstream-only observation.

## Production actions

No production mutation performed. Production access was read-only
(structural JSON introspection of `auth.json` and Argus state files, key names
only; no values printed, copied, or stored; no GET against the production
seam — deliberately, because it can mutate). All empirical work ran in
throwaway homes with synthetic credentials and was deleted afterwards.

## Recommendation for next contract

`OA1 — generic structural auth discovery` in
`scripts/integration-discover.py` per the rules above: extend layer 4 to
read `providers.<id>` (flat and nested `tokens`) plus `credential_pool.<id>[]`
metadata, emitting conservative `credential evidence present` entities without
any secret-derived fields. R1c (Authorization-header argv debt) stays next per
the roadmap order chosen by the maintainer; OA1 does not unblock or depend on it.

---

## Appendix A — Probe A: Argus gap reproduction (synthetic, local)

Two variants against `scripts/integration-discover.py` with a synthetic
`HERMES_DIR` (no Hermes execution; fixture built locally):

```python
# fixture builder
import base64, json, time
def b64(o): return base64.urlsafe_b64encode(json.dumps(o).encode()).rstrip(b"=").decode()
future = int(time.time()) + 3600
def fixture(singleton: bool, pool: bool, nous: bool) -> dict:
    auth = {"version": 2, "providers": {}, "credential_pool": {}}
    if nous:  # positive control: the flat shape current Argus DOES detect
        auth["providers"]["nous"] = {"access_token": "nous-flat-token",
                                     "refresh_token": "r",
                                     "expires_at": "2099-01-01T00:00:00Z"}
    if singleton:
        auth["providers"]["openai-codex"] = {
            "tokens": {"access_token": "hdr." + b64({"exp": future}) + ".sig",
                       "refresh_token": "rt"},
            "last_refresh": "2026-09-18T00:00:00Z", "auth_mode": "chatgpt"}
    if pool:
        auth["credential_pool"]["openai-codex"] = [{
            "id": "abc123", "label": "probe", "auth_type": "oauth", "priority": 0,
            "source": "device_code",
            "access_token": "hdr." + b64({"exp": future}) + ".sig",
            "refresh_token": "rt"}]
    return auth
# run per variant: HERMES_DIR=$TMP/home python3 scripts/integration-discover.py
```

Observed (asserted in the run):

- **Variant A1 — `fixture(singleton=True, pool=True, nous=True)`** (nested
  singleton AND pool row present, flat nous as positive control): snapshot
  entities == `["oauth:nous"]`; `oauth:openai-codex` absent; discover exit 2
  (events present). The control proves the harness sees a flat block while
  both Codex shapes stay invisible.
- **Variant A2 — `fixture(singleton=False, pool=True, nous=False)`** (pool row
  only): snapshot oauth entities == `[]`, discover exit 0 (silent) — a
  pool-only working Codex account produces *no* events at all, isolating the
  pool-only miss.

## Appendix B — Probe B: isolated seam probe (synthetic, throwaway home)

### Script (full, with assertions)

Runs on the Hermes venv (`main@prod` code — labeled; tag path source-verified
separately and independently reproduced by the reviewer at the exact tag, see
provenance below), `HERMES_HOME` pointed at a throwaway dir,
`HERMES_DASHBOARD_SESSION_TOKEN` pinned for the session header,
`HTTPS_PROXY/HTTP_PROXY=http://127.0.0.1:9` and empty `NO_PROXY`
(deny-by-construction), FastAPI TestClient.

```python
import base64, hashlib, json, os, sys, time
tmp = sys.argv[1]
def b64(o): return base64.urlsafe_b64encode(json.dumps(o).encode()).rstrip(b"=").decode()
def jwt(exp): return "hdr." + b64({"alg": "none", "exp": exp}) + ".sig"
now = int(time.time())
home = os.path.join(tmp, "home"); os.makedirs(home, exist_ok=True)
p = os.path.join(home, "auth.json")
sha = lambda: hashlib.sha256(open(p, "rb").read()).hexdigest()
def write_auth(singleton, pool, exp):
    auth = {"version": 2, "providers": {}, "credential_pool": {}}
    if singleton:
        auth["providers"]["openai-codex"] = {
            "tokens": {"access_token": jwt(exp), "refresh_token": "rt"},
            "last_refresh": "2026-09-18T00:00:00Z", "auth_mode": "chatgpt"}
    if pool:
        auth["credential_pool"]["openai-codex"] = [{
            "id": "abc123", "label": "probe", "auth_type": "oauth", "priority": 0,
            "source": "device_code", "access_token": jwt(exp), "refresh_token": "rt"}]
    open(p, "w").write(json.dumps(auth))
os.environ["HERMES_HOME"] = home
os.environ["HERMES_DASHBOARD_SESSION_TOKEN"] = "oa0-probe-token"
os.environ["HTTPS_PROXY"] = "http://127.0.0.1:9"; os.environ["HTTP_PROXY"] = "http://127.0.0.1:9"
os.environ["NO_PROXY"] = ""; os.environ["no_proxy"] = ""
from fastapi.testclient import TestClient
from hermes_cli.web_server import app, _SESSION_TOKEN
c = TestClient(app)
H = {"X-Hermes-Session-Token": "oa0-probe-token"}
assert _SESSION_TOKEN == "oa0-probe-token"

# case 1: pool-only codex, non-expiring — visibility + steady-state + 401
write_auth(singleton=False, pool=True, exp=now + 3600)
h0 = sha()
r = c.get("/api/providers/oauth", headers=H)
assert r.status_code == 200
codex = next(x for x in r.json()["providers"] if x["id"] == "openai-codex")
assert codex["status"]["logged_in"] is True
assert codex["status"]["source"] == "pool:probe"
h1 = sha()
for _ in range(2):
    assert c.get("/api/providers/oauth", headers=H).status_code == 200
assert sha() == h0 == h1, "steady-state GETs must not mutate auth.json"
assert c.get("/api/providers/oauth").status_code == 401, "unauthenticated GET must 401"

# case 2: expired singleton+pool — refresh attempt + persistent write
write_auth(singleton=True, pool=True, exp=now - 3600)
h2 = sha()
r = c.get("/api/providers/oauth", headers=H)
assert r.status_code == 200
codex = next(x for x in r.json()["providers"] if x["id"] == "openai-codex")
assert codex["status"]["logged_in"] is False
assert "Connection refused" in (codex["status"].get("error") or ""), \
    "refresh attempt must have hit the deny-by-construction proxy"
after = json.load(open(p))
row = after["credential_pool"]["openai-codex"][0]
assert row.get("last_status") == "exhausted", "failed-refresh path persists cooldown state"
assert after.get("updated_at"), "store metadata rewritten by a GET"
```

### Observed results (all assertions passed)

- **Case 1**: `200`; codex card `logged_in: true`, `source: "pool:probe"` —
  the seam sees pool-only Codex, the exact case Argus misses; `auth.json`
  byte-identical (sha256) across three GETs (0.03 s); unauthenticated GET
  → `401` (loopback regime).
- **Case 2**: `200` in 0.20 s; codex `logged_in: false` with the refresh
  attempt surfacing `[Errno 111] Connection refused`; field-level diff showed
  the pool row **persistently rewritten** — `last_status: "exhausted"` +
  `last_status_at` (a durable cooldown the runtime honors), `updated_at`
  added (and store `version` rewritten). A monitoring poller calling this
  endpoint during a provider incident would actively freeze Hermes' own
  credentials.

### Probe provenance

- Side-effect code paths (status helper dispatch, pool-first resolve, refresh
  + `write_through` save, cooldown persistence) were **source-verified at the
  exact supported tag** `345cd2b0` (authority for this decision).
- The empirical run above was **captured on `main@prod`** (`d177b119`,
  editable production venv) because the tag is not the installed tree; per the
  baselines section, tag→main drift in `auth.py`/`agent/credential_pool.py` is
  substantive, so main-run evidence alone was not treated as tag evidence.
- The reviewer (Pytna) **independently built and ran a minimal throwaway
  harness at the exact tag** and reproduced every claimed property: pool-only
  Codex → `200` with `source pool:probe`; three GETs → `200` with unchanged
  `auth.json`; missing session token → `401`; expired-refresh path →
  persisted `last_status=exhausted` + `updated_at`. The empirical claims of
  this report therefore have exact-tag provenance via independent
  reproduction.
