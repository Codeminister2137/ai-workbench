# Modal vLLM deployment: Qwen2.5-Coder-7B-Instruct

A cost-conscious, bearer-authenticated OpenAI-compatible inference endpoint for
the `modal/qwen/qwen2.5-coder-7b-instruct` Workbench route.

## What it does

- Runs `Qwen/Qwen2.5-Coder-7B-Instruct` with vLLM on a single L4 GPU.
- Caps deployment scaling at one container to bound concurrent GPU usage.
- Protects the OpenAI-compatible `/v1/*` endpoints with a bearer token
(`Authorization: Bearer <MODAL_API_KEY>`).
- Caches model weights and vLLM compilation artifacts in Modal Volumes.
- Enables automatic tool calling with the Hermes parser used by Qwen2.5's chat
  template, as required by the Workbench agent loop.
- Scales down after 30 seconds of inactivity to preserve credits.

> **Security note:** vLLM's built-in API-key auth covers `/v1`, `/v2`,
> `/inference` and `/cohere`, but it does not protect every admin/debug
> endpoint (e.g. `/tokenize`, `/invocations`). Keep the public URL private and
> rotate the token if it is ever exposed.

## Prerequisites

- A Modal account with hackathon or monthly credits.
- The Modal CLI installed and authenticated (`modal token info` shows your workspace).
- Verify remaining eligible credits and the workspace net-spend limit in Usage &
  Billing before deploying. A zero billed amount is historical usage evidence,
  not a remaining-credit balance. A zero net-spend limit is recommended for
  credit-only development; the workspace usage budget is a separate cap before
  credits. If the net-spend setting is unknown, record it as unknown and admit
  only a finite run covered by freshly verified eligible credits with headroom.

## Deploy

1. Create a strong runtime API key and store it as a Modal secret. The same
   value is used for both the Workbench client (`MODAL_API_KEY`) and vLLM's
   internal auth (`VLLM_API_KEY`):

   ```powershell
   $token = -join ((1..48) | ForEach-Object { Get-Random -Maximum 16 | ForEach-Object { $_.ToString('x') } })
   modal secret create modal-runtime-api-key MODAL_API_KEY=$token VLLM_API_KEY=$token
   ```

2. Deploy the app:

   ```powershell
   modal deploy deploy\modal\qwen25-coder-7b\modal_app.py
   ```

3. Note the URL printed by the CLI, e.g.:

   ```text
   https://<workspace>--ai-projects-qwen25-coder-7b-instruct-server.us-east.modal.direct
   ```

## Configure the Workbench

Set the runtime API key in your local environment (`.env` or shell):

```text
MODAL_API_KEY=<token-from-step-1>
```

Add or update this route in your `user-config.toml`:

```toml
[[routes.modal]]
route_id = "modal/qwen/qwen2.5-coder-7b-instruct"
base_url = "https://<workspace>--ai-projects-qwen25-coder-7b-instruct-server.us-east.modal.direct/v1"
api_key = "${MODAL_API_KEY}"
```

The orchestrator catalog already knows this route; `base_url` is the only piece
that must come from your deployment.

## Stop spending credits

When you are not using the endpoint, stop the app:

```powershell
modal app stop ai-projects-qwen25-coder-7b-instruct
```

Redeploy later with the same `modal deploy` command above.

## Updating the model or image

- Change `MODEL_NAME`, `MODEL_REVISION` or `SERVED_MODEL_NAME` in `modal_app.py`.
- Bump the vLLM version only after checking compatibility with the chosen model.
- Re-deploy; the image will rebuild if the dependencies changed.

## Tool calling

The Server explicitly sets `target_concurrency=1` to enable demand-based
autoscaling, alongside `max_containers=1` and the 30-second idle window. A maximum
container cap alone does not enable autoscaling. A bounded October 28 deployment
with neither a target nor a warm minimum received requests but started zero
containers; Server-specific stats located that failure before vLLM startup.
The fresh deployment with an explicit target also failed to start a container.
The target is a documented autoscaler prerequisite, not a demonstrated remedy
for that observed platform behavior. Both bounded apps were stopped; the remaining
startup cause is unknown. Do not infer a vLLM or model failure from those 503s.

The server passes `--enable-auto-tool-choice --tool-call-parser hermes` to vLLM.
Qwen2.5's tokenizer template supports this format. Plain chat probes alone do not
verify the tool-calling path used by the Workbench agent loop.

Modal Servers return HTTP 503 while no replica is ready; the first request triggers
startup rather than waiting in a queue. Before a bounded task, poll `/health` for
200 within an explicit startup deadline, recording other errors and stopping on
failure. Keep this readiness wait separate from inference; do not automatically
replay model requests. See [Modal Servers](https://modal.com/docs/guide/servers).

References checked 2026-10-28:
[Qwen function calling](https://qwen.readthedocs.io/en/v2.5/framework/function_call.html),
[vLLM tool calling](https://docs.vllm.ai/en/stable/features/tool_calling/), and
[Modal budgets and spend limits](https://modal.com/docs/guide/budgets).

## Files

- `modal_app.py` — Modal app, image, server and vLLM startup configuration.
- `README.md` — this runbook.
