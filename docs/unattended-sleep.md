# Unattended sleep timer

Owner update (2026-10-20): schedule deadline sleep at the **start** of each new
unattended window, before implementation. A usage-limit interruption must not
prevent an already-started timer from requesting sleep. An explicit owner
no-sleep override still wins. Never schedule retrospectively for an expired run
or while the owner has returned to attended work.

Record the fixed UTC deadline and reserve enough time before it for task cleanup,
verification, handoff and reporting. The owner approved rolling renewal: one
startup timer requests sleep after 30 minutes without renewal, or later when
needed to protect admitted bounded work. Its due time never exceeds the fixed
deadline. Admit only bounded operations whose complete execution and cleanup fit
before the work cutoff. This timer does not supervise or terminate task workers;
sleep can suspend applications. It cannot recover unsaved work or perform cleanup
after an agent interruption. A local helper surviving an agent cutoff is not a
guarantee against Windows shutdown, logoff, process termination or OS refusal.

## Startup and cancellation

Use fresh absolute paths in an existing writable run-artifact directory. The
following is a template, **not a command to execute during attended work**:

```powershell
$sleepScript = 'C:\Users\Jakub\PycharmProjects\ai-workbench\scripts\workstation-sleep.ps1'
$sleepReceipt = '<fresh absolute run directory>\sleep-startup.json'
$sleepCancel = '<fresh absolute run directory>\sleep-startup.cancel'
$sleepDeadline = '<fixed future UTC deadline, e.g. 2026-10-21T18:00:00Z>'
$sleepArguments = '-NoProfile -NonInteractive -File "{0}" -Sleep -Rolling -SleepAtUtc "{1}" -ReceiptPath "{2}" -CancelPath "{3}"' -f $sleepScript, $sleepDeadline, $sleepReceipt, $sleepCancel
Start-Process -FilePath powershell.exe -WindowStyle Hidden -ArgumentList $sleepArguments
```

Before starting work, read the receipt with a bounded wait and verify
`status=sleep_scheduled`, the expected `planned_sleep_utc`, fixed
`window_deadline_utc`, cancellation path and process identity. Investigate missing
or error receipts immediately; do not claim a timer exists just because launch
returned. Save all paths, PID, due time and
original deadline in the plan and `CURRENT_CONTEXT.md`. Tell the owner the due
time in Europe/Warsaw and this fixed command at startup, not just at closeout.
From the repository root:

```powershell
.\cancel-sleep.cmd
```

This cancels all timers created by this repository's updated helper, including
completion timers, without paths or identifiers. It broadcasts cancellation and
waits up to five seconds for registered timers' receipts; missing acknowledgements
produce a nonzero exit and identify the unresolved receipts. It is safe to repeat.
Inactive timer processes are reported separately while their original receipts
are retained. New receipts record process start time so a reused PID cannot be
mistaken for the timer. An absent process establishes neither an acknowledged
cancellation nor a Windows sleep transition. Unknown process identity remains
pending and produces a nonzero exit.
It does not cancel unrelated Windows or third-party power schedules. A future
explicitly authorized timer can start normally; this is not a permanent no-sleep
setting. Do not automatically rearm or renew after owner cancellation during the
same window; obtain the owner's direction before scheduling again.

Cancellation is acknowledged by `sleep_cancelled` in the receipt. The helper
checks every second while waiting; cancellation cannot undo a sleep request
already submitted. An owner return or attended switch requires cancellation and
verification before resuming work. Never delete markers or reuse receipt paths.

## Attended-presence override — owner requested 2026-11-01

When the owner is at the PC and says so (or is clearly interacting), no sleep
may be scheduled: cancel every pending timer via `.\cancel-sleep.cmd`, verify
each `sleep_cancelled` receipt plus helper exit, and record the override in
the handoff with its start time. Do not renew, re-arm, or schedule closeout
sleep while the override stands — a lease expiring under an attending owner
is the failure this option prevents (observed 2026-11-01: fallback fired at
19:02:39Z while the owner was present because renewal lapsed during message
handling). Heartbeats and inbox polls continue; only power actions pause.
Re-arm only on the owner's explicit direction (e.g. they leave again), with a
fresh receipt path and the unchanged hard deadline.

## Closeout and interruption

The existing default remains sleep ten minutes after normal completion, including
an evidenced early stop. After owned cleanup and handoff, launch and verify a
fresh `-Sleep -DelaySeconds 600` timer, then cancel the startup timer and verify
its cancellation using its individual marker (the all-timer command would cancel
the replacement too). Record both receipts; the owner's command remains
`.\cancel-sleep.cmd`. Complete this replacement before the current timer is due;
if that cannot be done safely, retain the verified fallback and report its actual due
time. Do not leave two active timers, silently drop the fallback, or remove an
owner's explicit not-before restriction. When needed, absolute scheduling permits
`-NotBeforeUtc` only when the selected sleep time is at or after that restriction.

