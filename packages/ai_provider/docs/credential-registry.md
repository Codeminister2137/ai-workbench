# Credential registry

**Purpose:** durable agent-readable record of which credentials exist, where
they live, what they are for, and how to check their balance — so the agent
never forgets a key or guesses funding. **Values are never stored here.**
All values live in gitignored `.env` files (workbench root, sibling
`remote-ai-operator/` root) and are loaded via
`ai_provider.secrets.load_dotenv`. Never print values; probe auth and record
only status/counts.

**Agent rule:** before any paid/live provider work, read this file plus
[source-state.md](source-state.md). Balances below are dated owner/agent
observations, not live reads — refresh consequential numbers with the owner.

## Provider keys (workbench `.env`)

| Env name | Provider / purpose | Balance source | Last verified |
|---|---|---|---|
| `META_API_KEY` | Meta Model API (`muse-spark-1.3` coding, wonder, voice). Hackathon credits. | Owner dashboard only (`dev.meta.ai`); no balance API in researched surface. Agent keeps a local spend ledger per allowance. | 2026-11-03: auth-ok, 9 models; balance $136.60 (owner). |
| `BASETEN_HACKATHON_API_KEY` | Baseten event key for `meta-models/muse-spark-open-1026` (open-weights bonus). Inference-scoped. | Owner dashboard only (`app.baseten.co/settings/billing`). This key gets HTTP 403 on `GET /v1/billing/usage_summary`, so it cannot read usage or balance. Full-scope keys can use that endpoint (≤31d window) — see source-state note 2026-11-03. | 2026-11-03: present; 403 on billing; $100 event credits (owner). |
| `MODAL_API_KEY` | Modal deploys / hosted demo. | Owner dashboard. | 2026-11-03: $129.97 (owner). |
| `OPENROUTER_API_KEY` | OpenRouter gateway routes. | Owner dashboard; free-tier daily remaining is checked per call by the adapter. | 2026-11-03: auth-ok, 415 models. |
| `REQUESTY_API_KEY` | Requesty gateway routes. | Owner dashboard. | 2026-11-03: auth-ok, 808 models. |
| `OPENCODE_API_KEY` | OpenCode Go inference. | Owner dashboard. | 2026-11-03: auth-ok, 28 models. |
| `OPENAI_API_KEY` | Direct OpenAI (BYOK fallback). | Owner dashboard. | Present; not recently probed. |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | Google/Gemini routes. | Owner dashboard. | Present; not recently probed. |
| `BRAVE_SEARCH_API_KEY` | Brave search tool. | Owner dashboard. | Present; not recently probed. |
| `TAVILY_API_KEY` | Tavily search tool. | Owner dashboard. | Present; not recently probed. |
| `AI_PROVIDER_*` | Harness override (`KIND`, `MODEL`, `BASE_URL`, `API_KEY`, `TIMEOUT_SECONDS`). Takes precedence per `BackendConfig.from_env`. | N/A (points at one of the above). | — |

## Operator / serve credentials

| Env name | Location | Purpose | Notes |
|---|---|---|---|
| `OPERATOR_ACCESS_TOKEN` | Sibling `.env` (and workbench `.env`) | Owner-local serve + phone access token. | Required for live serve; see sibling `.env.example`. |
| `OPERATOR_VISITOR_CODE` | Sibling `.env` / Modal secrets | Hosted demo shared access code. | Delivered out-of-band; never commit. |
| `OPERATOR_SESSION_SECRET` | Sibling `.env` / Modal secrets | Hosted session signing secret. | Rotating logs every visitor out. |
| `OPERATOR_PUBLIC_ORIGIN` | Modal env | Final HTTPS origin for Secure cookies + origin check. | Deploy-only. |
| `OPERATOR_GRANT_PATH` | Modal image | Finite grant file path in image. | Deploy-only. |

## Local allowance pattern

Paid work runs under a named finite allowance (id, model, cap USD, max calls,
per-call token bounds, stop conditions) with a per-call ledger
(input/output tokens, provider-reported when available, estimated cost).
Example: `.tmp/audit-meta-20261103-allowance.json`. The ledger is the spend
guard — providers here have no hard server-side cap, so never run paid calls
without one. Missing balance means ask the owner; never infer funding.
