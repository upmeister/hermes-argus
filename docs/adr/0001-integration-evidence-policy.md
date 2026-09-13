# ADR 0001: Integration evidence and side-effect policy

- **Status:** Accepted
- **Date:** 2026-09-13
- **Deciders:** Vlad (owner), Питна (review/maintainer)
- **Scope:** Argus verification policy — what a check proves, how results are
  classified, and which side effects checks may cause. Implementation mapping
  starts with the report schema v2 envelope (D0a) and per-check claims (D0b).
- **Non-goals:** the list of Hermes runtime imports/capabilities usable by a
  future runtime bridge is deliberately **not** decided here. That is ADR 0002
  (B1b), gated on the C0 spike evidence. This ADR also does not introduce a
  generic adapter/plugin framework (D1).

## Context

The current `ok/fail` result conflates several different questions:

- is the integration configured?
- can Argus reach it?
- were credentials accepted?
- did the specific capability work?
- is this integration actually selected by current Hermes runtime state?

That conflation makes false greens easy. Observed examples:

- an anonymous endpoint can prove transport but not authentication;
- MCP `tools/list` can succeed for an OAuth-configured server without any token;
- a `429` proves that an HTTP service replied, but not that credentials are valid;
- an API root `404` proves a round trip but not the intended semantic route;
- a present key proves configuration, not provider health;
- a stale or crashed engine run must never look like a recovery.

Hermes owns runtime truth; Argus owns verification policy. This ADR fixes the
vocabulary and the rules of that policy so that reports, hysteresis, alerts and
UI cannot silently inflate evidence.

## Decision

### 1. Claims are independent evidence dimensions

Every structured check may report these claims:

```text
presence        — configuration/credential metadata exists
transport       — a connection / HTTP round trip to the target is achievable
authenticated   — the endpoint contract actually accepted the credential
semantic        — the expected response shape/capability was confirmed
active          — a real selected operation was performed (usually deep/manual)
```

The claims are **not** a strict ladder. A check may prove `semantic` without
`authenticated` (public endpoints), and `active` is orthogonal to health.

### 2. Claim states

```text
pass           — collected evidence positively proves the claim under the check contract
fail           — the evidence positively disproves the claim
unknown        — evidence was collected, but it cannot prove either outcome
not_tested     — this run intentionally did not attempt the claim
not_applicable — the claim makes no sense for this target
```

`unknown` and `not_tested` are deliberately different. A public MCP
`tools/list` while OAuth is configured is `authenticated: unknown`; a regular
check that intentionally skips authentication is `authenticated: not_tested`.
Authentication on an intentionally unauthenticated local service is
`authenticated: not_applicable` — never an implicit `pass`.

### 3. Health verdict is separate from evidence

The canonical verdict enum is:

```text
healthy
failed
unknown
unconfigured
skipped
```

Semantics:

- `healthy` — every claim required by this check's contract is `pass` or
  explicitly `not_applicable`;
- `failed` — at least one required claim is `fail`, **or** the failure matrix
  (Decision 6) assigns `failed` to the observed evidence class (transport
  error, credential rejection, rate limiting, service error, wrong route,
  schema mismatch);
- `unknown` — the target is configured, but required evidence is unavailable or
  inconclusive;
- `unconfigured` — an optional target is absent;
- `skipped` — the target exists, but policy intentionally did not execute this
  check in the current tier.

A check cannot become `healthy` merely because *some* claim passed.
`unknown` is never a recovery.

### 4. The check contract declares what it proves

A check definition declares, at minimum, which claims are required for
`healthy`, what capability the semantic claim covers, and the full request/
response contract plus its side-effect budget — mirroring the AGENTS.md
invariant that authenticated semantic checks declare their method, expected
status, content type/schema, and safe side-effect boundary:

```yaml
required_claims: [presence, authenticated, semantic]
semantic_capability: queue_status
method: GET
expected_status: 200
expected_content_type: application/json
expected_schema: honcho_queue_status_v1
effects_budget:
  network: metadata
  process_spawn: false
  token_refresh: none
  quota: metadata
  llm: false
  write: none
  code_execution: none
```

In the current engine this contract may live in code next to the primitive; the
invariant is that it exists and is testable. No generic adapter framework is
required or introduced by this decision.

### 5. Structured reason codes

Every check result carries a machine-readable `reason_code`, separate from the
human-readable `detail`. Initial codes:

