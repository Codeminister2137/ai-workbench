# Publication and privacy review

Review both current source and reachable Git history before publishing a branch.
A clean working tree and passing tests do not establish privacy.

## What stays local

Ignore rules cover credentials, private preferences, immediate handoffs, private
plans, application configuration, reports, transcript databases, logs, documents
and IDE state. `.env.example`, `user-config.example.toml` and
`council.example.json` are public templates containing placeholders.
Never force-add their private counterparts to publish a working local setup.

Check the current tree from the repository root:

```powershell
git status --short
git diff --cached --stat
git ls-files .env user-config.toml CURRENT_CONTEXT.md docs/plans/ artifacts/ data/ logs/
git check-ignore .env user-config.toml CURRENT_CONTEXT.md docs/plans/example.md
```

The `git ls-files` check should produce no private-file paths. Inspect new files
for real credentials, personal contact details, machine paths, recipient lists
and private prompts. Review artifacts separately before sharing. Pattern-based
checks can miss unknown secret formats and can flag safe fixtures.

## History matters

Removed files can remain downloadable through older commits. Review private paths
on every branch intended for publication:

```powershell
git log --all --oneline -- .env user-config.toml CURRENT_CONTEXT.md docs/plans/
```

Commit authorship and license attribution are public metadata. Removing personal
details from a README does not anonymize authors or historical copies. Revoke or
rotate any committed real credential; deleting a file cannot make it safe again.

History cleanup requires an agreed scope, a protected local backup, branch/ref
verification and explicit owner approval. Coordinate rewritten published history
with collaborators. Never silently force-push or delete remote branches.

Rewriting branch history cannot erase other people's clones or forks. Cached
GitHub views and pull-request references may also require separate handling.
See [GitHub's sensitive-data removal guidance](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository).

## Runtime data boundaries

| Workflow | Data boundary |
| --- | --- |
| Offline planning | No inference; some wrappers create local log directories. |
| Local research | Inference stays local; public URLs and search queries leave the machine. |
| Hosted models or native external agents | Approved prompts/context go to the selected service; native tools can expose additional authorized workspace data. |
| Logs, reports and chat databases | Persisted text can include prompts, excerpts and quotations. Git ignores outputs; it does not sanitize them. |

`--log-full-prompt` explicitly retains complete assembled prompts. Memory-only
excerpt handling does not imply quotation-free saved outputs. See
[permissions](repo-assistant/permissions.md), [research](repo-assistant/research.md)
and [environment](environment.md).

## Publish reviewed refs

```powershell
git branch -vv
git ls-remote --heads origin
```

After privacy review and validation, a normal atomic push can create missing
branches and fast-forward existing ones. It should fail if any selected ref is
not a fast-forward. Rewritten history needs separately approved, explicit leases;
never substitute an unrestricted force push. Keep private backup refs local.
