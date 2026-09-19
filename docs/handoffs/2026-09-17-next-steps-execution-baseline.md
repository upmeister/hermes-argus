# 2026-09-17 next-steps execution baseline

Status: **ACTIVE EXECUTION BASELINE — UPDATED 2026-09-19**

This document translates the stabilization roadmap into bounded repository
work. Agents may perform only the named task currently assigned by the
maintainer.

## Architecture invariant

```text
Hermes owns runtime truth.
Argus observes externally, verifies independently where useful, and makes failures loud.
```

Do not introduce a Hermes runtime-import bridge to improve discovery.

## Exact current baseline

```text
Argus main = 12739f8c4fbd597606653281a6c4b1898a2b00a4

R1a / PR #29 = DONE
R1b / PR #31 = DONE
OA0 / PR #33 = DONE / STATIC ONLY
OA1 / PR #35 = DONE / MERGED
OA1b / PR #39 = DONE / MERGED (reviewed head a58075f7, PASS-TO-MERGE)
OA-close = DONE — OA PHASE COMPLETE
```

Supported Hermes authority:

```text
v2026.9.14 / v0.21.3
stable commit = 345cd2b057a452236de401d3534b8502a7465e8d
```

2026-09-20 warning-source watch:

```text
Hermes main = 00570550f37e9082676955d50f65c7d9ba846cc9 (+927 since 03c9fc89)
latest stable remains v2026.9.14
```

Upstream changed `hermes_cli/auth_codex.py` and `hermes_cli/web_routers/oauth.py`
(partial refresh-free improvement for nous listing), but `token_preview`,
refresh and persist paths remain and no stable release satisfies the reopen
conditions. OA2 is still closed.

## Current execution order

```text
R1c Authorization-header argv debt           NEXT (maintainer selects contract)
 -> R2a malformed YAML
 -> R2c bounded static compatibility
 -> R3 cleanup/stabilization

OA phase                                     COMPLETE
OA2 Hermes status shadow                     CLOSED / UPSTREAM-GATED
R2b gateway liveness                         DEFERRED
MP*                                          SEPARATE
```

## OA1 final maintainer gate

OA1 is accepted.

Verified:

- structural identity discovery no longer depends on `OAUTH_FLOWS`;
- nested Codex singleton and pool-only Codex are covered;
- arbitrary synthetic OAuth pool id is covered without production roster edit;
- explicit `api_key`, unknown auth type and malformed rows do not enter
  `oauth:*`;
- same-id singleton/pool evidence produces a stable entity;
- secret canaries are scanned across snapshot/report/stdout/stderr and health
  output;
- static auth evidence is `skipped`, not `healthy / logged in`;
- Copilot PAT-only remains `unconfigured`;
- no Hermes/network/refresh/write dependency was introduced;
- PR-head CI static checks and regression probes passed.

One non-blocking P3 documentation nit remains: `run_check()`'s docstring still
lists only `ok | fail | unconfigured` even though `skipped` is now a valid
return. Do not open an OA1 remediation only for this line; fix opportunistically
when that function is next touched.

## Current selected contract

None yet: the OA phase is complete and R1c (demonstrated non-Telegram
Authorization-header argv debt) is the next task. The maintainer selects the
task and its contract is authored/activated at that point.

## OA-close acceptance (executed 2026-09-20)

Executed on exact main `12739f8c4fbd597606653281a6c4b1898a2b00a4`:

1. exact merged main re-read — done;
2. focused OA1 fixtures and full regression suite — 109 pass / 0 fail;
3. secret-canary and false-green properties — confirmed (see
   `oa-close-account-auth-acceptance-contract.md` receipt);
4. OA2 reopen gate — CLOSED under latest stable v2026.9.14; fresh main watch
   recorded in the receipt;
5. authority docs updated to `OA PHASE COMPLETE -> R1c`.

## OA2 authority

Use:

```text
docs/handoffs/oa2-hermes-status-shadow-reopen-gate.md
```

OA2 requires a stable/tagged refresh-free, no-write/no-provider-network,
headless-authenticated, no-secret status seam before it may be reopened.

## Global non-goals

- runtime bridge revival;
- OA2 polling;
- auth validation/refresh;
- universal credential inventory;
- external CLI/keychain/cloud auth probing;
- schema rename;
- provider alias normalization;
- multi-profile implementation in OA-close;
- unrelated cleanup.

## Workflow

```text
one closeout pass
 -> exact-main evidence
 -> one focused review
 -> docs-only completion OR blocker
```

If closeout requires production code, stop to maintainer.

## Canonical contracts

Current:

- (none — R1c contract to be authored when the maintainer selects the task)

Completed:

- `oa-close-account-auth-acceptance-contract.md`
- `oa1b-oauth-evidence-rendering-contract.md`
- `oa1-static-account-auth-discovery-contract.md`
- `oa0-account-auth-discovery-research-contract.md`

Closed:

- `oa2-hermes-status-shadow-reopen-gate.md`

Queued:

- `r2a-malformed-yaml-contract.md`
- `r2c-static-discovery-compat-contract.md`

Deferred:

- `r2b-gateway-liveness-contract.md`

## OA1b production finding

Observed after deploy:

```text
⏸ oauth nous — пропущено
⏸ oauth openai-codex — пропущено
```

This is not an auth failure. It is a renderer bug: OAuth persisted evidence is
correctly canonical `skipped` because runtime health is unverified, but the
bot displays the generic skipped label without the evidence context.

Current contract:

```text
docs/handoffs/oa1b-oauth-evidence-rendering-contract.md
```

OA-close resumes only after OA1b passes.
