# Company site (P7)

The public P7 front: offering pages, intake flow, and chatbot. Content
is decision-traced; launch is gated on P7 answers (naming, offering,
pricing).

Key areas: `company-site/`, `docs/plans/p7-*`.

Current state: shell + intake live; placeholders await P7 deliberation.
See the Roadmap.

Company-site E2E checklists include an AI wording/tone review prompt for
changed HTML pages, or the PL index and an EN page when shared assets
change. The prompt covers clarity, natural PL/EN language, terminology,
claims, calls to action and form feedback. Findings must cite page/language
and exact copy, explain the impact, and propose corrections without
inventing offering facts. Review output belongs in the existing E2E notes;
the owner retains the verdict. Missing content or a review not run is a
limitation, never evidence of passing.

This slice generates prompts only. It does not execute inference, select a
provider, grant data transmission, or expand the command runner allowlist.
Use an already-authorized AI route when performing the review. Nonrenderable
changes still need concrete testing pointers. Model-quality evaluation of
the prompt remains separate from deterministic checklist tests.
