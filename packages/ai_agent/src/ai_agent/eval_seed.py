"""Mai eval seed v0: 24 tasks from real runs (charter 25.11, data only).

Transcribed from docs/plans/mai-program-20261125.md. Oracles:
- starves: a future run COMPLETES (reference: the stranded outcome);
- infra: a future run fails CHEAP with a clean error (no spin);
- completed: a future run REPRODUCES the accepted outcome.
Retire tasks whose oracle rots (area rewritten) rather than red-shifting.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SeedTask:
    """One eval task: historical reference + oracle for future runs."""

    seed_id: int
    run_ref: str  # 8-hex prefix of the reference run
    kind: str  # "starve" | "infra" | "completed"
    title: str
    reference: str  # what happened historically
    oracle: str  # what a future run must do to PASS


SEED: tuple[SeedTask, ...] = (
    SeedTask(
        1, "15e52c0c", "starve", "Trainer Q6/Q7 close-out", "starved, zero content", "completes"
    ),
    SeedTask(
        2,
        "1e7291c3",
        "starve",
        "Opencode structured-output proof",
        "starved, clean tree",
        "completes",
    ),
    SeedTask(3, "281b32f1", "starve", "Triage run 87a312c7", "triage itself starved", "completes"),
    SeedTask(
        4,
        "43e4611d",
        "starve",
        "Project registry systemic fix",
        "starved WITH partial work",
        "completes",
    ),
    SeedTask(5, "56ee2391", "starve", "Triage run c54b03d8", "triage itself starved", "completes"),
    SeedTask(
        6,
        "6dae4169",
        "starve",
        "Project registry (retry)",
        "starved WITH partial work",
        "completes",
    ),
    SeedTask(7, "7742bb62", "starve", "Triage run 1e7291c3", "command-spin starve", "completes"),
    SeedTask(
        8,
        "7c17776b",
        "starve",
        "Opencode proof (retry)",
        "starved, uv.lock collateral only",
        "completes",
    ),
    SeedTask(9, "87a312c7", "starve", "Opencode proof", "starved, clean tree", "completes"),
    SeedTask(10, "89bfb241", "starve", "Triage run b42d32c3", "command-spin starve", "completes"),
    SeedTask(
        11, "a6342bf6", "starve", "Triage run 43e4611d", "19 commands, clean tree", "completes"
    ),
    SeedTask(
        12,
        "aa030220",
        "starve",
        "Allowance health",
        "starved WITH real edits (kiro_usage)",
        "completes",
    ),
    SeedTask(13, "c54b03d8", "starve", "E2E follow-up", "75 receipts, uv.lock only", "completes"),
    SeedTask(14, "d448f334", "starve", "Triage run 15e52c0c", "starved, clean tree", "completes"),
    SeedTask(
        15,
        "09b0ece8",
        "infra",
        "Triage 3e7d9554",
        "kimi 400",
        "clean error + cheap triage, no spin",
    ),
    SeedTask(
        16,
        "3e7d9554",
        "infra",
        "Provider scouting",
        "kimi 400 (done by hand after)",
        "clean error + cheap triage, no spin",
    ),
    SeedTask(
        17,
        "ad22d8ff",
        "infra",
        "Allowance health",
        "kimi 400",
        "clean error + cheap triage, no spin",
    ),
    SeedTask(
        18,
        "d2b493cb",
        "infra",
        "Triage ad22d8ff",
        "kimi 400",
        "clean error + cheap triage, no spin",
    ),
    SeedTask(
        19,
        "9993d94e",
        "infra",
        "Provider scouting",
        "compaction overflow",
        "clean error + cheap triage, no spin",
    ),
    SeedTask(
        20,
        "b8e7de5d",
        "completed",
        "Allowance-aware route ranking",
        "accepted outcome + regression coverage",
        "reproduces the accepted outcome",
    ),
    SeedTask(
        21,
        "f1a5e441",
        "completed",
        "Digest readability",
        "human run summaries",
        "reproduces the accepted outcome",
    ),
    SeedTask(
        22,
        "bdc99a4c",
        "completed",
        "E2E generator grounding gap fix",
        "accepted fix",
        "reproduces the accepted outcome",
    ),
    SeedTask(
        23,
        "88a3a5f2",
        "completed",
        "Review + integrate run branch",
        "review-only reference",
        "reproduces the accepted outcome",
    ),
    SeedTask(
        24,
        "7c2eee0a",
        "completed",
        "Sweep triage",
        "report-only reference, honest empty",
        "reproduces the accepted outcome",
    ),
)


def get_seed() -> tuple[SeedTask, ...]:
    """Seed tasks in charter order."""
    return SEED
