# Xiaomi S4 → Health Connect import runbook

Decision: inbox `173cb000` (2026-11-11) chose **B: Health Connect trickle**
over Gadgetbridge (A) and Notify (C). The S4 pairs with Mi Fitness only;
Health Connect carries steps, workouts, sleep and heart rate on-device,
and our side reads from there. Privacy-copy backfill covers history.

## Owner steps (one time)

1. **Backfill history.** Request the Xiaomi data copy at privacy.mi.com
   (full history: heart rate, SpO2, steps, sleep, workouts, weight).
   Save the files somewhere safe; tell the agent where they landed.
2. **Enable the trickle.** In Mi Fitness: Profile → Third-party data →
   Health Connect → authorize. Allow writing for Steps plus every other
   data type Mi Fitness offers.
3. **Install a reader/export.** Either:
   - Health Sync app (exports CSV/TCX files we can import), or
   - FitMesh (viewing/verification that data flows).
4. **Drop the first export** in an agreed folder and tell the agent.
   The importer is built against that real file, not a guessed format.

## Agent side (after the first export lands)

1. Write an importer for the actual export format (CSV/TCX columns as
   observed) into the knowme-bank trainer area.
2. Map fields to bank entries (activity, sleep, workouts) with dates.
3. Verify: import counts vs. the export, no silent drops, nothing leaves
   the PC except through the already-approved Mi Fitness account.

## Boundaries

- Data path stays on-device + local PC. No new cloud accounts.
- No importer is written before a real export file exists.
- If the trickle proves too thin (missing types), revisit Gadgetbridge (A)
  via a new inbox brief; do not silently switch paths.
