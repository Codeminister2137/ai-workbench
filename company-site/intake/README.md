# P7 intake files

Chatbot-filled client inquiry handoffs. One JSON file per inquiry, validated
before it is shown as ready for owner review. Approved files move to Workbench
intake; the format never auto-creates tasks or spend.

- `schema.json` — canonical draft 2020-12 schema (closed).
- `example.json` — complete valid file (also the validator's golden case).
- Producer: website chatbot (guided flow, full brief) or the site contact
  form (`form.js`), which emits a JSON **lead**: P7 identity keys
  (`format_version`, `project_id`, `created_at`, `capture_method: "human"`)
  plus contact/goal/budget only. A lead is not a valid brief.
- Consumer: owner review, then Workbench.
- Files live in `p7-projects/<slug>-<YYYYMMDD>-<short-id>.json`, UTF-8,
  max 32 kilobytes (KB), immutable after approval (edits create `v2` + `parent_id`).

Lead → brief enrichment (founder, after the enquiry email arrives):

1. Keep the lead's `project_id` and `created_at` (identity survives).
2. Add the missing required fields from the client thread: `target_users`,
   `success_criteria`, `deliverable_type`, `features_in`, `features_out`,
   `timeline`; drop the lead-only `title`/`format`/`version` keys.
3. Validate (below), then drop the file into `p7-projects/` for dashboard
   review → approve → plan. Nothing auto-executes.

Validate:

```powershell
.venv\Scripts\python.exe scripts/validate-p7-intake.py company-site/intake/example.json --as-of 2026-11-13
```

Exit 0 = valid (warnings allowed, surfaced to owner); 1 = invalid with
error list (chatbot re-prompts); 2 = usage/input-output (IO) error. `--as-of` pins the
30-day expiry check (default: today).

Full contract: `docs/plans/p7-project-file-format-proposal.md` (approved
2026-11-10, inbox D9e-A).