Preserve timer ownership and original deadline across context changes. After a
usage cutoff, the existing helper continues without model calls; do not silently
restart the window. On return inspect the actual receipt/process state. Report
scheduled, requested, rejected and verified Windows transition separately.

## Wake-up-sleep: verify and report after wake (2026-11-21)

Standing follow-up to owner item `e341cfae` and run `f0e36476`: the sleep
requester must close the loop on its next execution after wake. Preserve the
receipt path and pending verification in the handoff before requesting sleep;
if interrupted, the next session resumes that verification. This is a requester
workflow, not a new timer or background monitor. The remote-wake idle-sleep
request remains subject to existing work/presence guards; whether audio should
block sleep remains an open owner question.

Audio-report provenance (owner follow-up `dac8bf5b`): see the **Agent report**
in dashboard run `f0e36476218c4021a5fc9455c8236e26` (Wake up sleep),
dated 2026-11-20 22:56 Europe/Warsaw, linked from inbox
`e341cfae1a6043b5bf89ba5aec733503`. It reported "Windows reports an active
audio stream" and said it did not request or schedule sleep because idle
status was uncertain. This is a historical agent-reported observation, not
proof of an audio fault, a particular application's involvement, or a failed
Windows sleep request. The audio-blocking policy was a recommendation/question,
not an accepted owner decision. Owner clarification
`86dfdd67b6074866a86504d2e70507c3` records remote wake via Termux, an AI task
given to Mai, and the requirement to connect the report to that task. Do not
repeat those answered questions or infer a physical button actor from the
Windows wake-source label.

Historical mapping resolved by owner answer `a0c04c3f257d42028791e0ddb494c336`
(2026-11-21): both wakes at 01:26:49 and 13:51:37 Europe/Warsaw were the
owner's. The originating task and report destination are **Wake up sleep**,
inbox `e341cfae1a6043b5bf89ba5aec733503`, run
`f0e36476218c4021a5fc9455c8236e26`. It was the only owner-created task in
the inspected overnight window (20 November 21:00 through 21 November 04:00
Warsaw), created at 22:53:47 on 20 November. The run receipt records
`source=mai-session` and Mai session `33479568a6db4a3585382aed0ade0740`;
Codex was its backend, not evidence of a different task channel. The earlier
audio report and the later sleep outcome belong to this same task. This
identifies the task/report destination; it does not establish who invoked the
Sleep-button API or claim that the earlier run requested the later sleep.

The attached historical outcome is: slept **12 min 36 s**, 21 November
01:14:13–01:26:49 Warsaw, woken by **Power Button** (SleepStudy session 12).
The saved receipt `.tmp/owner-sleep/sleep-owner.json` records a request at
01:14:10 and `sleep_api_returned_success` at 01:26:49. Troubleshooter Event 1
independently matches those endpoints; the request-to-wake span includes
transition overhead. The Windows source label and the owner's account of
remote waking via Termux are separate evidence, not a contradiction requiring
another actor question. This mapping closeout does not decide the audio policy
or complete the originating task's automatic remote-wake behavior requirement.

1. Re-read the actual receipt, including `status` and `transition_times_utc`.
   Distinguish scheduled, requested, cancelled, blocked and API-returned states.
   `sleep_api_returned_success` alone does not prove sustained Windows sleep.
2. Query System log `Microsoft-Windows-Power-Troubleshooter` Event 1 for the
   matching request/wake interval. Inspect SleepTime, WakeTime and wake source;
   do not attribute the latest unrelated wake to this request. Correlate
   Kernel-Power events and, when needed, existing SleepStudy evidence and
   `powercfg /lastwake`. A seconds-apart 42/107 pair alone proves neither an
   aborted suspend nor its duration.
3. Calculate elapsed time from matched sleep/wake evidence. Label the source:
   Troubleshooter's request-to-wake span can include transition overhead;
   SleepStudy's Sleep session measures the sleep interval. Never use the API's
   return timestamp as work-end time or its call duration alone as proven sleep.
4. Report visibly through the originating task/channel: "slept X min, woken by
   Y", with the dated Europe/Warsaw interval, receipt status and evidence source.
   Example: 2026-11-21 SleepStudy session 12, 01:14:13-01:26:49 Warsaw:
   "slept 12 min 36 s, woken by Power Button"; Troubleshooter starts at 01:14:10.
   A wake source does not identify the actor or physical mechanism. Owner answer
   `86dfdd67` (2026-11-21): the owner wakes the PC remotely via Termux and gave
   Mai an AI task. Record that as the owner's account alongside the Windows
   "Power Button" label; do not infer a physical button press or the dashboard
   Sleep button as the task's entry point. The later `a0c04c3f` answer and
   historical mapping above identify the originating task and prior Mai report.
   The owner requires the report to be connected to that AI task: retain its
   task/run reference with the sleep receipt and pending check, then attach the
   post-wake report to the same task/thread, including its run reference when
   available. A standalone sleep clarification does not replace that report.
   If the originating task cannot be located, state that limitation and preserve
   the missing link for investigation; do not invent an identifier or delivery.
