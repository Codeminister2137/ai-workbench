# Fleet services

One-paragraph explanations for every service on the dashboard Fleet and
Schedule tabs. The dashboard parses this file (strict `## <name>` headers)
and shows each paragraph under its service, so keep headers exact and each
explanation to one short paragraph.

## WorkbenchDashboard

Starts the dashboard at sign-in (installer-registered autostart). If the
dashboard is down, nothing else on this page can report.

## MsiUdpWatchdog

Every 5 minutes: restarts the MSI service when it holds more than 2,000
UDP endpoints. Incidents go to `.tmp/msi-watchdog/incidents.log`.

## UDPPortExhaustionTrap

Fires on the Windows Tcpip 4266 event (UDP port exhaustion) and captures
a read-only UDP snapshot to `.tmp/udp-trap/trap.log`. It never changes
anything; it only preserves evidence.

## CloneScan

Weekly Sunday 06:00: scans the checkout for duplicated code and files a
brief to the owner inbox. Read-only; it never deletes or merges.

## WakeSelfTest

Weekly Sunday 06:30: self-tests the wake path (dashboard probe, NIC
wake-armed check, public IP, DDNS resolution, Gmail SMTP login). Silent
on success; mails the owner once on any failure.

## PrivateBackup

Weekly: backs up company-sensitive working docs, never secrets. Pushes
allowlisted private dirs to the private repo and writes a timestamped
zip to a second physical disk. Aborts before any write when secret-like
files are staged or the snapshot drive is missing.

## WorkbenchWeeklyDigest

Weekly Monday 08:00: fetches the latest Gmail, summarizes it via the
hosted no-training route, and mails the summary to the owner. Receipts
land under `.tmp/weekly-digest/`. Registered by
`scripts/register-weekly-digest.ps1` (owner inbox answer, 2026-11-08).

## dashboard

This server: the dashboard web app serving these pages on loopback. It
is always "up" whenever you can read this.

## ollama

The local Ollama server on this PC (port 11434). Serves the local
models used for free, private inference.

## sleep guard

The unattended-window fallback: puts the PC to sleep at the planned
time unless the owner cancels. Armed only during unattended loops.

## agents

Supervision verdicts over agent runs: stuck (running, silent 30+
minutes), broken (fresh failure, with cause class), parked (queued
over an hour), or ok. Anything stuck or broken needs attention.