```text
ok                        # healthy, nothing else to say
optional_not_configured   # optional target absent
missing_required_config   # a required configuration entry is missing/empty
credential_missing
credential_rejected
transport_timeout
transport_error
rate_limited
server_error
wrong_route
unexpected_status
wrong_content_type
invalid_json
schema_mismatch
policy_blocked
compatibility_degraded
unsupported_probe
probe_crashed
invalid_runtime_config
unclassified_failure      # legacy projection: failed without a classified cause
```

Provider-specific strings stay in `detail` only after sanitization, and only
when no stable code suffices. The legacy projection (report schema v2, D0a)
uses `unclassified_failure` for `failed` results until D0b adapters classify
their causes precisely.

### 6. HTTP evidence matrix

The status code itself is not the verdict. Claim states distinguish positive
evidence (`fail`) from inconclusive evidence (`unknown`): a response that never
delivered semantic content cannot positively disprove the semantic claim.

| Observation | transport | authenticated | semantic | Default verdict note |
|---|---|---|---|---|
| timeout / connection error | fail | not_tested | not_tested | failed (transport) |
| 401 with configured credential | pass | fail | not_tested | failed; the credential was positively rejected; fail fast |
| 403 with configured credential | pass | unknown | not_tested | failed; a 403 does not by itself prove the credential invalid (it may be a permission denial) — `authenticated: fail` only when the check contract states that a valid credential cannot receive 403 on this route |
| 404 on a required semantic route | pass | unknown | fail | failed; positive evidence the expected capability/route is absent; only an explicit check contract may treat 404 differently |
| 429 | pass | unknown | unknown | failed (degradation); no semantic content was received, so neither authentication nor semantic health is proven or disproven; never proof of valid auth; fail fast by default |
| 5xx | pass | unknown | unknown | failed (service error); no semantic content was received; bounded retry allowed |
| 2xx wrong content type | pass | contract-dependent | fail | failed; positive schema evidence |
| 2xx invalid JSON/schema | pass | contract-dependent | fail | failed; positive schema evidence |
| 3xx | pass | unknown | not_tested | not semantic success unless the check contract explicitly accepts redirect behavior |

### 6a. Failure classes without HTTP evidence

Not every failure arrives as an HTTP response. These classes are fixed as:

```text
missing_required_config / credential_missing
  presence: fail; transport/authenticated/semantic: not_tested
  -> verdict failed (no probe executed; nothing else is proven)

probe_crashed (the check itself crashed or timed out)
  all claims: unknown
  -> verdict unknown; failure counter preserved; never recovery

compatibility_degraded (discovery or a runtime bridge is unavailable)
  affected checks: unknown with reason_code compatibility_degraded
  -> verdict unknown; failure counter preserved; never recovery
```

A crashed or degraded check must degrade to `unknown`, not to `failed` and not
to `healthy`: "we could not observe" is neither "it is broken" nor "it recovered".

Authentication may be marked `pass` from a successful semantic response only
when the route's contract guarantees that anonymous access cannot produce that
success response.

### 7. Retry policy belongs to the failure class

Default:

- 401/403: fail fast;
- 404 wrong route: fail fast;
- 429: fail fast by default (a specialized check may specify bounded backoff,
  but it still may not turn 429 into auth success);
- timeout / connection errors / 5xx: bounded retry allowed;
- invalid body/schema: fail fast unless the backend contract explicitly
  documents eventual consistency.

### 8. Side-effect budgets are explicit

Every executed check declares its effect contract across these dimensions:

```text
network          # none | metadata | live_service | generation | arbitrary
process_spawn    # boolean
token_refresh    # none | possible | observed
quota            # none | metadata | generation | unknown
llm              # boolean
write            # none | local_ephemeral | local_persistent | remote
code_execution   # none | explicit_configured | plugin_discovery | arbitrary
```

Notes:

- For the regular tier, `token_refresh: possible` is already too much — a probe
  that *can* refresh a token does not satisfy the regular contract merely
  because a particular run happened not to refresh it.
- `code_execution` exists as a separate dimension because Hermes provider
  discovery can import bundled/user/pip plugin Python code; that is materially
  different from reading a declarative file.
- If a transport or provider has no safe authenticated read operation, only the
  honestly proven lower-level claims are published.

### 9. Tiers are policy, not implementation names

