# Supervised AI-to-AI trial — 2026-10-29

Owner explicitly requested that Codex conduct the Meta conversation while the
owner cannot respond frequently. This bounded foreground trial exercised the
existing coding-chat controller, Meta transport and transcript store. It adds
no product orchestration protocol, service, queue, storage engine or autonomous
multi-task loop. Prototype handoff files are local experiment artifacts.

Codex assigned a public Operator documentation proposal without edits. Meta read
the public documentation/checker and returned a proposal. Codex reviewed that
actual response and supplied a specific correction: omit parser internals and
duplicated credential names, describe one or more spaces/tabs after export, and
scope non-disclosure to credential violations. Meta then applied the revision.
The host independently checked seven assertions against the resulting diff and
observed tool receipts, including preserved runtime/inherited-env limitations.

All supervisor messages are labelled AI-authored pilot continuations. The worker
received ordinary public documentation file-write authority up front through the
existing workspace-write policy. It did not receive permission to answer human
approvals, execute host code, release, handle credentials or transmit private
Workbench source. Unexpected native approval requests would stop the trial.
No shell/host execution receipt occurred. The owner's earlier terminal session
was not taken over: it had exited130 and its worktree was clean; this experiment
used a separate worktree/session.

Four actual Meta requests consumed the fixed allowance (worst-case reservation
USD0.815104, freshUSD1 envelope). The worker reread the document before editing,
so the next request for its final report was refused. The original worker session
therefore retains exit2/allowance_exhausted and has no second-turn final report.
The host verified and accepted the documentation effect separately; it does not
regrade the incomplete worker outcome. There was no retry or budget extension.

This establishes proposal → actual supervisor review → corrective follow-up →
worker edit → independent host acceptance for this one task. It does not establish
unattended multi-task autonomy, arbitrary task quality, production approval
delegation or interruption/resumption guarantees. Future work should account for
rereads/tool follow-ups and preserve final-report headroom within shared bounds;
current limits must not be silently renewed to compensate. Production continuity
and architecture decisions remain separate owner choices.

Local evidence: `artifacts/ai-to-ai-supervised-20261029/`, especially supervisor
messages, worker-1.json, live/receipt.json, conversation.json and effects-review.json.
The worker authored the documentation; the host supplied feedback/verification
and the completion report. No software behavior changed; no runtime tests were
needed for the documentation edit. Existing passing Operator suite evidence remains
the earlier184tests/8skips/69subtests, not a new test run for this experiment.
