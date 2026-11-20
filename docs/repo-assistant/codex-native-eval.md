# Native Codex capability worker

Owner decision `2c1555fd784348019af83b9fc2ffc45b`, 2026-11-20:
extend the existing worker. The owner's accompanying note permits preparing
the bounded grant without asking again and favors headroom over brittle
per-call consumption estimates. This does not remove observed-stop budgeting.

`ai_provider.capability_eval` now accepts exactly one explicit `codex_cli`
OpenAI subscription route with `--allow-hosted`. The existing foreground
scheduler already forwards that flag from its persisted allowance acknowledgement.
No service or scheduler schema change is needed.

The native branch uses the existing external-agent runner, read-only sandbox,
ChatGPT-only login selection, OpenAI provider, ephemeral session and a separate
temporary working directory. It passes a fixed synthetic prompt and the native
`--output-schema` flag, grading an exact integer object. Tools and streaming
remain unmeasured; no quality grade or catalog capability is changed.

Bounds: one CLI invocation, 180 seconds, no worker retries/fallback. This bounds
the invocation, not the native client's internal transport requests or output
tokens. Native reasoning settings remain inherited. Before and after the call,
both primary and secondary allowance readings must be available, no older than
60 seconds, unexhausted and in the same cycle. Missing, duplicate, invalid or
changed windows stop the worker. A consumption delta of 10 percentage points
or more stops after the call; overshoot is accepted, rather than forecasting a
call's consumption. The reset snapshot itself is never an inference grant.

An exclusive `<output>.native` directory retains admission, schema, final answer,
usage when reported, and a receipt including pre/postflight and failure phase.
Existing directories and output files refuse reuse. Raw CLI streams are not
persisted by this worker. Unexpected tool/command/web/file events invalidate
the result; read-only native sandboxing is not a general host-read isolation
guarantee. A separate working directory avoids inheriting this repository's
project instructions; native user configuration can still apply.

Validation for run `bf4bb70fecf34e93984fcf9ae63f8f44`: deterministic native,
capability, allowance, scheduler and external-runner tests; focused Ruff,
formatting and Pyright. The live metadata-only allowance read is private runtime
evidence under `.tmp/codex-reset-bf4bb70fecf3/allowance.json`. No native model
probe was launched during this implementation. Live reset evaluation remains
with source `0e579697` / follow-up `723faa04`; the old deferred trial is preserved.

Official OpenAI documentation checked 2026-11-20:
[non-interactive output schema](https://learn.chatgpt.com/docs/non-interactive-mode),
[configuration sample](https://learn.chatgpt.com/docs/config-file/config-sample).
These document the native flags/configuration, not this account's live headroom
or successful runtime compatibility.
