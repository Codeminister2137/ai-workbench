# Repo Assistant CLI Parity Plan

## Status
Accepted planning direction as of 2026-09-27. See
`docs/decisions/ADR-024-codex-cli-parity-authorization-and-dev-tool-policy.md`.

## Goal
Make `ai-assistant` a coherent CLI-first coding workflow with Codex as the
baseline capability target while preserving provider-neutral execution,
authorization, and approval policy.

Full parity does not mean silently inheriting every ChatGPT/Codex runtime tool.
It means the CLI has explicit, testable equivalents for the capabilities needed
for code and development work.

## Planned Slices

### 1. Model-neutral approval policy presets

Define project-owned approval modes that can work across Codex, local Ollama,
hosted provider APIs, and future executors.

Expected shape:

- read-only inspection;
- workspace file writes;
- shell command execution;
- external network/search;
- external service read actions;
- external service write actions.

Codex CLI sandbox flags can implement some of these policies for Codex routes,
but the policy names and semantics should belong to the repo assistant rather
than Codex-specific UI behavior.

### 2. Reusable authorization boundary

Create one shared authorization boundary before adding serious connector
support. It should cover:

- service identity and account/session discovery;
- whether the user is authorized;
- what read and write permissions are available;
- where credentials or sessions are expected to live;
- diagnostics that do not reveal tokens or secrets;
- how revocation or reauthorization is surfaced.

Individual GitHub, Codex plugin/app, cloud deployment, document/control, issue
tracker, or similar integrations should consume this boundary instead of
implementing their own auth handling.

### 3. Development-relevant app/tool bridges

Add app/control integrations only when they support current coding and
development workflows. Examples that may become relevant:

- GitHub repository, issue, pull request, and CI workflows;
- local Codex plugin/app capability diagnostics;
- deployment targets such as Cloudflare, Vercel, or Supabase when an app needs
  them;
- development documents or spreadsheets only when they are part of an active
  engineering workflow.

Do not add broad personal productivity, communications, design, finance, or
document-control parity until a concrete task requires it.

### 4. Read/write capability contracts

When a tool surface may eventually mutate state, design the contract with both
read and write capability in mind. Write actions can be disabled by default and
require stricter approval, but the initial design should avoid a read-only
contract that must later be replaced.

### 5. One connector at a time

External-service connectors should be approved and implemented one at a time.
For each connector, record:

- service/provider;
- account/auth method;
- read data boundary;
- write action boundary;
- approval policy required for writes;
- logging and secret-handling rules;
- tests and live/manual validation plan.

GitHub is the likely first connector candidate when a concrete repository
workflow justifies it, but its read/write boundary must be approved before
implementation.

## Deferred

- Exact ChatGPT managed approval UI parity.
- Broad document/app-control parity unrelated to development work.
- Bulk connector/plugin installation or authorization.
- Autonomous external writes without an explicit approval policy.