- **Regular** — scheduled automatically. Default budget:
  `network <= metadata`, `process_spawn` only when bounded and declared,
  `token_refresh = none`, `quota <= metadata`, `llm = false`, `write = none`,
  `code_execution = none`. No automatic OAuth refresh, generation, memory
  write or remote write.

  A regular check may run `explicit_configured` code only when its contract
  explicitly declares and bounds it: a fixed allowlisted entrypoint (never
  arbitrary or plugin-supplied code), a bounded timeout, an output-size cap,
  an explicit environment allowlist that does not inherit secrets beyond the
  declared set, no network beyond the declared budget, and no writes. Plugin
  discovery — importing bundled/user/pip plugin Python code — is never part of
  the regular budget: it requires a live/deep tier assignment and explicit
  maintainer acceptance backed by C0 evidence.

- **Live** — explicit or less frequent real connectivity checks. May permit more
  network/process activity, but still no model generation or remote writes by
  default. Token-refresh-capable checks must be explicitly declared.

- **Deep** — manual/explicit. May perform provider-native generation or other
  expensive verification where that is the only meaningful semantic evidence.
  Paid generation requires explicit policy. Deep checks still never perform
  remote writes or token refresh unless the specific check contract explicitly
  declares them and the maintainer has approved that contract; any observed
  token refresh is recorded in the check's effect contract
  (`token_refresh: observed`). Deep checks never run from regular schedules.

### 10. Redaction

Reports, evidence containers, logs and alerts must not contain:

- credential values or Authorization/header values;
- raw request/response bodies or headers;
- secret-bearing URLs (userinfo, secret query parameters);
- full environment mappings or secret-bearing argv;
- raw exception strings/reprs from credential or provider code;
- private response payloads.

Evidence is sanitized metadata only: protocol, HTTP status, content type,
schema identifier, tool counts, exit classes, and similar bounded facts.

## Rules that follow

1. A `2xx` status, key presence, an anonymous response, or a `429` — none of
   them, alone or together, prove `authenticated` or `semantic` health.
2. `active` is informational by default and does not make a check
   `healthy`/`failed` without a separate explicit contract (for example a
   "verify the currently selected route" check).
3. `unknown`, `unconfigured` and `skipped` verdicts never reset a failure
   counter and never emit recovery. Only `healthy` does.
4. The legacy projection `unknown → skipped` is allowed only for old consumers
   during the schema-v2 migration; canonical v2 retains `unknown`.
5. A green UI icon must not imply `authenticated` unless the check contract
   proves it.

## Rejected alternatives

1. **One scalar evidence level** (`presence < transport < authenticated <
   semantic < active`). The dimensions are not universally ordered; an
   integration may be semantically usable without auth, and active selection is
   orthogonal to health.
2. **Any 2xx/3xx = healthy.** False-green prone.
3. **`429` = valid key.** Rate limiting does not reliably prove authentication.
4. **Endpoint-template-only universal checker.** Provider/backend semantics
   differ materially; integration-specific routing is allowed only through
   trusted adapters/resolvers (the Honcho workspace queue route is the first
   concrete case).
5. **Arbitrary plugin-provided probe code.** Probe behavior must be declared and
   bounded, not supplied by probed plugins. Plugin-code execution inside
   regular scheduled checks is likewise rejected: plugin discovery imports
   executable Python and stays out of the regular budget (Decision 9).
6. **Probe output text as the contract.** Structured claims and reason codes are
   the contract; human text is presentation only.

## Consequences

- Tests can assert exactly what an observation proves (the HTTP matrix above is
  directly testable).
- The UI can distinguish "reachable but auth unknown" from green.
- Hysteresis operates on the verdict, not on incidental details; "we stopped
  knowing" is no longer recoverable-looking.
- Future checks enrich claims without changing the meaning of `healthy`.

## Implementation mapping

- **D0a** introduces the report schema v2 envelope: `schema: 2`, `source`,
  nested `summary`, `inventory`, `checks[]`; per-check canonical `verdict`,
  `reason_code`, `legacy_status`, and empty `claims`/`effects`/`evidence`
  containers; dual-read in the wrapper and `/integrations`; conservative
  hysteresis on the verdict. Existing producers keep their semantics:
  `ok→healthy`, `fail→failed`, `unconfigured→unconfigured`, `skipped→skipped`.
- **D0b** enriches proven checks (Honcho first, then safe Telegram, TCP/local
  HTTP) with real claims/effects per the rules above.
- The Hermes runtime bridge import list is out of scope until C0 evidence
  exists (ADR 0002 / B1b).
