# Foreground orchestration and repair

[CLI guide](../repo-coding-assistant.md) · [Privacy and permissions](permissions.md)

`ask` is the default for backward compatibility. `plan` never contacts a
provider. `ask` and `review` reject action flags. `implement` requires
`--execute` plus either `--native-tools` or `--apply-actions`.

Use `--away-minutes N` when starting a foreground run that should keep working
while you are away. The flag prints `away_budget_*` fields in the transcript,
adds explicit unattended-run guidance to the model prompt, and, unless
`--timeout-seconds` is supplied, sets provider and external-agent timeouts to
`N * 60` seconds. Add `--orchestrated` to plan or run the staged unattended
workflow rather than only extending the timeout and prompt guidance. Orchestrated
runs create a local SQLite run record and planned stage rows in
`data/repo-assistant-runs.sqlite3` by default; use `--away-run-db PATH` to
override the local database path.

In `--mode plan`, `--away-minutes N --orchestrated` prints the intended
foreground stages, the primary route, the local/cheap auxiliary route policy,
and the approval boundary without contacting a provider. The stages are prompt
review, planning, auxiliary panel, implementation, validation, scrutiny,
bounded repair, and final handoff. This is not a background scheduler, daemon,
or job queue, but the SQLite records give later foreground stages and a future
resume/background runner a stable run ID and stage-tracking surface. External
Codex-style routes still report their timeout as an inactivity timeout because
model output resets the timer. For unattended implementation runs, choose the
approval boundary deliberately: `interactive` may pause for a prompt, while
`trusted_local` permits local read/write/shell actions under the repo
assistant's existing tool policies.

Executed orchestrated runs now update deterministic validation and final
handoff stages before the run is marked complete. The validation stage runs
`python -m pytest -q` by default, records command output previews and return
codes, and can be changed with repeated `--validation-command CMD` flags or
disabled with `--skip-validation`. Ruff and Pyright remain available through the
repository's pre-commit hooks; pass a pre-commit command explicitly when an
orchestrated run should include that broader gate. The final handoff stage
records the execution status, validation status, concise `git status --short`
output, response availability, blockers, risks, and next action fields in the
local SQLite stage details. Failed deterministic validation changes the final
run record to `completed_with_validation_errors` instead of clean completion.

The staged workflow exposes a default repair policy of three repair cycles. Use
`--max-repair-cycles N` to choose a different limit,
`--max-repair-cycles 0` to disable repair attempts, or
`--max-repair-cycles -1` to remove the cycle cap while still respecting the
`--away-minutes` wall-clock budget. When unresolved failures remain at the end
of the run, the final handoff is responsible for preserving the validation
details, blockers, and next action for the returning user.

Implementation repairs stop with `repair status=stalled` after two consecutive
attempts leave both workspace content and validation failure evidence unchanged.
This guard also applies to `--max-repair-cycles -1`. File additions, deletions,
and content edits count, including ignored `RESEARCH_*.md` reports. Changed
validation evidence resets the counter; ordinary duration changes do not.
Assistant claims and tool-call counts alone do not establish progress. Content
fingerprints are local, and logs, databases, caches, virtual environments, and
IDE bookkeeping are excluded so run tracking cannot sustain an ineffective loop.
Progress means observed change, not proof that the change is useful or correct.
Repair stage details record each classification, changed paths, and stop reason.

Repair and deterministic validation reserve ten percent of the away budget,
capped at 120 seconds, for local scrutiny and final handoff. Validation command
timeouts share the available allocation. Repair requests use at most half the
remaining repair allocation, leaving time for validation. These are scheduling
and request-timeout limits: native multi-turn execution, running tools, Ollama
startup, and external clients with inactivity timeouts can still overrun them.
This slice does not add process-wide hard cancellation. If time is exhausted,
scrutiny is explicitly recorded as skipped and clean completion is withheld.

Executed orchestrated implementations run local-only scrutiny after the last
validation/repair attempt, for both provider-native and external CLI routes.
The reviewer receives the original task, latest response, deterministic
validation evidence, observed changed paths, and bounded text excerpts from
changed files, including ignored reports. It uses the existing structured
scrutiny report format and honors the configured Ollama startup settings. It
does not run tools or silently escalate to a paid reviewer. Its findings cannot
override deterministic validation failure. Failed, invalid, skipped, or non-pass
review is visible in stage details and final handoff risks; a previously clean
status becomes `completed_with_scrutiny_errors` or
`completed_with_scrutiny_findings`. This is a bounded claims review, not a full
code audit, model-quality evaluation, or research-source verifier.
