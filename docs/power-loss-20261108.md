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

## Revision 2026-11-09: sleep/wake failure, not power loss (loop10)

Owner observation ("only when AI scheduled sleep") checked against
every sleep receipt. SetSuspendState blocks until wake, so a success
receipt's timestamp = WAKE time. Reconstructed (local):

- 11-07 18:53 event: helper wrote post-wake 19:01:39, fresh boot
  19:02:35 (~1 min later). Death within a minute of wake.
- 11-07 19:42 event: helper wrote post-wake 22:29:37, fresh boot
  22:30:38 (~1 min later). Same signature.
- 11-08 15:23 event: helper requested sleep 15:24:53, wrote
  post-wake 18:38:33 (owner's remote WoL?), fresh boot 18:39:26
  (~1 min later). Same signature; the 6008 "15:23" stamp is the
  last pre-sleep flush, not the death time.
- 11-06 01:16 and 11-08 00:35 events: same-night helper sleep
  cycles with abnormal immediate wakes (36s, 2s).

Verdict: the S3 sleep/wake path is unstable — immediate spurious
wakes plus crashes within ~1 min of wake (no dump, no 107 flush,
black screen reads as "turned off"). The earlier PSU/power theory
is demoted: 3 of 5 deaths sit exactly on helper sleep/wake cycles.

Suspects (unproven): AMD Radeon driver 32.0.21045.16010 (Oct 2026,
very fresh), Meta Virtual Monitor display hook, Hyper-V + S3
interplay, MSI services. Wake-armed devices are normal (NIC for
owner WoL, keyboard, mouse); no OS wake timers.

Mitigation options went to the owner as an inbox decision (loop10):
hibernate instead of S3 (recommended), pause AI sleep, chase the
driver, or keep S3 (not recommended).

## Recommendation (2026-11-08, SUPERSEDED by the revision above)


Software investigation is exhausted: nothing in the OS, drivers, disks,
or loop activity explains these. Next steps are physical: different
socket/strip first (cheapest), PSU test/swap if it recurs, BIOS temp
check, reseat RAM/GPU power. Until then, commit and push often — power
can cut at any time.
