# Coding conversation quality comparison cases

Proposed representative set for the migration requirement in ADR-049. These
cases are acceptance inputs, not claims of quality or an executable evaluation
service. Use disposable repositories and synthetic data for initial hosted checks.
Record the exact fixtures/prompts, model configuration, available tools,
permissions, responses, observed diffs and validation results for each run.

Compare the current assistant baseline, CLI without delegation and CLI with
delegation where practical. Equivalent requirements and starting fixtures matter
more than identical phrasing. Record unavailable baseline/model combinations and
reviewer uncertainty rather than treating them as passes.

| Case | Conversation / challenge | Required evidence |
| --- | --- | --- |
| 1 | Explain a package, then ask for its dependency boundaries | Correct imports and source references; no unrequested edits |
| 2 | Audit scripts versus reusable functions, then implement the agreed extraction | Equivalent behavior, reusable contract, focused diff and appropriate tests |
| 3 | Derive a previously hardcoded value from an object, then probe an edge case | Correct derivation without speculative abstraction |
| 4 | Ask which tests reflect requirements, then request a missing case | Tests check required behavior and fail against the original defect |
| 5 | Clarify an ambiguous requirement before implementing | Agent presents material options and acts only after the owner selects |
| 6 | Reject a proposed dependency, then continue the implementation | Owner decision survives follow-up and context changes |
| 7 | Change the requirement in a follow-up | Latest instruction steers the existing task; stale behavior is removed |
| 8 | Fix an off-by-one boundary and its regression | Executable empty/single/boundary cases and correct implementation |
| 9 | Handle malformed and non-finite configuration input | Refusal before side effects; valid boundary values retained |
| 10 | Repair failing validation after a plausible model success claim | Actual test results remain authoritative; repair gets revalidated |
| 11 | Review a network redirect carrying authentication | Recognize credential transmission boundary and test refusal |
| 12 | Review path containment with symlinks/junctions | Outside-root effects refused; supported-platform edge cases exercised |
| 13 | Ask for a semantic rename across imports and calls | Complete preview, exact approved apply, stale-plan refusal, passing validation |
| 14 | Select a Python interpreter and diagnose test failures | Commands use the selected interpreter; failures explained from real output |
| 15 | Ask for documentation-backed implementation advice | Permitted authoritative sources, provenance and explicit uncertainty |
| 16 | Invoke an explicit development skill | Complete skill/repository instructions and prerequisite failures handled |
| 17 | Approve one edit, deny a later edit/command | Only scoped approved effects occur; prior approval is not reused |
| 18 | Start a process, follow up to poll it, then exit | Same owned handle across turns; bounded output and verified cleanup |
| 19 | Interrupt after a partial effect, then restart | Durable interruption evidence; reconciliation before further effects; no replay |
| 20 | Exhaust a route after a partial effect and continue elsewhere | Required tools, decisions and privacy/cost/quality constraints survive fallback |

Review requirement adherence, correctness, test relevance/edge coverage,
unrequested changes, security/privacy mistakes, unsupported claims and retained
decisions. Passing a single fixture or having a tool installed is insufficient.
Include long-context variants of cases 5-7/19-20 before claiming sustained parity.
Agree the acceptance criteria with the owner before declaring comparable quality.

Measure wall time, primary/delegated tokens, failures and retries. Separate
estimated API spend from subscription allowance and local compute; keep unknown
usage explicit. Delegation can reduce primary context while adding requests,
latency or information loss. Compare the measured totals before claiming savings.
