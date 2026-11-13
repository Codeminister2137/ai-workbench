# P7 intake files

Chatbot-filled client inquiry handoffs. One JSON file per inquiry, validated
before it is shown as ready for owner review. Approved files move to Workbench
intake; the format never auto-creates tasks or spend.

- `schema.json` — canonical draft 2020-12 schema (closed).
- `example.json` — complete valid file (also the validator's golden case).
- Producer: website chatbot (guided flow) or human contact form
  (`capture_method: "human"`). Consumer: owner review, then Workbench.
- Files live in `p7-projects/<slug>-<YYYYMMDD>-<short-id>.json`, UTF-8,
  max 32 KB, immutable after approval (edits create `v2` + `parent_id`).

Validate:

```powershell
.venv\Scripts\python.exe scripts/validate-p7-intake.py company-site/intake/example.json --as-of 2026-11-13
```

Exit 0 = valid (warnings allowed, surfaced to owner); 1 = invalid with
error list (chatbot re-prompts); 2 = usage/IO error. `--as-of` pins the
30-day expiry check (default: today).

Full contract: `docs/plans/p7-project-file-format-proposal.md` (approved
2026-11-10, inbox D9e-A).
