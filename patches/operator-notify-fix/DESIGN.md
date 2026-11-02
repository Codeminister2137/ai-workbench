# Owner-notification gap fix — design

Base: `remote-ai-operator` at `cc3577e`.

## Incident (2026-11-02)

An owner thread message sat invisible with only a scripted ack. Verified
read-only against the base:

- `supervisor_runner.py` already has `send_owner_mail` + waiting-on-owner run
  mails, but the nested `_notify_send_or_none` returns `None` unless
  `supervision == "unattended"`, so an attended `serve` NEVER notifies.
- Nothing notifies about new owner thread messages or stalled/failed runs
  outside the drain mail path, so an external supervisor has nothing to poll.

## Decision 1 — key run-event mail in every supervision mode

`notify_plan(operator)` (new module-level helper in
`src/remote_operator/supervisor_runner.py`, replacing the nested
`_notify_send_or_none`) returns `(notify_send, notify_on)` for the serve
drain worker:

- SMTP configured → a live sender in EVERY mode. Attended notifies on
  `waiting_on_owner` + `failed` + completed-after-questions; unattended keeps
  its existing full verbosity (`completed`, `failed`, `cancelled`,
  `awaiting_approval`, `waiting_on_owner`).
- SMTP missing → `(None, full-set)`: silent skip. Never a crash, never
  dry-run receipt spam (no `send_owner_mail` call at all, so no receipt
  files). A one-line warning is logged.
- Completed-after-questions is detected by `job_had_owner_questions`
  (linked task history contains an `owner_answer` entry — the durable signal
  `Operator.answer` leaves behind). The flag is persisted on the job file as
  `had_questions` and carried in the notify summary. `format_run_mail` renders
  it as "It is done after your answers. No action needed."

`SupervisorRunner._finish_job` now notifies when `status in notify_on` OR
(`completed` AND `had_questions`), with a sender configured. Direct
`SupervisorRunner(operator, notify_send=...)` callers keep the previous
default set, so existing behavior there is unchanged; only the serve worker's
attended plan differs, and it is strictly more notifying than before.

Deliberately unchanged: `awaiting_approval` and `cancelled` stay silent in
attended mode (the existing `test_attended_never_notifies` case drains to
`awaiting_approval`, so it still passes unmodified). The CLI
`supervisor-drain --notify/--notify-live` path is untouched.

## Decision 2 — agent inbox: `GET /api/supervisor/inbox?since=<seq>`

New module `src/remote_operator/supervisor_inbox.py` + one route in
`_supervisor_routes` (`src/remote_operator/web.py`). Returns:

```json
{"cursor": 123, "items": [{"seq": 120, "type": "owner_message", ...}]}
```

Cursor semantics:

- `since` is a global `events.sequence` (the store's autoincrement log).
- `cursor` is always the current log tip, even when no item matched, so the
  poller unconditionally advances. Unrelated/excluded events still advance it.
- Items are ordered by `seq`; each item carries its own `seq` for resume.

Item types (exactly what needs attention, nothing else):

- `owner_message`: `thread_id`, `topic` (160 chars), `text` (the user turn
  that produced THAT event, 500 chars), `route`. Per-event text is resolved
  by counting `thread_message` events, so two messages yield two exact texts.
- `parked_question`: `task_id`, `question` (500 chars), `run_id` (linked run
  if any, preferring the parked one), `answered` (current task state — the
  poller can skip already-answered rows while history stays stable).
- `run`: `run_id`, `thread_id`, `status` (`failed`|`completed` only —
  `awaiting_approval`/`cancelled`/`waiting_on_owner` finishes are excluded),
  `error`, `had_questions`. `status` is the event-time status, now captured in
  the `run_finished` payload (pre-patch events without it fall back to the
  current job status).

All enrichment is best-effort: a missing thread/task/run file skips that item
without failing the poll. `since`/`limit` misuse raises `ValueError`
(HTTP 422 via `Query(0, ge=0)`); the route requires the same owner/visitor
auth as the other supervisor routes.

### Polling pattern (for the external supervisor)

1. `GET /api/supervisor/inbox?since=0` on first connect; persist `cursor`.
2. Every N seconds: `GET /api/supervisor/inbox?since=<cursor>`.
3. For each item: surface `owner_message` text to the owner, route
   `parked_question` (unanswered) to Review & approve, page on `run` with
   `status: failed`.
4. Set `cursor` to the response `cursor` (even when `items` is empty) and
   repeat. Never reuse an old cursor: items are stable history, the tip moves.

## Alternatives rejected

- **Mail on every event in attended too.** Rejected: attended owners watch the
  UI; full verbosity would double-notify. The three key events are the ones an
  absent owner must not miss.
- **Mail for owner thread messages.** Rejected for this slice: a message is
  not a run event, and mail-per-message spams. The inbox poll covers it with
  exact cursor semantics.
- **Cursor over per-thread sequences.** Rejected: per-thread cursors force the
  poller to track N threads and miss new threads. The global log gives one
  number.
- **Including awaiting_approval runs in the inbox.** Rejected for contract
  exactness: the inbox covers owner messages, parked questions, and
  failed/completed runs. Awaiting_approval stays visible in Review & approve
  and (unattended) mail; revisit if the external supervisor needs it.

## Behavior changes an owner must know

1. Attended `serve` with SMTP configured now SENDS mail for `waiting_on_owner`,
   `failed`, and completed-after-questions runs. Previously it never mailed.
   No SMTP config → still fully silent, as before.
2. Unattended mail is unchanged (same five outcomes, same subjects).
3. Job files gain a `had_questions` boolean (old files read as `False`).
4. Completed-after-questions mail reads "It is done after your answers."
5. New authenticated endpoint `GET /api/supervisor/inbox?since=<seq>` (owner
   and hosted-visitor principals, same auth as other supervisor routes).
6. `settings.py` docstring now states the per-mode mail contract.

## Follow-ups (not in this slice)

- `docs/owner-questions.md` ("Unattended supervision mails the question")
  should gain one line noting attended now mails it too.
- Consider whether the external supervisor also wants `awaiting_approval`
  inbox items.
