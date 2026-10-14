# ADR-057 - Free Gemini CLI And OpenRouter Access Direction

**Status:** Accepted direction; Gemini individual-access pilot blocked by service retirement

**Date:** 2026-10-13

## Context

The owner's Copilot and Kiro allowances are exhausted. Antigravity is already
connected for model discovery, but remaining quota and shared-tool execution are
not established. Requesty's existing free route has live zero-price evidence;
its quality remains provisional and its daily remaining allowance is unknown.

The owner wants another free source before investing in additional credits.
Sources must remain distinct by product, authentication and billing provenance,
even when the vendor or model family is shared.

## Owner Decision And Rationale

- Approve Gemini CLI integration, using the investigated free Google-account
  access direction. The owner described it as a good option and approved it.
- Request OpenRouter connection. Defer the $10 credit purchase until the owner
  explicitly chooses that investment; prepare free access first.
- Retain Requesty support for average users, including its existing paid paths.
  The owner's personal choice is not to deposit prepaid credits there now.
  That preference is not a prohibition on the product's Requesty integration.
- Record Antigravity as the owner's confirmed Free account. Connection checks
  do not require the no-hooks/no-workers isolation promised by an automatic
  quota collector. ADR-050's collector requirement remains unchanged.
- Defer Cerebras and Zed/Delta promotions as possible emergency sources. Revisit
  when distinctive capabilities or cost justify them; no trial activation was
  requested.

The owner explicitly prefers adding another free service before making the
OpenRouter deposit, even though the amount is acceptable as a likely later
investment. Temporary promotions are less useful for the owner's normal usage
than recurring free access or paying an already selected service.

## Alternatives Considered

Gemini CLI offers a native terminal client and published individual-account
allowance, but requires runtime/client setup, native authentication and a new
adapter. OpenRouter offers API access to multiple free models and a higher daily
quota after a credit purchase, but free capacity and model availability vary.
Neither is established as equivalent coding quality by its published allowance.

Groq remains a candidate for small tasks. Current published token limits appear
tight for the recorded coding reviews; deferring full-session use is an engineering
recommendation, not a new owner decision. OpenCode Console remains research-only:
temporary models, account funding requirements and model-specific data policies
need further assessment before adoption.

## Implementation Boundaries

Reuse existing provider adapters, orchestration and shared-tool/process contracts.
Do not identify Gemini CLI as Antigravity or API-key billing, or identify OpenRouter
as OpenAI merely because their HTTP protocols are compatible. Preserve strict
quality admission, required instructions/history, scoped approvals and cleanup.

Keep new routes opt-in until their actual client/model/tool behavior is verified.
No global default, quality promotion, automatic purchase or paid fallback is
approved by this direction. Native client sign-in remains owner-controlled;
private subscription credentials must not be extracted into unofficial APIs.

The owner subsequently selected project-scoped environment changes to ease setup
on another machine. Python dependencies stay in the existing `uv` workspace
environment; supported portable external runtimes/clients use the ignored `.tools/`
convention with explicit versions and paths. Node is a separate runtime, not a
Python virtual-environment dependency. Node/npm and Gemini CLI were not found on
PATH or in inspected common locations. No runtime installation or live inference
has occurred under this decision. See [installation guidance](../installation.md).

Implementation update, 2026-10-14: the selected project-local Node/Gemini pair
is installed and version/help verified. The experimental adapter adds distinct
access/product/billing provenance and a separate opt-in catalog, reusing shared
MCP/approval/process/history contracts. Installed-client offline MCP read/edit
and owned cleanup passed. Gemini rejects user-owned Windows system settings;
the adapter instead creates project settings exclusively, refuses existing files,
verifies effective settings before inference, and removes only its unchanged
file. It does not alter administrator ACLs or copy credentials. Native tools,
hooks, extensions, updates and prompt telemetry are disabled. Owner sign-in and
separately scoped live quality acceptance remain pending; no default or quality
promotion follows from offline checks. The earlier paragraph records setup state
at the decision, rather than today's implementation status.

The owner also explicitly deferred OpenCode Console. Wiring additional full agents
is a possible improvement direction, not approval to install or integrate one now.

Model/API calls transmit selected context and tool results to the chosen service.
Before live acceptance, verify the selected route's account, cost and data contract.
Research approval alone does not authorize confidential-data transmission to a
different free provider.

## Validation And Sources

Access correction, 2026-10-14: the owner approved the prepared Gemini-only pilot
and confirmed readiness, but native Google sign-in returned an unsupported-client
error directing individual accounts to Antigravity. Investigation verified the
official 2026-06-18 retirement announcement for free/Pro/Ultra individual access.
The earlier research missed this announcement; the advertised individual quota
was not current usable access. Offline compatibility does not restore entitlement.
The pilot did not start and its approval does not authorize another product or
billing route. The adapter refuses the retired free route even with cached auth.
Preserve the implementation/fixtures and installation evidence pending the
owner's next-source decision. No migration or replacement decision is recorded.

Subsequent owner decision, 2026-10-14: after the retirement was established,
the owner approved the recommendation to prioritize OpenRouter free-first as an
independent source. The deposit remains deferred. This selects the already
requested API integration, not Antigravity migration or a transfer of the unused
Gemini inference grant. Existing Gemini evidence and all uncommitted work remain.

