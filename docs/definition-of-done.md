# Definition of Done

## Functional
- [ ] Requested behavior implemented.
- [ ] Existing behavior that should remain unchanged still works.
- [ ] Relevant edge cases considered.
- [ ] Error handling is appropriate.

## Tests
- [ ] Relevant tests added/updated.
- [ ] Tests pass.
- [ ] External integrations tested at an appropriate boundary.
- [ ] AI behavior changes have an evaluation plan/result where applicable.

## Quality
- [ ] Ruff passes.
- [ ] Formatting passes.
- [ ] Type checking passes when configured.
- [ ] No unnecessary dependency added.
- [ ] No speculative abstraction added.

## Architecture
- [ ] Provider-specific logic remains behind provider boundaries.
- [ ] Application code does not become provider-specific accidentally.
- [ ] No unnecessary service/infrastructure split introduced.
- [ ] Existing decisions respected.
- [ ] Changed architecture has an explicit decision.

## Security / Privacy
- [ ] No secrets added.
- [ ] Sensitive data is not logged unnecessarily.
- [ ] External data transmission is intentional.
- [ ] New permissions/access are justified.

## Scope
- [ ] No unrelated refactoring.
- [ ] No unrelated files modified.
- [ ] User decisions were not silently replaced with assumptions.

## Documentation
- [ ] Public behavior/configuration documented where needed.
- [ ] Architecture docs updated if architecture changed.
- [ ] Decisions recorded if significant.
- [ ] Obsolete documentation updated rather than duplicated.
- [ ] Local `CURRENT_CONTEXT.md` updated for non-trivial work when present.

## Final review
- [ ] `git diff` reviewed.
- [ ] `git status` reviewed.
- [ ] Known limitations reported.
- [ ] Anything not tested/verified explicitly stated.
