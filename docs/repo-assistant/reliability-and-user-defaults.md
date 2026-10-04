# Reliability and user defaults

## Implemented recovery

Recognized usage exhaustion and model overload use compatible, same-tier fallback.
Quality policy belongs to private configuration and can be overridden per run:

```toml
[fallback]
enabled = true
quality_policy = "preserve_quality"
```

`preserve_quality` requires the original declared catalog grade as well as the
task minimum. `task_minimum` explicitly permits a weaker model meeting task needs.
Missing grade evidence or missing capabilities refuses continuation. If nothing
suitable remains, local edits survive and a metadata handoff is saved. Remaining
usage/credits are unknown unless reliably reported; preflight is not a balance check.

## Other interruption classes

| Failure | Current handling and appropriate next work |
| --- | --- |
| Connection loss, HTTP 5xx, temporary provider outage | Provider adapters normalize errors; research has bounded request retries. Investigate safe compatible route fallback separately from account exhaustion. |
| Timeout or broken stream | Retain receipts and inspect uncertain effects before restarting; do not rerun the entire coding task blindly. |
| Expired login, missing entitlement or credentials | Preflight excludes unverified routes; sign-in/configuration needs correction. Never infer permission or credits from executable availability. |
| Context/output budget failure | Refuse before inference where sizing can detect it; preserve instructions, expose budget diagnostics and resume from saved reports. Tool-capable exact token counts remain incomplete. |
| Tool permission, malformed request, unavailable tool | Report the specific boundary. Do not grant broader access or pretend a textual tool request executed. |
| Failed validation or no-progress repair | Existing repair bounds/progress checks apply; unchanged failed work is not success. |
| IDE/runtime/process crash, reboot or disk-write failure | Preserve existing durable receipts. Session restart requires effect reconciliation; old handles/approvals are not restored. Unwritten handoffs must be reported as failures. |

Only the overload/usage policy is expanded here. Generic retries, automatic login,
automatic mutation replay, background resume and new services are not enabled.

## Accepted execution defaults

Owner approved task quality, context/instruction limits, request/validation
timeouts and repair caps in the existing private `[defaults]` section. The
example config documents shipped values, which remain unchanged. CLI flags
always win, including abbreviated options. Invalid types, non-finite/non-positive
timeouts and out-of-range budgets fail before routing. Required instructions
refuse overflow rather than being truncated. `context_budget_chars = 0` removes
the optional context cap; `max_repair_cycles = -1` removes the cycle cap while
retaining the time budget. An explicitly configured request timeout wins over
away-mode automatic request sizing; omit it to retain automatic sizing.
Scheduler deadline admission is unchanged.

## Privacy and approval defaults

Private `[defaults]` now accepts `privacy` and `approval_policy`, validated against
the existing CLI enums. Shipped values remain `local_only` and `interactive`.
Explicit CLI flags win, including abbreviated and equals forms and values equal
to shipped defaults. No broader values were selected for the owner's private file.

Coding sessions record the effective configured/CLI privacy before execution and
refuse a resume with different privacy/cost boundaries. Shared inspection still
forces `read_only`; configuration cannot broaden native client restrictions.
The research scheduler and PowerShell research launcher continue to supply their
existing explicit privacy/approval flags, which take precedence over private defaults.
The [next-session brief](next-session-decisions.md) retains the D1 approval and
separate search-operator and acceptance-job design boundaries.

## Remaining configuration boundaries

| Setting | Recommendation and reason |
| --- | --- |
| IDE endpoint and search operator | Use explicit local config once connection/operator is selected; never discover a service and silently send data to it. |
| Persistent quota balances, reset guesses, cross-tier fallback | Defer: account-specific reliable evidence is needed; local guesses cannot guarantee allowance or spending limits. |

Avoid making every internal retry, heuristic, buffer or tool setting configurable.
Add a default when it solves a repeated user choice; retain typed validation and
clear CLI precedence.
