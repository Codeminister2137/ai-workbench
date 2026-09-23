# ADR-023: Google / Antigravity Access Routes and Live Multi-Model Delegation Workflow

## Status
Accepted

## Date
2026-09-24

## Context
When running local development or executing complex tasks under OpenAI/Codex usage limits, the orchestration and provider layers needed:
1. Alternative high-capability hosted models (such as Google Gemini 3.1 Pro and Gemini 3.8 Flash) accessible through Google AI Studio free allowances, Antigravity IDE subscription allowances, and Requesty prepaid gateways.
2. Route provenance awareness: the exact same model (e.g. `gemini-3.1-pro`) can exist across distinct products and billing models (Google AI Studio Free vs. Antigravity Subscription Allowance vs. Requesty billing), where mixing them up would risk unintended financial cost or auth failures.
3. An end-to-end execution runner (`live_delegation_runner.py`) that executes subtask delegation in practice—summarizing large context with local Ollama before injecting the distilled context into high-capacity hosted models (Google Gemini or OpenAI).

## Decision
1. **Google & Antigravity Route Enums**:
   - `AccessMethod.ANTIGRAVITY_CLI`
   - `AuthMethod.GOOGLE_ACCOUNT_SIGN_IN`
   - `BillingSource.GOOGLE_AI_STUDIO_FREE`, `BillingSource.GOOGLE_API_BILLING`, `BillingSource.ANTIGRAVITY_SUBSCRIPTION_ALLOWANCE`
   - `ProviderKind.GOOGLE` mapped to Google's OpenAI-compatible endpoint (`https://generativelanguage.googleapis.com/v1beta/openai`) with API key resolution from `GEMINI_API_KEY` or `GOOGLE_API_KEY`.
2. **Explicit Catalog Provenance**:
   - Catalog entries for Google AI Studio (`free_only`), Antigravity IDE (`allowances_allowed`), and Requesty (`prepaid_credits_allowed`) routes disambiguating access methods, billing sources, and auth requirements.
3. **Live Multi-Model Workflow Runner**:
   - `ai_provider/examples/live_delegation_runner.py` executes local subtask summarization via Ollama, parses the distilled output, constructs an enriched primary prompt, and executes the primary coding/architecture request via Google or OpenAI backends according to user-selected privacy and cost policies.

## Consequences
- The system can continue high-capability coding tasks even when Codex subscription limits are exhausted.
- Route provenance is guaranteed: free Google AI Studio tiers and Antigravity subscription routes cannot silently incur metered API charges.
- End-to-end multi-model delegation is tested and reproducible.
