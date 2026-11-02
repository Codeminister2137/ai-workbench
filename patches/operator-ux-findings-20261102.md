# Operator UI findings — owner live test 2026-11-02 (patch candidate for remote-ai-operator)

Source: owner's first live phone pass over the served UI (scripted mode).
Recorded verbatim-ish with technical mapping; fixes belong to a sibling-side
UI/polish session, not to this note.

## A. Demo flow (§8 → §3 → §6) is undiscoverable

- Owner: going from section 8 (Demo playground) to section 3 (Review &
  approve) and then section 6 (Task history) "is a mess, no user would
  understand this is the intended way to run the demo".
- Mapping: `newTask` (§6) only resets the draft; `submit` (§8) creates+runs;
  `approve` (§3) approves. Three sections must be visited in a non-obvious
  order; §6's button label ("New task") promises what §8's button does.
- Direction: a single guided demo path (one section or a wizard order),
  or co-locate draft → run → approve. Needs owner decision on layout.

## B. §6 Task history scope is unclear

- Owner: "§6 being connected only to demo is pretty bad, unless that's just
  dependent on the mode."
- Mapping: §6 lists `recent_tasks` for the owner principal. Open question:
  do supervisor-run tasks surface there, or only playground demo tasks?
  Either the scope or the label ("Task history" vs "Demo tasks") must change.

## C. Approve-plan ordering (Flow B)

- Owner: "If I'm supposed to check settings etc before clicking approve plan
  then that button should be below settings, shouldn't it?"
- Mapping: `supervisorApprovePlan` lives in §1 Chat, but §2 Run settings
  (run mode, supervision) must be reviewed first. Layout should read
  Chat → settings → approve, or the plan approval should restate the
  effective settings inline.

## D. Progress doesn't follow the thread

- Owner: "Progress doesn't automatically switch to correct thread, in fact
  I think it's too tied to our open reply thread."
- Mapping: §4 Progress renders the selected *task* view, not the open
  supervisor thread; thread runs and their status need a thread-scoped
  progress surface (or auto-follow).

## E. Review & validation (§3) is confusing

- Owner: "Review and validation tab is confusing." No further detail yet —
  needs a follow-up question or a UI pass with the owner watching.
- Candidates: diff vs receipt vs evidence split across `<pre>` blocks,
  nonce/lifetime invisibility, no plain-language verdict line.

## Status

Findings recorded; no code changed. Proposed next step: sibling-side UI
batch carrying A–D plus an owner walkthrough for E.
