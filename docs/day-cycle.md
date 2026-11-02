# Day cycle: close at night, open in the morning

One helper owns the overnight boundary: `scripts/day_cycle.py`.
It never deletes, resets, or force-pushes anything.

## Evening: `close`

```powershell
.venv/Scripts/python.exe scripts/day_cycle.py close
```

It snapshots git state for both checkouts (branch, cleanliness,
ahead/behind, HEAD), the listening service ports with their exact
command lines, and Docker daemon state into
`artifacts/day-cycle/close-<utc>.json`, then prints a verdict:

- `READY FOR POWER OFF` — both trees clean and pushed.
- `NOT READY FOR POWER OFF` — explicit blocker list (uncommitted
  files, unpushed commits, behind origin, unreadable git).

Power off only on the READY line. The snapshot is what `open`
replays in the morning.

## Morning: `open`

```powershell
.venv/Scripts/python.exe scripts/day_cycle.py open
```

For each expected service (operator serve :8765, dashboard :8766,
Ollama :11434) it reports `already listening` or starts the missing
one — replaying the exact snapshotted command line, or `ollama serve`
for Ollama — then re-checks every port, reports Docker daemon state
(starting Docker Desktop itself when the daemon is down, then waiting
up to three minutes for the daemon), and smoke-imports the workspace packages. It exits
nonzero with explicit lines for anything still not listening.

After a green `open`, continue with the handoff in `CURRENT_CONTEXT.md`
and the next-day prompt from the previous closeout.
