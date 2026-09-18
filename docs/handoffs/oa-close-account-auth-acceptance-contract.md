# OA-close contract — account-auth phase acceptance and handoff

Status: **NOW / READY — CLOSEOUT ONLY**

This is the final OA-phase acceptance/docs task. It is deliberately smaller
than OA1 and is **not** a second auth implementation project.

## Exact starting baseline

```text
Argus main = cfa6c535518e3d3ad9b78c20d442335f48e84fd6

OA0 / PR #33 = DONE / STATIC ONLY
OA1 / PR #35 = DONE / MERGED
OA2 = CLOSED / UPSTREAM-GATED

OA1 reviewed PR head = abb7ceecd805fe4c4ffc1f90248a562be88de051
OA1 CI run #61 = SUCCESS
```

The OA1 production blobs are byte-identical between reviewed PR head and merged
main for:

- `CHANGELOG.md`
- `scripts/integration-discover.py`
- `scripts/health-check-v2.py`
- `tests/probes.py`

Supported Hermes authority:

```text
v2026.9.14 / v0.21.3
stable commit = 345cd2b057a452236de401d3534b8502a7465e8d
```

Latest warning-source watch at contract activation:

```text
Hermes main = 03c9fc892f5cf3f2e02aa4a4888a30ae292d256d
latest stable = still v2026.9.14 / v0.21.3
```

The account-auth/OAuth router/provider-catalog/dashboard token-auth files
relevant to the OA2 reopen gate are unchanged since the previous
`1e4952dd...` watch. OA2 therefore remains closed.

## 1. Purpose

Close the OA phase with one exact-main acceptance receipt and make the next
selected task unambiguous.

Required final state:

```text
OA0 DONE
OA1 DONE
OA2 CLOSED / UPSTREAM-GATED
OA PHASE COMPLETE
NEXT = R1c
```

## 2. Acceptance questions

Against **exact merged main**, answer all of these:

1. Does nested
   `providers.openai-codex.tokens.{access_token,refresh_token}` produce
   `oauth:openai-codex`?
2. Does pool-only `credential_pool.openai-codex[]` with
   `auth_type=oauth` produce the same entity?
3. Does an arbitrary synthetic future OAuth pool provider work without a
   production roster edit?
4. Do explicit `auth_type=api_key`, unknown/malformed auth types and bare
   access-token rows stay outside `oauth:*`?
5. Does same-id singleton/pool storage movement keep entity content stable?
6. Do malformed auth structures fail safely without crashing discovery?
7. Can any secret canary appear in:
   snapshot, discover report, stdout/stderr, health report or health
   stdout/stderr?
8. Does a static account-auth entity remain non-green:
   `status=skipped`, canonical `verdict=skipped`,
   `summary.healthy == 0`, and no "logged in" claim?
9. Does Copilot PAT-only remain `unconfigured`?
10. Can the quick renderer ever say "всё в порядке" for a skipped-only static
    OAuth report?
11. Does the merged implementation still contain no Hermes import/call,
    provider-network call, token refresh or auth-store write in account-auth
    discovery?
12. Is OA2 still upstream-gated under the latest stable Hermes release?

## 3. Required evidence

Run against the exact closeout baseline:

- `python3 tests/probes.py`;
- repository static/syntax checks used by CI;
- `git diff --check` for any closeout doc changes;
- focused OA1 probes already present in the suite;
- explicit secret-canary result;
- explicit health non-green result.

Record:

- exact Argus main SHA;
- exact candidate closeout head;
- test/probe counts;
- CI run;
- latest stable Hermes tag/version;
- fresh warning-source Hermes main SHA;
- OA2 reopen result: `CLOSED` or concrete trigger.

Do not rely only on the old PR #35 receipt: closeout is the exact-main
acceptance record.

## 4. Allowed changes

Preferred changes are documentation/authority only:

- mark OA1 DONE / PR #35;
- mark OA-close complete after acceptance;
- mark OA phase COMPLETE;
- retain OA2 CLOSED / UPSTREAM-GATED;
- select R1c as the next task;
- refresh repository/vault roadmap pointers.

No production code change is expected.

A tiny documentation correction may be recorded as debt rather than changing
production code. Known example at activation: `run_check()` still documents
only `ok | fail | unconfigured` although `skipped` is now valid. This is not
an OA-close blocker.

## 5. Stop conditions

STOP and return to the maintainer if any acceptance item requires:

- changing `integration-discover.py`;
- changing auth classification rules;
- changing health verdict behavior;
- adding a test solely to make a failing behavior look accepted;
- implementing OA2;
- adding external credential readers;
- schema migration;
- provider alias normalization;
- deployment or credential mutation.

A functional failure is an **OA1 regression**, not permission to repair it
inside closeout.

## 6. Production boundary

OA-close does not authorize:

- deploy/restart;
- login/logout;
- credential rotation;
- token refresh;
- production `auth.json` mutation;
- polling `/api/providers/oauth`.

If the maintainer separately authorizes a production deploy, a read-only
observation that `oauth:openai-codex` appears may be added as extra evidence,
but it is not required for closeout.

## 7. Known limitations retained

Closeout does not attempt to solve:

- raw provider alias drift such as `xai` vs `xai-oauth`;
- external CLI/keychain-only auth;
- Vertex ADC / Bedrock IAM / Azure Entra ambient chains;
- universal API-key pool inventory;
- `oauth` entity naming debt;
- multi-profile implementation.

These remain explicit known limits, not OA1 failures.

## 8. Pytna review

One narrow acceptance review only.

Check:

- exact main/head provenance;
- all acceptance items above;
- secret-canary evidence;
- static-auth false-green absence;
- absence of an accidental OA2/runtime dependency;
- authority docs point to R1c only after evidence passes.

Do not request:

- new auth providers;
- external stores/keychains;
- universal credential inventory;
- schema rename;
- alias normalization;
- OA2 implementation;
- broad redesign.

If any functional defect is found, recommendation is
`OA1 REGRESSION -> MAINTAINER`, not a closeout remediation wishlist.

## 9. ZCode receipt

```markdown
# OA-close outcome

## Exact baselines
- Argus merged main:
- closeout candidate head:
- Hermes stable:
- Hermes warning-source main:

## OA1 exact-main acceptance
- nested Codex singleton:
- pool-only Codex:
- generic future id:
- API-key / malformed negatives:
- storage-shape stability:
- Copilot PAT-only:

## Secret boundary
- canary scan:

## Health truthfulness
- static oauth status/verdict:
- healthy count:
- quick renderer:

## No-effects review
- Hermes/runtime calls:
- network:
- refresh:
- auth-store writes:

## Full suite / CI
- probes:
- static checks:
- diff check:
- CI:

## OA2 gate
CLOSED | REOPEN TRIGGER FOUND

## Known limitations retained

## Production actions
None.

## Final recommendation
OA PHASE COMPLETE -> R1c
| OA1 REGRESSION -> MAINTAINER
| OA2 REOPEN TRIGGER -> MAINTAINER
```

## 10. Pytna receipt

```markdown
# OA-close review

## Exact head reviewed

## Exact-main provenance

## Acceptance failures
- none | concrete blockers only

## Secret / false-green checks

## OA2 gate

## Scope review

## Recommendation
PASS-TO-CLOSE-OA
| OA1-REGRESSION
| BLOCKED-FOR-MAINTAINER
```
