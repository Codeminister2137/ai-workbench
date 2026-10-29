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
$sleepScript = 'C:\Users\Jakub\PycharmProjects\AI-projects\scripts\workstation-sleep.ps1'
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