OpenRouter implementation uses the shared Chat Completions translator and host
tool loop behind a distinct free-only client, with `openrouter_free` provenance.
Every model call rechecks the exact named `:free` variant, all advertised prices,
tool support and the authenticated daily free-request counter. Missing or
inconsistent observations refuse inference. Provider routing requires parameters,
denies data collection and caps prices at zero; there is no gateway model router,
paid plugin or paid retry. These conservative guards may leave no eligible
endpoint. No default catalog or quality promotion follows. The example Qwen
candidate's public endpoint listing was empty at inspection; usable account
capacity and actual coding quality remain unverified.

Read-only metadata checks are separate from inference. The initial live task must
have a fresh input/path/time/turn allowance, full instructions/history, original
tests, substantive review and independently verified effects/cleanup. No key or
private raw account response belongs in tracked evidence. No deposit is required
by this implementation and none is authorized automatically.

- [OpenRouter account limits and free-request observations](https://openrouter.ai/docs/api_reference/limits)
- [OpenRouter provider price/parameter/data-policy filters](https://openrouter.ai/docs/guides/routing/provider-selection)
- [Candidate public endpoint listing](https://openrouter.ai/api/v1/models/qwen/qwen3.8-27b:free/endpoints)

Final contract check found a material documentation conflict: the current pricing
table excludes data-policy routing from Free, while provider-logging/routing docs
describe per-request filters without qualifying the plan. The adapter refuses
Free/unknown-tier key metadata before inference; offline success fixtures represent
an already non-free-tier account requesting only free models. This is a conservative
implementation refusal, not a new owner decision to fund an account or allow
data collection. Read-only key/price checks can continue; a Free-plan pilot needs
verified filter entitlement or an explicit owner-approved privacy-policy change.
No policy weakening or deposit is implemented.

- [OpenRouter plan feature table](https://openrouter.ai/pricing/)
- [Provider logging and free-model account settings](https://openrouter.ai/docs/guides/privacy/provider-logging)

Evidence-precedence clarification, 2026-10-14: the owner authorized current account
model discovery and explicitly stated that current official-site/API data should
override older research and the potentially stale local catalog. The authorized
metadata-only check succeeded; current public free variants include Gemma4 31B,
Inkling/Inkling Small and North Mini Code. The earlier Qwen candidate is absent
and its example now explicitly records that obsolete observation. Failed receipts
and route history are preserved; no model substitution or inference followed.

The account-filtered model endpoint is callable on the observed Free account.
This contradicts treating Free status as absence of all model access, but does
not by itself establish per-request privacy-filter enforcement. The temporary
local guard is an engineering refusal pending that contract decision, not an
OpenRouter access-denied response. Actual account observations remain in ignored
receipts/current handoff. No paid migration is inferred from local assumptions.

Subsequent owner approval, 2026-10-14: approve the proposed pilot-only public/
synthetic exception, accepting possible provider retention/training for the toy
fixture while Free-plan filtering remains unresolved. This obtains initial
coding/tool evidence without a deposit using non-confidential inputs. Private
project code, secrets and private plans remain excluded. This is not a general
privacy-policy change or a live inference grant. Production Free-tier refusal
remains unchanged; the exception is confined to a local acceptance harness.

The bounded candidate is Gemma4 31B through its exact OpenRouter :free variant,
keeping the already-declared Requesty model family while testing independent
gateway/allowance behavior. The runner reuses coding-chat, shared tools, full
instructions/history, preserved original tests, host inspection/oracles, frozen
model review and owned cleanup. A separate exact live grant/readiness is required
after offline validation; Gemini approval and metadata readiness do not transfer.
No paired comparison, deposit, paid fallback, quality promotion or default change.

Live acceptance observation, 2026-10-14: the owner subsequently granted the exact
attended Gemma4-free public/synthetic pilot. A local hash-casing preparation bug
was repaired and checked offline before launch. The trial then stopped on the
first completion's OpenRouter error, with no model output or tool effects and
verified cleanup. Error cause, usage and cost remain unknown; no model-quality
acceptance or route promotion follows. Preserve the consumed grant's receipts;
any later trial requires a fresh bounded grant. Production privacy admission is
unchanged. The local evidence entry point is CURRENT_CONTEXT.md.

- [Official individual-account retirement announcement](https://github.com/google-gemini/gemini-cli/discussions/28017)
- [Google consumer-account deprecation](https://developers.google.com/gemini-code-assist/docs/deprecations/code-assist-individuals)

Connection, quota, software correctness and coding-quality acceptance are separate
checks. Start with offline contracts and one bounded synthetic acceptance, retaining
original tests, inspecting host results, requiring substantive model review and
verifying owned cleanup. A connection or one fixture does not certify broad parity.

- [Gemini CLI quotas](https://geminicli.com/docs/resources/quota-and-pricing/)
- [Gemini CLI authentication](https://geminicli.com/docs/get-started/authentication/)
- [OpenRouter free-model limits](https://openrouter.ai/blog/tutorials/how-to-get-the-lowest-cost-llm-inference-on-openrouter/)
- [Antigravity plans](https://antigravity.google/docs/plans/)
- [Requesty free access](https://www.requesty.ai/free-models)

Sources checked 2026-10-13; offers and actual account limits can change.
