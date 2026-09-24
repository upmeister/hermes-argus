# UX0 contract — Telegram interaction cleanup

Status: **PROPOSED NEXT / PRODUCTION UX FIX**

This is a bounded production-UX patch inserted before RR0b. It changes only the
Telegram control-plane interaction surfaces already exercised in production.
It does not redesign Argus alerts, auth, or menu architecture.

## 1. Exact authority

```text
main at contract creation = f1f9a77659b349a10983fb330badef9ef52b5996
RR0a / PR #51           = merged
```

Primary user evidence:

- the persistent reply keyboard is inconvenient to collapse;
- automatic watchdog/other alert messages should not carry action buttons;
- `Статус` and `Мониторинг` duplicate main navigation inside
  `Обслуживание`;
- `Настройки` and `Обслуживание` should swap positions on the reply keyboard;
- intermittent `🚫 У вас нет доступа к этому боту.` appears after watchdog
  alerts.

Telegram Bot API authority:

- a non-persistent `ReplyKeyboardMarkup` can be hidden and reopened by the
  client using the native keyboard icon;
- `ReplyKeyboardRemove` permanently removes the custom keyboard until the bot
  sends it again;
- pinning can produce service-message updates. Service/non-action updates are
  not user commands and must not enter the user auth-denial path.

Prefer native Telegram keyboard behavior over inventing bot-side toggle state.

## 2. Scope

UX0 owns exactly five behavior changes.

### U1 — reply keyboard must be natively collapsible

Current `reply_keyboard()` sets:

```text
is_persistent = true
```

Remove that persistence request (or explicitly make it false).

Required behavior:

- Telegram clients may hide the reply keyboard with their native keyboard
  control and reopen it later;
- `/start` and the existing plain-text welcome path still send the reply
  keyboard;
- do not add a server-side per-user expanded/collapsed state machine;
- do not use `ReplyKeyboardRemove` as the normal collapse mechanism.

### U2 — reorder Settings and Maintenance

Preserve the existing two-column reply keyboard and all labels/actions.

Swap the positions occupied by:

```text
⚙️ Настройки
🛠 Обслуживание
```

Do not rename their commands.

### U3 — simplify the Maintenance inline menu

Remove the duplicate row:

```text
📊 Статус
🔍 Мониторинг
```

from `webhook.menu_keyboard()`.

The underlying `health` and `watchdog` commands/callback handlers remain
available elsewhere. Do not remove status functionality.

### U4 — no action buttons on automatic alerts

Automatic watchdog problem/recovery messages must not attach the old action
inline keyboard.

Preserve:

- alert text;
- notification/silence semantics;
- critical-alert pinning where it already exists;
- manual action keyboards for `/menu`, `/logs`, `/settings`, silence
  selection, reboot confirmation, etc.

Before editing, prove active callers by repository search.

Known current live owner:

- `scripts/hermes-watchdog.sh` sends problem alerts with `pin keyboard` and
  recovery messages with `keyboard`.

The historical `send-monitoring-report.sh` and `webhook.alert_keyboard()`
are cleanup candidates already owned by RR0b. Do not broaden UX0 into deleting
dead/duplicate runtime surfaces unless a live caller is demonstrated.

### U5 — stop false access-denied messages from non-action updates

Current poller authenticates every update before it decides whether the update
is an actionable text message or callback query.

That allows Telegram service messages (including pin-related messages) or other
non-command updates to enter the denial path even though no user attempted an
action.

Required routing order:

1. classify update type;
2. silently ignore unsupported/non-action/service updates;
3. authenticate actionable callback queries and actionable text messages;
4. route only after auth succeeds.

An unsupported/service update must never produce:

```text
🚫 У вас нет доступа к этому боту.
```

Unauthorized real user commands/callbacks must still be denied.

Also fix the poller's denial cooldown identity: it currently documents a
per-user cooldown but keys callback denials by callback-query id/chat fallback.
The cooldown must be stable per unauthorized user, not per button press.

Do not weaken `WATCHDOG_ALLOWED_USER_ID`.

## 3. Owner surface

Primary:

- `scripts/monitoring-bot-poller.py`;
- `scripts/webhook.py`;
- `scripts/hermes-watchdog.sh`;
- focused tests in `tests/probes.py` or a small dedicated bot test file;
- `CHANGELOG.md`.

