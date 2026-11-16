# Muse window loss: capture and recovery

Three vanishes on 2026-11-16, zero OS trace (no event-log or WER entry,
Defender clean, no scheduled task near any vanish time). Twice the
window died while every client survived and kept working; once (an old
resumed session) the processes went with the window. Cause unknown —
the countermeasure below makes the next occurrence a one-minute,
fully-evidenced non-event instead of a manual scramble.

## When a window vanishes

1. Capture (one double-click, or one command):
   `capture-window-loss.cmd <session-id>` (session id optional).
   Writes a timestamped bundle to `.tmp/window-loss/` (never
   committed): process table, visible-window enumeration, screenshot
   attempt, WER archives, event-log tail, reliability records,
   nearby scheduled tasks, session state.
2. Reclaim (dry-run first):
   `recover-muse-session.cmd <session-id>` prints the kill set and
   the exact drill without sending any signal. Re-run with
   `-Execute` to kill, verify, and open a fresh `muse resume`
   window. Its own chain is always excluded from the kill set, so
   run it from a fresh window outside the lost session —
   otherwise the lost chain hides among the excluded ancestors
   and there is nothing to kill.
3. Tell the agent where the bundle is; the bundle says which
   context captured it (interactive vs window-blind) so blind
   evidence is never mistaken for "no windows existed".

## What the agent cannot do here

The agent sandbox is window-blind by isolation (proven: a live
conhost reports handle 0 from inside it). Window enumeration and
screenshots therefore need the owner-side run above; everything
else the agent can collect itself.

## Open follow-up (needs owner decision)

A scheduled-task watchdog that polls visible conhost windows every
few minutes and auto-captures on vanish detection. That is a
persistent background service, so it ships only on explicit owner
approval — the on-demand scripts above are the approved slice.