5. If evidence is absent, conflicting or unavailable, report the observed receipt
   status and "sleep outcome/duration/wake source unverified" as appropriate.
   Preserve the pending check and name missing evidence. Do not remain silent,
   infer success, retry sleep, or introduce a timer to obtain a result. Use inbox
   for unresolved owner questions; mail remains subject to existing policy.

## Pending-update gate (2026-11-14)

Before requesting sleep, the helper refuses when Windows Update servicing
reports a reboot is required (`RebootRequired` / `RebootPending`). Sleeping
through a pending update reboot trades a clean owner reboot for an
update-driven one mid-work. A refused timer records
`status=sleep_blocked_pending_update` with the signals in `detail` and
requests no sleep; the agent reports it and asks the owner to reboot for
updates instead of sleeping. `PendingFileRenameOperations` alone never
blocks (routinely benign).

## Rolling renewal — owner approved 2026-10-20

A renewable 30-minute timer reduces idle time after an interruption. Renew
about every ten minutes during ordinary checkpoints, before starting a long
operation, and before context handoff. Its due time must cover the longest
remaining hard task bound plus cleanup and ample working headroom; renewals must
never extend the work window or an inference allowance. An operation that cannot
fit still must not start. Refreshing only every thirty minutes races expiry.

Renew the existing timer rather than launching another process:

```powershell
& $sleepScript -Renew -ReceiptPath $sleepReceipt
# Before long work, include its hard end + cleanup + ample working headroom:
& $sleepScript -Renew -ReceiptPath $sleepReceipt -ProtectedUntilUtc '<future UTC bound>'
```

The helper atomically submits a lease for the later of now + 30 minutes and the
protected bound, capped at the original deadline and respecting any not-before
restriction. A protected bound after the deadline is rejected; reduce work instead.
Routine refresh never shortens an already protected interval. This can leave
extra headroom after a task finishes; normal closeout replaces the timer.
Verify the updated due time in the scheduling receipt before admitting that work;
submission alone is not acknowledgement. Expired and cancelled leases cannot be
renewed. If supervision is interrupted, the last acknowledged timer still runs;
missed renewal means sleep, not automatic renewal by another background service.
Keep a next-renewal checkpoint no more than ten minutes away and renew before a
blocking operation when required. No standalone reviewer/model call is needed.
Do not wait until lease expiry to renew. Invalid control state stops the helper
with an error rather than requesting sleep; investigate immediately.

Local control state and append-only timer registrations live under ignored
`artifacts/workstation-sleep-control`; receipts/leases remain with their run
artifacts. Preserve them as evidence while timers remain relevant. No new service,
scheduled task, dependency or machine-wide configuration is installed.

A deadline-only timer is simpler but can leave the PC awake until the deadline
after interruption.
The local waiting/renewal work should be small, but has not been benchmarked.
Ten-minute refreshes mean roughly six lightweight checkpoints per hour; combining
them with normal progress checks avoids separate model/reviewer invocations.

## Dashboard wake-idle interlock

The existing dashboard supervision/drain tick checks wake-idle sleep when its
periodic scheduler is enabled. Startup and detected resume receive 30 minutes
of grace. Only unattended mode is eligible. Open agent inbox tasks, queued or
running runs, claimed runs (including claim files), and runs finished within
30 minutes block sleep. Owner inbox items and audio playback do not block it.

Task admission and mode changes share `wake_idle.interlock`; new work cancels
the pending idle handoff. RunDrain uses the dependency-free agent-side
`ai_agent.wake_idle_lock.interlock` with the same protocol: byte zero of
`<data_dir>/wake-idle.lock` via Windows byte-range locking, or POSIX `flock`.
Claim, release, requeue and publish mutations take this lock and touch the idle
cancel marker while holding it; touching the marker alone cannot serialize
with suspend. JSON staging, execution and callbacks stay outside the lock.
Work admitted before sleep commitment cancels the handoff; mutations arriving
after the helper owns the commitment lock wait until it releases the lock.

The helper performs display restoration without that lock, then holds the same file lock across a fresh Python state check and the
Windows suspend call. Unreadable state fails closed. The helper's own receipt
(`wake-idle-helper.json`) distinguishes cancellation, rejection and API return;
an API return alone does not prove a sleep transition.

`wake_idle.commit_sleep` is the single handoff seam. This implements option A
per e8eb8857/A and the safety condition; 4b7c31d0 remains pending owner
retro-confirmation. Option B was excluded because deferring admission without
a configured waker can strand queued work. No scheduled task is installed.
`WakeIdle.tick(dry_run=True)` writes `wake-idle.json` without invoking the helper.
