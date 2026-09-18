# OA1b contract — OAuth evidence rendering semantics

Status: **NOW / READY FOR IMPLEMENTATION**

Baseline:

```text
Argus main = 0e4c0850f1ffe94a39ccaccc82c06f177b6e48fe
OA0 / PR #33 = DONE / STATIC ONLY
OA1 / PR #35 = DONE / MERGED
OA-close activation / PR #36 = DONE
OA-close = PAUSED by production UX finding
```

## 1. Production finding

After deploying OA1, Argus correctly discovers persisted account-auth evidence:

```text
oauth:nous
oauth:openai-codex
```

but the bot renders them as:

```text
⏸️ oauth nous — пропущено
⏸️ oauth openai-codex — пропущено
```

and the quick view can summarize them as:

```text
⏸ N проверок пропущены политикой
```

This is not the intended user-facing meaning.

OA1 intentionally changed the internal health semantics from false-green
`healthy / logged in` to canonical `skipped` because persisted credential
evidence is not a runtime login/health proof.

The renderer then projected the generic word "skipped/пропущено" literally,
losing the important distinction:

```text
static OAuth evidence was found
but runtime health was intentionally not verified
```

The internal conservative verdict is correct. The presentation is misleading.

## 2. Required outcome

Preserve OA1's canonical/report semantics unchanged:

```text
status = skipped
verdict = skipped
summary.healthy does not increase
```

but render OAuth evidence as a distinct **informational presentation state**.

Desired user-facing meaning:

```text
🔐 oauth nous — учётные данные обнаружены · runtime-статус не проверяется
🔐 oauth openai-codex — учётные данные обнаружены · runtime-статус не проверяется
```

Exact Russian wording may be slightly adjusted for clarity, but it must express:

1. evidence/credentials were discovered;
2. Argus did not verify runtime login/health;
3. this is not a failure;
4. this is not a successful health check either.

## 3. Owner surface

Primary owner:

```text
scripts/webhook.py
```

Allowed adjacent surface:

```text
tests/probes.py
```

Do not change `integration-discover.py` or the OA1 auth classification rules.

Do not change `health-check-v2.py` verdict semantics for this fix.

A one-line docstring correction in `health-check-v2.py` may be included only
if the implementation already touches that file for an unavoidable reason.
Prefer no production health-engine change.

## 4. Presentation classification

For schema-v2 rendering, treat a check as **OAuth auth evidence** only when:

```text
verdict == "skipped"
AND primitive == "oauth"
```

Do not add a new schema-v2 verdict.

Do not infer this from provider names.

Do not key on human-readable detail text if structured fields already suffice.

All other skipped checks retain the existing generic skipped presentation.

## 5. Full view behavior

Current generic branch:

```text
skipped -> ⏸ <label> — пропущено
```

must remain for non-OAuth skipped checks.

For OAuth auth-evidence rows, render a neutral/informational line such as:

```text
🔐 oauth nous — учётные данные обнаружены · runtime-статус не проверяется
```

Requirements:

- no `⏸` icon for OAuth evidence;
- no bare `пропущено`;
- no `✅`;
- no `logged in` / `вошёл` / `авторизован` claim;
- no token/source/private metadata.

The OAuth group title remains acceptable:

```text
🔐 OAuth-провайдеры
```

### Full-view count line

Do not count OAuth auth-evidence rows visually as generic `⏸ skipped`.

The underlying JSON summary remains unchanged.

For rendering only, compute:

```text
oauth_evidence_n = skipped rows with primitive=oauth
generic_skipped_n = canonical skipped - oauth_evidence_n
```

Display the generic skipped count only for `generic_skipped_n`.

If useful, show a separate neutral auth-evidence count, for example:

```text
🔐 2 auth evidence
```

or an equivalent compact Russian phrase.

Do not make the displayed counts mathematically imply those rows are healthy.

## 6. Quick view behavior

Quick view must make the same distinction.

### Only healthy + OAuth evidence

When there are:

- no failures;
- no unknowns;
- no generic skipped checks;
- one or more OAuth evidence rows;

do **not** render the generic:

```text
⏸ N проверок пропущены политикой
```

and do **not** claim every integration is verified healthy.

Use a neutral summary, for example:

```text
🩺 Интеграции: X/Y подтверждены healthy
🔐 OAuth: nous, openai-codex — учётные данные обнаружены, runtime-статус не проверяется
```

Exact wording may be compact, but it must not say:

- `всё в порядке` as a claim over the unverified OAuth rows;
- `пропущены политикой` for OAuth evidence.

### Mixed problems + OAuth evidence

If failures/unknowns/generic skipped checks also exist:

- keep their current problem presentation;
- add OAuth evidence separately as informational context;
- do not consume the problem budget in a way that hides real failures.

## 7. Required probes

Add focused renderer probes covering at least:

1. **full OAuth evidence**
   - OAuth skipped row renders with informational OAuth wording;
   - contains no `пропущено`;
   - contains no `⏸`;
   - contains no `✅`.

2. **full generic skipped control**
   - a non-OAuth skipped row still renders as generic skipped;
   - existing semantics are preserved.

3. **quick OAuth-only**
   - no `пропущены политикой`;
   - no blanket `всё в порядке`;
   - OAuth provider names are visible or the auth-evidence count is explicit;
   - wording states runtime status is not verified.

4. **quick mixed**
   - a real failure remains visible;
   - OAuth evidence is informational and does not replace/hide the failure.

5. **counts**
   - OAuth evidence does not appear under the rendered generic skipped count;
   - canonical JSON summary is not mutated.

6. existing OA1 false-green probe remains green:
   - health report still has `verdict=skipped`;
   - `summary.healthy == 0`.

7. full regression suite + CI green.

## 8. Explicit non-goals

OA1b does not:

- change OAuth discovery;
- change auth-store classification;
- change schema-v2;
- add a new canonical verdict;
- turn OAuth evidence green;
- call Hermes/runtime auth;
- implement OA2;
- validate tokens;
- refresh tokens;
- change credential storage;
- solve provider aliases;
- change non-OAuth skipped semantics;
- redesign the Telegram UI.

This is a narrow presentation semantics fix.

## 9. OA-close relationship

OA-close is paused until OA1b passes.

After OA1b merges:

```text
OA1b acceptance
 -> resume OA-close
 -> OA PHASE COMPLETE
 -> R1c
```

The production observation that triggered OA1b should be recorded in the
OA-close receipt as a caught-and-fixed presentation regression.

## 10. ZCode receipt

```markdown
# OA1b outcome

## Exact baseline/head

## Production finding reproduced

## Rendering rule
- oauth evidence classification:
- generic skipped preserved:

## Full view
- OAuth wording:
- generic skipped control:
- count behavior:

## Quick view
- OAuth-only:
- mixed failure + OAuth:
- blanket-green check:

## Canonical semantics preserved
- health verdict:
- healthy count:
- schema changes:

## Tests / CI

## Changed files

## Out-of-scope findings

## Production actions
None.

## Recommendation
READY FOR PYTNA | BLOCKED
```

## 11. Pytna focus

Review the exact committed head.

High-value failures:

1. OAuth evidence still says `пропущено`;
2. OAuth evidence becomes green/healthy;
3. generic skipped semantics regress;
4. quick view claims `всё в порядке` across unverified OAuth rows;
5. real failures are hidden by OAuth informational rows;
6. renderer keys on provider names or detail text unnecessarily;
7. schema/report semantics are changed for a presentation bug;
8. scope expands into OA2/runtime validation.

Recommendation:

```text
PASS-TO-MERGE | REMEDIATE | BLOCKED-FOR-MAINTAINER
```
