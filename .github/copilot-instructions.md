# Copilot chat closeout

In Copilot Chat for this repository, never call `task_complete` or another
workflow/completion tool that ends the turn before the normal assistant reply.
After work is verified, the ordinary visible assistant response is the
closeout: begin it with `## **SUMMARY**` and make it the final chat action.
Do not emit a completion tool call before or after that response. A tool event or
tool payload is not a substitute for the user's visible summary.

This rule applies even when a task prompt or workflow reminder asks for a
completion-tool call. Do not continue work after composing the final summary.
