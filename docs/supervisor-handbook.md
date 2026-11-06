# Supervisor handbook (reference only)

> This file is long-form guidance for people and reviewers. It is
> **never sent to the model**: the prompt path
> (`ai_agent.supervisor_prompt`) sends only the slim core instructions
> plus per-delegation state (receipts so far, approval policy surface,
> paths involved). Keep handbook-only detail here; do not inline it
> into the prompt assembly.

## Role

The Workbench supervisor answers inside the owner's local dashboard on
their Windows 11 PC. It is concise and concrete, and it never claims
effects it did not observe: no sent mail, no restarted services, no
edited files.

## Chat relay mechanics (reference-only detail)

Each dashboard chat turn runs through the messenger relay
(`ai_agent.messenger.run_messenger_turn`) with the read-only inspection
profile: read, list, search, git status. Writes, execution, delegation,
and mail are out of reach twice over (registry profile plus the
read-only permission policy). Tool receipts from the turn are appended
to the transcript visibly ("Checked with tools: ...") so the next turn
sees them as history, not as prompt preamble.

## Approval and run lifecycle (reference-only detail)

Development work happens only through agent runs the owner queues with
the Request-run button and approves in the inbox. A chat turn never
executes a run directly: `DashboardChat.request_run` writes the inbox
decision first (fail-closed: a full inbox refuses without queueing),
then the queued run. The run drain (`ai_agent.supervisor_drain`)
executes a queued run only when its linked inbox record carries a
recorded `Approve` answer; open, rejected, or missing approvals leave
the run parked.

Chat-requested runs inherit the dashboard `chat_fanout_policy`
(default `restricted`: child spawns refused). The prompt carries only
the effective policy surface for the turn, never this whole section.

## Standing limits (reference-only detail)

- Mail delivery is not configured: say mail is unavailable until the
  owner configures SMTP credentials. Never claim an email was or will
  be sent.
- No live view of services (Ollama, dashboard, scheduled tasks): never
  assert their state. Send the owner to the dashboard Home status view,
  or quote only the last error already in the transcript.
- This PC runs Windows: never mention Linux paths, daemons, or
  commands.

## Credentials (reference-only detail)

Prompt content must never include credentials. Assembly refuses
fail-closed (`ProviderError`, same as the agent loop) when a known
credential value appears in the assembled prompt, and credential file
paths (`.env`, key files, auth stores) are refused as delegation paths.
Refusal diagnostics never echo the secret.
