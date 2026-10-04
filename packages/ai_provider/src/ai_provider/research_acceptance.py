"""Shared fixed public research acceptance prompt and post-run checks."""

from pathlib import Path

from ai_provider.orchestrated_runs import SQLiteOrchestratedRunStore

RESEARCH_ACCEPTANCE_PROMPT = (
    "Research Ollama's public tool-calling and thinking contracts for a provider-neutral\n"
    "research runner. First call search_web with the public query "
    '"Ollama tool calling documentation".\n'
    """Record discovery limits honestly if it fails or finds nothing. Search snippets do not prove
source retrieval. Fetch these two primary sources using fetch_url:
https://docs.ollama.com/capabilities/tool-calling
https://docs.ollama.com/capabilities/thinking
Then write a source-grounded Markdown report using write_research_report. Give the requested
sections substantive coverage; length is advisory and alone never requires repair or filler.
Write an initial report early and repair mandatory validation errors.
Do not fetch more than four sources. After the first valid report, scrutinize it and refine
concrete weaknesses when the controller requests another pass. Avoid filler and repeated fetches.
Use these eight Markdown sections, each nonempty:
1. Executive summary
2. Source map
3. Candidate models, practices, or facts to add/revisit
4. Recommended fields, metrics, or decision criteria
5. Provider/source-specific notes
6. Risks, stale-data warnings, and unknowns
7. Suggested next implementation slice
8. Repair checks performed
Declare every URL in a Source map table with IDs S1/S2, retrieval status fetched/not fetched, and
the actual UTC access date from its fetch receipt. Every candidate entry must have its own
verified/inferred/unknown/stale-risk label and [S1]/[S2] citation, unless explicitly unknown.
Discuss what remains unknown. Report only executed checks; do not claim the validator proves truth.
Do not edit source files or use shell/delegation. Save progress before finishing each attempt.
"""
)


def check_acceptance(database: Path, report: Path) -> int:
    """Check one dedicated acceptance run after its supervised worker succeeds."""
    if not database.is_file() or not report.is_file():
        print("Acceptance incomplete: missing run database or surviving report")
        return 1
    # The acceptance database is private to this invocation, not the normal run database.
    import sqlite3

    with sqlite3.connect(database) as connection:
        runs = connection.execute("SELECT run_id FROM orchestrated_runs").fetchall()
    if len(runs) != 1:
        print("Acceptance incomplete: expected one dedicated acceptance run")
        return 1
    run_id = runs[0][0]
    store = SQLiteOrchestratedRunStore(database)
    run = store.get_run(run_id)
    if run is None or run.status != "completed" or run.execution_status != "completed":
        print("Acceptance incomplete: research execution did not complete successfully")
        return 1
    stages = {stage.name: stage for stage in store.list_stages(run_id)}
    if not {"implementation", "repair", "final_handoff"}.issubset(stages):
        print("Acceptance incomplete: missing execution or final handoff stages")
        return 1
    if stages["final_handoff"].status != "completed":
        print("Acceptance incomplete: final handoff not completed")
        return 1
    evidence = stages["implementation"].details or {}
    receipts = evidence.get("fetch_receipts", [])
    searches = evidence.get("search_receipts", [])
    if not isinstance(searches, list) or not any(s.get("query_transmitted") for s in searches):
        print("Acceptance incomplete: no actual search query attempt")
        return 1
    if not isinstance(receipts, list) or len(receipts) < 2 or not evidence.get("report_receipts"):
        print("Acceptance failed: missing actual fetch/write receipts")
        return 1
    refinement = (stages["repair"].details or {}).get("research_refinement", {})
    if not isinstance(refinement, dict) or not refinement.get("attempt_count"):
        print("Acceptance incomplete: no executed refinement after structural validation")
        return 1
    print(
        f"Executed refinement cycles: {refinement['attempt_count']}; "
        f"stop_reason={refinement.get('stop_reason')}"
    )
    print(f"Acceptance passed: report={report}; run_id={run_id}; database={database}")
    print("This verifies plumbing and report acceptance; it is not a model-quality evaluation.")
    return 0
