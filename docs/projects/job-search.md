# Job search automation

CV variants, offer matching with personalized scoring, and application
tracking. Reuse-first: adopts the Openings service instead of rebuilding it.

Key areas: `apps/job_search`, `data/profiles/job-preferences.toml`.

Current state: Openings personalized with Q7 profile; execution-plan
M2–M4 open; vendor sourcing blocked on accounts. See the Roadmap.

D3 resolved (owner A, 2026-11-18): M3 review will live in the existing
Workbench dashboard, rather than a richer CLI. The page is still
**INCOMPLETE**. Next: implement vacancy + match + material diffs + warnings
in one dashboard review screen, with per-item edit/approve/reject using
the existing application approval gate. Completion requires a reachable
page, a sent-material snapshot and passing unapproved/changed-material
delivery guards. See [ADR-091](../decisions/ADR-091-job-search-dashboard-review.md).
