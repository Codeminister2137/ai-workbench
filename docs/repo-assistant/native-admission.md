# Native coding compatibility and input admission

ADR-041's offline compatibility/admission slice is implemented. The CLI foundation
remains **INCOMPLETE**; shared mutation approvals, IDE connectivity and live
acceptance remain separate work.

Automatic native coding selection excludes Ollama models without positive built-in
tool-call evidence. Initially this retains GPT-OSS. Explicit `--model` and
`--route-id` constraints are preserved; an incompatible choice is refused rather
than replaced. Existing privacy, quality, latency and cost selection still applies.
Native delegated coding uses the same eligibility rule. Research selection and its
separate review/tokenizer contracts are unchanged.

The built-in receipts in `ai_provider.native_admission` record model name, manifest
digest, Ollama version, native request-contract revision and observed tool support.
They summarize the 2026-10-04 paired tool probes and inventory, preserved locally in
`artifacts/cli-foundation-window-20261004/native-prompt-eval*/` and
`artifacts/cli-contract-window-20261004/ollama-inventory.json`. GPT-OSS called actual
tools with 19/20 strict effect checks per prompt; one check missed a newline.
Qwen2.5-Coder returned textual requests without actual tools. These are bounded
compatibility observations, not a general quality ranking or all-tool acceptance.

Before **every** native Ollama coding turn, read-only metadata checks compare the
current manifest digest and runtime version. Missing or changed identity invalidates
both positive and negative receipts. Unknown models refuse without a metadata probe.
No inference, downloads or runtime startup is performed by the evidence checker.
When adapter/tool-loop semantics change, bump `NATIVE_CONTRACT_VERSION`; receipt
revisions remain pinned until new bounded acceptance justifies updating them.
Offline readiness applies static eligibility without querying runtime metadata;
it does not prove the receipt is current or that a route is execution-ready.

The coding client checks the complete request on each turn: system/user instructions,
selected skills, tool schemas, tool arguments and accumulated history. It never
trims these to make the request fit. Capacity comes from existing model-catalog
limits. For Ollama, the selected resource profile or declared runtime default is
capped by the model window and sent explicitly as `num_ctx`. Unknown local runtime
capacity refuses; an unknown hosted capacity is reported as unknown.

Admission uses the existing research convention of serialized UTF-8 bytes divided
by two, rounded up, plus a 256-token framing reserve. Output defaults to one quarter
of context, capped at 8192 tokens, and is sent as the explicit generation limit.
An existing explicit request output limit is respected and reserved. Overflow
refuses before the next inference call; earlier effects and complete loop receipts
remain available for reconciliation.

Diagnostics label this `estimated_utf8` and `verified_token_count=false`. This
heuristic can reject inputs an exact tokenizer would fit and cannot prove actual
native capacity. It must not be reported as a verified token count. The verified
research-review counter supports specific tool-free framing only; it is deliberately
not reused for coding tools/history. Exact tool-bearing counting remains deferred.

## Deferred bounded live checks

Wait for an owner-selected compute window. Do not insert these cases into the
research-only scheduler as arbitrary jobs:

- Inspect installed version/digest and confirm stale evidence refuses with zero
  inference. Record versions and contract revision.
- Run a short GPT-OSS inspect/edit/test/diff fixture under explicit permissions and
  sufficient context. Record actual tool/effect receipts and generation limits.
- Check explicit incompatible-model refusal with no substitution or inference.
- Run a complete-instruction request and a growing-history overflow fixture. Record
  the estimated admission diagnostic separately from provider-reported usage.

These checks establish bounded compatibility/admission behavior, not model quality
improvement, cross-agent parity or exact tokenizer verification.

The fixed D3 GPT-OSS fixture passed on 2026-10-05 in the owner-selected compute
window with real read/edit effects and host validation. It emitted three complete
estimated admission records separately from provider-reported usage. Runtime,
worker and validators were cleaned up and listener absence was verified. This
does not complete growing-history live overflow or exact tool-bearing counting.
