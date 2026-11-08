# Unexpected power losses, 2026-11-06/08 — findings (loop9, read-only)

## Failures (local Warsaw time, from event 6008 messages)

| # | Shutdown | Context |
|---|---|---|
| 1 | 11-06 01:16 | Night, idle |
| 2 | 11-07 18:53 | Evening |
| 3 | 11-07 19:42 | Evening |
| 4 | 11-08 00:35 | Night, idle |
| 5 | 11-08 15:23 | Afternoon, loop8 running tests (moderate CPU) |

Plus a 41 reboot 11-08 12:02 (owner-initiated power cycle, not a failure).

## Ruled out (evidence)

- Windows crash: zero BugCheck 1001 events, zero memory dumps.
- Hardware error records: zero WHEA events in the last 2000 System events.
- GPU/display driver: zero nvlddmkm/amdkmdap/Display errors.
- Disks: all 5 physical disks report Healthy/OK (no SMART failure flags).
- Failed sleep transition: all 42/107 pairs are clean seconds-apart
  transitions; none adjacent to a failure.

## Signature

Abrupt power loss, load-independent (idle nights and active use),
accelerating: 1 → 2 → 2 over three days. Stability index ~5/10.

## Likely causes (ordered, need physical checks)

1. PSU aging or fault (idle + load failures fit failing regulation).
2. Power strip / UPS / wall power (try another socket, bypass strip).
3. Thermal protection (no sensor evidence available; WMI thermal zones
   absent; check fans/dust and BIOS temp readings).
4. Motherboard VRM or RAM seating (reseat, then memtest).

## Recommendation

Software investigation is exhausted: nothing in the OS, drivers, disks,
or loop activity explains these. Next steps are physical: different
socket/strip first (cheapest), PSU test/swap if it recurs, BIOS temp
check, reseat RAM/GPU power. Until then, commit and push often — power
can cut at any time.
