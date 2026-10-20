# Unattended sleep timer

Owner update (2026-10-20): schedule deadline sleep at the **start** of each new
unattended window, before implementation. A usage-limit interruption must not
prevent an already-started timer from requesting sleep. An explicit owner
no-sleep override still wins. Never schedule retrospectively for an expired run
or while the owner has returned to attended work.

Record the fixed UTC deadline and reserve enough time before it for task cleanup,
verification, handoff and reporting. The startup fallback requests sleep at that
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
$sleepArguments = '-NoProfile -NonInteractive -File "{0}" -Sleep -SleepAtUtc "{1}" -ReceiptPath "{2}" -CancelPath "{3}"' -f $sleepScript, $sleepDeadline, $sleepReceipt, $sleepCancel
Start-Process -FilePath powershell.exe -WindowStyle Hidden -ArgumentList $sleepArguments
```

Before starting work, read the receipt with a bounded wait and verify
`status=sleep_scheduled`, the exact `planned_sleep_utc`, cancellation path and
process identity. Investigate missing/error receipts immediately; do not claim a
timer exists just because launch returned. Save all paths, PID, due time and
original deadline in the plan and `CURRENT_CONTEXT.md`. Tell the owner the due
time in Europe/Warsaw and the **fully substituted** cancellation command at
startup, not just at closeout:

```powershell
New-Item -ItemType File -Force -Path '<exact absolute sleep-startup.cancel path>'
```

Cancellation is acknowledged by `sleep_cancelled` in the receipt. The helper
checks every second while waiting; cancellation cannot undo a sleep request
already submitted. An owner return or attended switch requires cancellation and
verification before resuming work. Never delete markers or reuse receipt paths.

## Closeout and interruption

The existing default remains sleep ten minutes after normal completion, including
an evidenced early stop. After owned cleanup and handoff, launch and verify a
fresh `-Sleep -DelaySeconds 600` timer, then cancel the startup timer and verify
its cancellation. Record both receipts and expose the replacement's exact cancel
command. Complete this replacement before the startup deadline; if that cannot
be done safely, retain the verified deadline fallback and report its actual due
time. Do not leave two active timers, silently drop the fallback, or remove an
owner's explicit not-before restriction. When needed, absolute scheduling permits
`-NotBeforeUtc` only when the selected sleep time is at or after that restriction.

Preserve timer ownership and original deadline across context changes. After a
usage cutoff, the existing helper continues without model calls; do not silently
restart the window. On return inspect the actual receipt/process state. Report
scheduled, requested, rejected and verified Windows transition separately.

## Rolling timer proposal — awaiting owner decision

A renewable 30-minute timer could reduce idle time after an interruption. Renew
about every ten minutes during ordinary checkpoints, before starting a long
operation, and before context handoff. Its due time must cover the longest
remaining hard task bound plus cleanup and ample working headroom; renewals must
never extend the work window or an inference allowance. An operation that cannot
fit still must not start. Refreshing only every thirty minutes races expiry.

This needs a defined renewal/cancellation mechanism and missed-heartbeat policy;
it is not yet implemented or an active requirement. A single startup deadline
timer is simpler but can leave the PC awake until the deadline after interruption.
The local waiting/renewal work should be small, but has not been benchmarked.
Ten-minute refreshes mean roughly six lightweight checkpoints per hour; combining
them with normal progress checks avoids separate model/reviewer invocations.
