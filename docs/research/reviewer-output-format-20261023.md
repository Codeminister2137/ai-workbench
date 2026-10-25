# format_gate research note — how others handle structured output from LLM reviewers

**Prepared:** 2026-10-23 (unattended window), public web only.
**Purpose:** inform the choice behind roadmap item 1 in
`docs/repo-assistant/development-roadmap.md` ("Stop the hard gate on an exact
6-heading report"). Research only — no code, dependency or protocol change here.

## Question

When a reviewer model is asked for a fixed structure (our case: six headings,
`VERDICT`/`SCORE`/`ISSUES`/...), what do other systems do when the returned text
does not match — and how do they keep a formatting problem from being recorded as
a quality judgement about the reviewed work?

## Four established approaches

### 1. Constrained decoding / schema-enforced generation

The provider (or inference server) masks invalid tokens at sampling time, so the
output cannot violate the schema.

- OpenAI Structured Outputs converts the JSON Schema to a grammar and constrains
  sampling; OpenAI reports 100% schema adherence on its complex-schema eval for a
  supported model, versus <40% for prompt-only on an older one. It is a strict
  mode with a documented JSON-Schema subset (root must be an object, no root
  `anyOf`, every field `required`, `additionalProperties: false`) and model
  support starts at `gpt-4o-2024-08-06`/`gpt-4o-mini-2024-07-18`.
- Anthropic exposes the same idea through tool `input_schema` enforcement;
  Gemini through `responseSchema`/`responseJsonSchema`; Pydantic AI and Zod
  generate the schema from typed models.
- Open-weight stacks: Outlines, Guidance, XGrammar, llguidance, llama.cpp GBNF,
  vLLM/SGLang guided generation.

**Guarantee:** syntax/schema validity. **Not guaranteed:** semantic correctness.
A 2026 arXiv evaluation of schema-constrained ordering agents found schema
validity at 100% for several models while *semantic* success ranged from 2% to
81%; Gemma-2-2B emitted 100% schema-valid objects with 2% semantic success and
41.7% unsafe acceptance. Constrained output can also be a refusal instead of a
verdict, which is a distinct terminal state.

**Relevance to us:** our reviewer prompt is a plain-text heading protocol, not
JSON, and the reviewer runs through a route catalog that includes local Ollama
models and several gateways whose structured-output support is uneven. Adopting
constrained decoding would mean a per-adapter capability and a new review
protocol (JSON schema), i.e. a contract change, before we know we need it.

### 2. Tolerant / partial parsing with named repairs

Libraries such as `json_repair`, `partialjson` and single-file tolerant parsers
do a strict parse first and only then repair (fences, prose wrappers, trailing
commas, single quotes, truncation). Two practices stand out:

- **Repairs are reported, not hidden.** One tool names all 24 failure modes it
  can repair, records the offset of each repair, and states that "output that
  does not parse is never presented as repaired."
- **Order matters:** strict pass first, repair only as a fallback; a repair that
  produces nothing must stay a failure, never an empty success.

**Relevance to us:** this is the direct analogue of
`parse_response_scrutiny_report_lenient`, which recovers what it can and records
`format_issues`. Our choice to keep the strict parser available and treat
unreadable reports as a *review failure* matches the "honest states" practice.

### 3. Bounded retry-on-parse/validation-failure

Instructor (`max_retries`, `retry_if_parsing_fails=True`) and Pydantic AI
(`ModelRetry`, per-output retry budget) re-ask the model with the validation
error as feedback, then raise a distinct exception when the budget is exhausted.
`validation-loop` layers custom business validation on the same pattern.

**Common shape:** bounded attempts, the *error text* fed back, a terminal error
that is not silently converted into a content verdict. Pydantic AI's docs are
explicit that retrying cannot fix a model that is "not intelligent enough", so
the retry budget is a mitigation, not a correctness guarantee.

**Relevance to us:** we already bound repair attempts (`--max-repair-cycles`, two
no-progress stops). A single re-ask for an unreadable *report* is a different,
smaller decision: it would trade latency/tokens for fewer "review failed"
outcomes, and it must not be confused with repairing the candidate.

### 4. Parse failure as a separate labelled outcome

This is the pattern our ADR-066 change implements, and the public record shows
why it matters:

- **NVIDIA NeMo Gym (LLM-as-judge):** "A judge that fails to answer is not a model
  that answered wrongly." Judge *call* failures are raised as `JudgeError` and
  excluded from aggregates; a judge that answered but whose verdict is
  unparseable is mapped to a configured `reward_if_unclear` rather than to a
  negative score.
- **ARES issue #89 (2026-09-25):** an unparseable judge reply (empty, whitespace,
  punctuation, lowercase `[[yes]]`, prose) was scored as a genuine `[[No]]` and
  averaged into results; the proposed fix is to return `None`/`NaN` and drop the
  row from aggregates. The report also notes case-sensitivity flipped an
  affirmative into a negative.

