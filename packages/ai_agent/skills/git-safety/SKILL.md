---
name: git-safety
description: Source-control safety for Git work. Use before any commit, push, or history operation. Never write history without an explicit ask.
---

# Git source-control safety

The working tree belongs to the user. Make the change, leave it visible,
and let them decide what becomes history.

Use the shared `git_status`, `git_diff` and `read_file` operations for
read-only inspection. This skill provides instructions, not authorization
or tools.

Never commit, amend, push, tag, rebase, cherry-pick, revert, reset --hard,
branch-delete, path-restore, or clean without the user asking for that
exact write in this session, in their own words. An explicit request to
create a new commit is not a request to amend, push, or tag. Finishing a
task without such a request is not authorization: leave work uncommitted
for review.

Never commit or push while status reports changes you did not make and
cannot explain.

If a Git lock file or corrupt index blocks you, never kill the holding
process or delete state: wait, retry, use the holder's own stop
mechanism, or stop and report.

Do not use a broad add in a tree you did not clean; name the files you
changed. Do not initialize repos inside vendored, build, data, or
existing source-control trees. Do not stash the user's files to make
status look clean; clean up only scratch you created.

If you already made an unwanted write, say so plainly and stop. Do not
attempt more history surgery without direction.