Allowed only for evidence/comment synchronization:

- `scripts/send-monitoring-report.sh` comments, if required to remove a false
  claim about the active alert-keyboard canon.

Not owners:

- Deep AI provider/model behavior;
- OAuth/provider discovery;
- RR0b dead-runtime deletion;
- RR0c personal defaults/naming migration;
- RR1 installer/cron redesign;
- i18n framework work.

## 4. Required red-capable tests

At minimum:

1. **reply keyboard collapsibility**
   - rendered reply keyboard does not request `is_persistent=true`;
   - navigation buttons remain present.

2. **reply keyboard order**
   - Settings and Maintenance occupy the requested swapped positions.

3. **maintenance menu**
   - restart/reboot/silence/deep-ai/log actions remain;
   - status/watchdog duplicate row is absent.

4. **automatic watchdog alert**
   - problem alert retains pin behavior but has no inline action keyboard.

5. **automatic watchdog recovery**
   - recovery message has no inline action keyboard.

6. **service message ignored**
   - a Telegram `message` update with no actionable text, including a
     `pinned_message` service shape, emits no denial and no command.

7. **unsupported update ignored**
   - an update type outside message/callback action handling is silent.

8. **unauthorized text command**
   - still produces a bounded denial.

9. **unauthorized callback**
   - still answers the callback and produces at most the intended bounded
     denial.

10. **per-user cooldown**
    - two different callback ids from the same unauthorized user within the
      cooldown do not create two chat denial messages.

11. **authorized paths**
    - authorized reply-keyboard label and callback behavior remain routable.

Record baseline RED evidence for at least U1, U3/U4, and U5.

## 5. Regression gates

At minimum:

```bash
python3 tests/probes.py
python3 tests/test_watchdog_swap.py
python3 -m py_compile scripts/monitoring-bot-poller.py scripts/webhook.py tests/probes.py
bash -n scripts/hermes-watchdog.sh
git diff --check
```

If a dedicated test module is added, run it explicitly and add it to CI only if
the existing CI does not already discover it.

Exact candidate-head `argus-ci` must be green.

## 6. Non-goals

UX0 does not authorize:

- replacing reply keyboards with a new UI framework;
- storing keyboard open/closed state;
- removing manual action keyboards;
- changing alert thresholds, debounce, pinning policy or remediation logic;
- changing bot-token/user-id configuration;
- widening bot access;
- deleting `send-monitoring-report.sh` or other RR0b candidates;
- Deep AI changes;
- general Russian/English localization.

## 7. Stop condition

Stop and report if the fix begins to require:

- a persistent per-user UI database;
- a new Telegram framework/library;
- broad bot-auth redesign;
- alert-delivery architecture changes;
- RR0b cleanup to make the UX behavior work.

## 8. Role-based delivery

### Builder

Return:

```markdown
# UX0 implementation receipt

## Exact baseline/head

## U1 reply keyboard
- persistence change:
- reopen behavior:

## U2 layout
- old positions:
- new positions:

## U3 maintenance menu
- removed duplicates:
- retained actions:

## U4 automatic alerts
- active alert callers found:
- problem alert:
- recovery alert:
- manual keyboards preserved:

## U5 auth/service updates
- classification order:
- ignored service shapes:
- unauthorized text/callback behavior:
- cooldown identity:

## Baseline RED evidence

## Tests / CI

## Changed files

## Out-of-scope findings

## Production actions
None.

## Recommendation
READY FOR FOCUSED REVIEW | BLOCKED
```

### Focused reviewer

Prioritize:

1. auth was weakened instead of non-action updates being ignored;
2. service/pin updates still trigger denial;
3. callback cooldown is still keyed per callback rather than user;
4. manual `/menu` or settings/log/silence keyboards were removed accidentally;
5. reply keyboard becomes impossible to reopen;
6. alert pinning or notification semantics change;
7. dead-code cleanup or Deep AI work enters UX0.

Return:

```text
PASS-TO-MAINTAINER | REMEDIATE | BLOCKED-FOR-MAINTAINER
```

At most one bounded remediation pass.

### Maintainer

After review/remediation:

- reread exact candidate head;
- verify CI/receipt;
- verify no auth widening;
- merge;
- compare merged blobs;
- deploy separately and smoke-test Telegram UI with one automatic alert and one
  authorized/unauthorized interaction fixture where safe.
