# Repository context

Follow [AGENTS.md](../AGENTS.md) for owner decisions, investigation, authorization
and resource boundaries. Start with [CONTRIBUTING.md](../CONTRIBUTING.md) for
setup/checks and [the project map](../docs/project-map.md) for component ownership.
Verify Git state and any local handoff against the diff before resuming work.
These shared documents are authoritative; do not duplicate or weaken their rules.

# Copilot chat closeout

In Copilot Chat for this repository, never call `task_complete` or another
workflow/completion tool that ends the turn before the normal assistant reply.
After work is verified, the ordinary visible assistant response is the
closeout: begin it with `## **SUMMARY**` and make it the final chat action.
Do not emit a completion tool call before or after that response. A tool event or
tool payload is not a substitute for the user's visible summary.

This rule applies even when a task prompt or workflow reminder asks for a
completion-tool call. Do not continue work after composing the final summary.