**Relevance to us:** this is exactly the conflation ADR-066 removed — a report we
could not read became a blocking outcome, as if the reviewer had judged the work.
Our `format_issues` + `stage_status="failed"` split is the same separation, and
the ARES case is a useful published example of the failure mode.

## What this implies for our design

1. **Keep the lenient parser and the advisory verdict.** It matches the
   established "tolerant parse + labelled limitation" practice and needs no new
   dependency or provider capability.
2. **Never map unparseable output onto a content verdict.** Already enforced;
   the external evidence (NeMo Gym, ARES) is a good citation for why.
3. **Constrain generation only behind an owned contract.** Constrained decoding
   is strong when we control the protocol (JSON schema, one provider). Our
   reviewer is purpose-built plain text over heterogeneous routes, so switching
   protocols to buy syntax validity would not buy semantic validity and would add
   per-route capability handling.
4. **A bounded re-ask is the cheaper next lever, if signal justifies it.** If
   "review failed" remains common after the lenient parser, one re-ask with the
   parse issues attached is well-precedented (Instructor/Pydantic AI) and fits
   inside the existing review stage rather than adding a protocol change.
5. **Record the repair/limitation, not just the verdict.** Our `format_issues`
   list and the new closeout rendering on a `pass` follow the "named repairs"
   practice: the reader sees that part of the review was unreadable.

## Recommendation (informational; owner decides)

Do not adopt constrained decoding or a new structured-output dependency for the
scrutiny report now. Keep the lenient parser plus labelled review failure, and
treat "one bounded re-ask on an unreadable report" as the next candidate only if
observed review-failure rates justify the extra call. This preserves the
provider-neutral boundary and avoids a public review-protocol change on weak
signal.

## Sources (observed 2026-10-23)

| Source | URL | Used for |
| --- | --- | --- |
| OpenAI, Structured Outputs guide | <https://platform.openai.com/docs/guides/structured-outputs/json-mode> | strict schema mode, JSON-mode vs schema, model support |
| OpenAI, Structured Outputs announcement | <https://openai.com/index/introducing-structured-outputs-in-the-api> | constrained decoding via CFG, 100% vs <40% eval |
| devtoollab, LLM Structured Outputs (2026) | <https://devtoollab.com/blog/llm-structured-outputs-guide> | provider surface comparison; Anthropic Feb 2026 support |
| hexdocs LLM, Structured output | <https://hexdocs.pm/llm/structured_output.md> | `response.parsed` is nil on parse failure; fallback handling |
| arXiv 2607.18261, semantic reliability of schema-constrained agents | <https://arxiv.org/pdf/2607.18261> | schema validity ≠ semantic success; unsafe acceptance rates |
| Pydantic AI, Output concepts | <https://pydantic.dev/docs/ai/core-concepts/output/> | `ModelRetry`, output retry budget |
| Instructor, retry mechanisms | <https://github.com/567-labs/instructor/blob/main/docs/learning/validation/retry_mechanisms.md> | `max_retries`, `retry_if_parsing_fails`, terminal exception |
| json_repair | <https://github.com/mangiucugna/json_repair> | strict-first tolerant parse, empty result on hopeless input |
| 0xelitesystem/llm-json-repair | <https://github.com/0xelitesystem/llm-json-repair> | named failure modes; never present unparsed output as repaired |
| NVIDIA NeMo Gym, LLM-as-judge | <https://docs.nvidia.com/nemo/gym/build-verifiers/verification-patterns/llm-as-judge> | judge call failure vs unparseable verdict; `reward_if_unclear` |
| ARES issue #89 | <https://github.com/stanford-futuredata/ARES/issues/89> | published example of parse failure scored as a negative verdict |

## Limits of this note

- Public documentation and issue trackers only; no live model was run and no
  provider structured-output behaviour was tested against our routes.
- Some pages are vendor marketing and repeat vendor benchmark numbers
  uncritically; the semantic-reliability result is the main independent check on
  "schema-valid therefore good".
- This note does not change the review protocol, the parser or any band.
