# Document library

Company knowledge served by the dashboard Documents tab.

## Where files live

- `docs/library/` (this folder, **tracked**): portfolio-safe documents only.
  Anything here is public by definition.
- `docs/plans/` (**gitignored**): existing private plans and company
  research. Listed read-only; nothing moves.
- `docs/library-private/` (**gitignored**): company-sensitive default for
  new research — pricing deliberations, client files, market analysis.

Rule of thumb: when in doubt, file it private.

## Front-matter (optional, markdown only)

```markdown
---
title: Human-readable title
tags: [services, pricing]
project: some-project-id
created: 2026-11-05
---
```

Files without front-matter list by filename. The `project` field is
reserved for future project linking.
