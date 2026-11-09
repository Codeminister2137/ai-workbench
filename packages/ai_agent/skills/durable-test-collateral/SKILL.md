---
name: durable-test-collateral
description: Keep a focused regression test with every bug fix or behavior change. Use when fixing reported wrong behavior in an existing project.
---

# Durable test collateral

A report that something already built behaves wrongly is a bug fix,
even when it comes with feature requests. Verification is part of
the delivered project when it can prevent the same behavior from
breaking again. Use the project's existing framework and conventions.

Use the shared `read_file`, `find_files`, `grep_search` and
`python_runtime` operations. This skill provides instructions, not
authorization or tools.

Workflow, at its smallest: one focused failing test that reproduces
the reported behavior, then the smallest fix, then that test
passing. Observe the authentic failure before the implementation
change when it is safe and runnable.

Keep the check with the project: add or update the smallest
maintained test in the repository's normal test layout that
exercises the changed behavior. A scratch script, probe, or manual
check may help diagnose but never replaces the maintained test.

Do not weaken or delete a real failing test to obtain green. Fix
the product, or explain why the test's expectation is wrong before
changing that expectation.

Run a broad or full suite only when the user, a repository gate, or
proportionate risk requires it — once, after the final edit, not
after each intermediate edit. A focused regression test comes
first; broad proof does not substitute for missing focused
coverage.

Skip the failing-test-first workflow only when the change leaves
program logic alone (typo, text/style tweak, config value, version
pin) or the user asks for speed; say so in the report when no
maintained test is added.
