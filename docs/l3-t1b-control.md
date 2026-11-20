# L3 T1b builtin control

T1b is an opt-in control for T1's `clamp` and `retry_delay_ms` problem.
It keeps the examples, held cases and 4096-token output cap, but explicitly
permits the computational builtins listed in its prompt. Imports and printing
remain unavailable. The default T0–T3 ladder and original task graders remain
unchanged. The shared grading child accepts an optional builtin allowlist;
its empty default preserves the original namespace restrictions.

Run through `scripts/l3_ladder.py --routes ollama --tasks T1b
--allow-tier local_only --walk-all --catalog PATH --max-candidates 3` with a
catalog restricted to the intended three models. Preserve a fresh bounds record
and snapshot directory for each authorized run.

Interpretation proposal: retain original T1 FAIL results and annotate failures
caused by banned builtin use with `constraint_following` (reason:
`builtin_used_when_forbidden`). Report the independent T1b result beside them.
This separates evidence of constraint compliance from correctness on the held
cases without retroactively changing consumed trials. This is a reporting
proposal, not a new persisted verdict field or automatic classification rule.

T1b permits an explicit computational subset rather than Python's entire builtin
namespace: enough for ordinary solutions, without adding file I/O or dynamic
execution helpers. One passing control per model establishes only this small
problem's observed result, not general model quality or reliable compliance.
