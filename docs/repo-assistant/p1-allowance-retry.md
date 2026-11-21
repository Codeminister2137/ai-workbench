# P1 allowance retry — 2026-11-21

Status: **COMPLETE for the single synthetic transport acceptance**.

Run `e36d7208c62b4b59b6400d411b44bc5b` used one Codex subscription
invocation and served one mailbox turn. The fresh trial budget was 24,576
tokens, with a 180-second call timeout. Reported usage was 15,740 input and
16 output tokens (15,756 total). Accounting is checked after return; this
budget is not a provider-side generation cap.

The Codex native result still reports cleanup as unknown. Acceptance instead
uses independently observed Docker teardown: compose down exited zero, then
`docker ps --all` filtered by the unique compose project label exited zero
with empty stdout. The receipt retains the exact command and observation time.
All six worker findings passed, including the relay response and mailbox cleanup.

Preflight and postflight allowance observations both showed primary usage 5%
and secondary usage 44%, with reset timestamps retained. These rounded account
observations do not measure this invocation's allowance cost.

Evidence remains local under
`.tmp/relay-hosted-accept/e36d7208c62b4b59b6400d411b44bc5b-prepared/receipt.json`;
the fresh driver is `.tmp/relay-hosted-accept/e36d7208-driver.py`.
The previous consumed trial was inspected, not replayed or regraded.

The probe now preserves the teardown listing and gates its final receipt on
successful teardown and an empty listing. Final printing/exit status were also
moved after teardown; that reporting adjustment was made after the live trial
and was checked locally, without another invocation.

This is transport evidence, not general coding quality or production acceptance.
It establishes project-container removal, not native process-tree cleanup or
a host-wide network audit.
