# Architecture Decision Records

This directory contains detailed Architecture Decision Records (ADRs).

ADRs preserve **why** important decisions were made, not just what implementation currently exists.

They are particularly useful when a future Codex session encounters an architectural choice and needs to understand the reasoning behind it.

---

## When to create an ADR

Create an ADR when a decision:

* materially affects architecture;
* creates a long-lived constraint;
* has multiple reasonable alternatives;
* changes a previous architectural decision;
* affects provider boundaries;
* affects privacy or data routing;
* introduces persistent storage;
* introduces a significant dependency;
* changes a public API or data contract;
* determines how multiple projects interact;
* would otherwise be easy to forget or misunderstand later.

Do **not** create ADRs for every implementation detail.

For example, choosing a variable name does not need an ADR.

Choosing SQLite instead of PostgreSQL for persistent usage tracking probably does.

---

## Who makes the decision?

The human owner makes material product and architectural decisions.

Codex should participate actively by:

1. identifying when an ADR may be appropriate;
2. investigating the technical context;
3. identifying viable alternatives;
4. explaining trade-offs;
5. providing a technical recommendation when useful;
6. asking the user to make the decision;
7. asking for the user's reasoning when the decision is significant;
8. recording the resulting decision and rationale.

Codex must **not invent the user's rationale after making the decision itself**.

The purpose of the ADR is partly to preserve the human owner's architectural intent for future development.

---

## ADR workflow

When Codex discovers a significant unresolved decision:

```text
Discovery
    ↓
Investigation
    ↓
Identify decision boundary
    ↓
Present alternatives + trade-offs
    ↓
Technical recommendation, if useful
    ↓
Ask user to decide
    ↓
Ask for rationale/context when appropriate
    ↓
Record ADR
    ↓
Implement the agreed decision
```

Codex should not begin implementation of the disputed part before the decision is resolved.

---

## Asking for rationale

Codex should ask for the user's reasoning when:

* the decision has meaningful future consequences;
* the reasoning is not already documented;
* future developers/Codex sessions could reasonably question the choice;
* understanding the motivation would prevent an incorrect future change.

The question should be lightweight.

For example:

> Which option do you want to use?
> I would technically lean toward SQLite because the current system is local and single-user, but this is your architectural decision.
> Once you've chosen, give me the main reason you prefer it so I can record the rationale.

The user does not need to provide a lengthy explanation.

If the rationale is already obvious from the discussion, Codex should not ask unnecessarily.

---

## ADR numbering

Use:

```text
ADR-001-short-name.md
ADR-002-short-name.md
ADR-003-short-name.md
```

Numbers should never be reused.

If a decision changes, preserve the old ADR and mark it:

```text
Status: Superseded
```

Then create a new ADR explaining the new decision and linking to the old one.

---

## ADR template

```markdown
# ADR-NNN — Short Decision Name

**Status:** Proposed / Accepted / Superseded / Rejected

**Date:** YYYY-MM-DD

## Context

What problem or decision required attention?

## Options Considered

### Option A

Description and relevant consequences.

### Option B

Description and relevant consequences.

### Option C

Description and relevant consequences.

## Decision

What did the human owner decide?

## Rationale

Why was this decision made?

Prefer the human owner's actual reasoning where available.

## Consequences

What becomes easier, harder, constrained, or possible as a result?

## Related Decisions

Links to related ADRs.

## Related Projects / Documents

Relevant project plans, architecture sections, issues, etc.
```

---

## Important distinction

`docs/decisions.md` is the current lightweight decision index.

This directory contains detailed ADRs for decisions that deserve their own permanent record.

Do not migrate every existing decision into an ADR automatically. Create detailed ADRs when the decision actually matters enough to justify one.
