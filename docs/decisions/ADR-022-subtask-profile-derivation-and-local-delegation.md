# ADR-022 - Subtask Profile Derivation And Local Delegation

**Status:** Accepted

**Date:** 2026-09-23

## Context

Complex AI tasks (such as repository-aware coding, prompt refinement, context
extraction, and test evaluation) often involve smaller preparatory or subsidiary
subtasks. Executing every subtask through external or metered routes consumes
unnecessary subscription allowance or API budget and may send large context
unnecessarily across privacy boundaries.

Delegating smaller steps to less capable or free local models (such as local
Ollama models) saves cost and preserves allowance. However, subtask planning must
not hardcode rigid privacy rules that break caller expectations: child tasks must
respect the parent task's privacy boundaries by default, while allowing the cost
policy to target local compute (`LOCAL_ONLY`) to achieve cost savings.

## Options Considered

### Ad-Hoc Delegation In Application/CLI Layer Only

Implement subtask routing directly within client scripts (such as
`repo_coding_assistant.py`) by hardcoding local Ollama calls.

The drawback is bypassing orchestrator capability matching, catalog validation,
and cost policy rules, while duplicating logic across multiple applications (CLI,
AI Council, Job Search).

### Full Multi-Step DAG Workflow Engine In Orchestrator

Build a graph/DAG execution engine into `ai_orchestrator`.

The drawback is premature complexity and dependency bloat that violates the
modular monolith principles (ADR-014, ADR-016, ADR-017).

### Neutral Subtask Profile Derivation And Planning In Orchestrator (Selected)

Provide explicit neutral contracts in `ai_orchestrator` (`derive_subtask_profile`
and `plan_delegated_subtask` returning `DelegatedSubtaskPlan`) that derive child
task profiles from parent tasks.

The child task inherits the parent's `privacy_class` by default (unless
explicitly overridden), defaults its `cost_policy_tier` to `LOCAL_ONLY` to prefer
free local compute, and drops parent model-specific user overrides so subtasks
are routed independently based on their own requirements.

## Decision

Add `derive_subtask_profile`, `plan_delegated_subtask`, and
`DelegatedSubtaskPlan` to `ai_orchestrator`.

Key rules:

1. **Privacy Boundary Inheritance:** A derived subtask profile inherits its
   parent's `privacy_class` by default. If the parent is `LOCAL_ONLY`, the
   subtask is strictly `LOCAL_ONLY`. If the parent is `EXTERNAL_ALLOWED`, the
   subtask profile inherits `EXTERNAL_ALLOWED` unless a stricter policy is
   explicitly requested.
2. **Cost Policy Default:** A derived subtask profile defaults its
   `cost_policy_tier` to `LOCAL_ONLY` to route preparatory/smaller steps to
   local compute, while accepting an explicit cost tier if hosted subtask
   execution is desired.
3. **Override Isolation:** User overrides for specific models/routes on the
   parent task do not cascade to child subtasks unless explicitly provided.
4. **Neutral Output:** `DelegatedSubtaskPlan` pairs the subtask profile with a
   neutral `ExecutionPlan` containing target route metadata, reasons, and
   description without executing provider calls.

## Rationale

This gives applications and execution runners a clean, transparent way to
compose multi-stage tasks across local Ollama and hosted models while strictly
respecting privacy and cost policies.
