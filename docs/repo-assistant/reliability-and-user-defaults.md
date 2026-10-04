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

## Further configuration recommendations — not yet approved

The current user config has a cost ceiling, fallback enablement and quality policy.
Most execution controls already exist as CLI flags. Prefer exposing selected flags
as defaults through that same config rather than adding another settings system.

| Setting | Recommendation and reason |
| --- | --- |
| Default task quality | Add next: common personal preference, with CLI override; keep separate from fallback continuity quality. |
| Optional context and instruction limits | Add next: useful workstation/task preferences; instructions must still refuse overflow rather than truncate. |
| Request/validation timeouts and repair cap | Add next after validating combinations: useful bounded execution preferences; must not weaken scheduler deadline admission. |
| Privacy default | Worth adding only after explicit selection: it determines which data may leave the PC. Keep current local-only default meanwhile. |
| Approval preset | Worth adding only after explicit selection: it changes command/write authority. Preserve current interactive behavior meanwhile. |
| IDE endpoint and search operator | Use explicit local config once connection/operator is selected; never discover a service and silently send data to it. |
| Persistent quota balances, reset guesses, cross-tier fallback | Defer: account-specific reliable evidence is needed; local guesses cannot guarantee allowance or spending limits. |

Avoid making every internal retry, heuristic, buffer or tool setting configurable.
Add a default when it solves a repeated user choice; retain typed validation and
clear CLI precedence. No further defaults were implemented in this slice.
