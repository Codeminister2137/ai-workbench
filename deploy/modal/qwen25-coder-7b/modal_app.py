"""Modal serverless vLLM deployment for Qwen2.5-Coder-7B-Instruct.

This app runs a small OpenAI-compatible inference endpoint on a single L4 GPU.
Authentication is enforced by vLLM itself: the container receives
``VLLM_API_KEY`` from the ``modal-runtime-api-key`` Modal secret, and the
Workbench sends the same value as ``Authorization: Bearer <MODAL_API_KEY>``.

Before deploying, create the runtime API-key secret:

    modal secret create modal-runtime-api-key MODAL_API_KEY=<strong-random-token> \\
        VLLM_API_KEY=<same-token>

Then deploy with:

    modal deploy deploy/modal/qwen25-coder-7b/modal_app.py

The CLI will print the public URL (e.g.
https://<workspace>--ai-projects-qwen25-coder-7b-instruct-server.us-east.modal.direct).
Use that URL as the `base_url` for the `modal/qwen/qwen2.5-coder-7b-instruct`
route in `user-config.toml` and set `MODAL_API_KEY` to the same token you used
above.

To stop the deployment and stop spending credits:

    modal app stop ai-projects-qwen25-coder-7b-instruct
"""

from __future__ import annotations

import subprocess
import time

import modal

MODEL_NAME = "Qwen/Qwen2.5-Coder-7B-Instruct"
MODEL_REVISION = "c03e6d358207e414f1eca0bb1891e29f1db0e242"  # pinned 2025-01-12
SERVED_MODEL_NAME = "Qwen/Qwen2.5-Coder-7B-Instruct"

PORT = 8000
STARTUP_TIMEOUT_SECONDS = 600

vllm_image = (
    modal.Image.from_registry(
        "nvidia/cuda:12.9.0-devel-ubuntu22.04",
        add_python="3.12",
    )
    .entrypoint([])
    .uv_pip_install("vllm==0.21.0")
    .env(
        {
            "HF_XET_HIGH_PERFORMANCE": "1",
            "VLLM_LOG_STATS_INTERVAL": "1",
            "VLLM_USE_FLASHINFER_SAMPLER": "0",
        }
    )
)

hf_cache_vol = modal.Volume.from_name("huggingface-cache", create_if_missing=True)
vllm_cache_vol = modal.Volume.from_name("vllm-cache", create_if_missing=True)

app = modal.App("ai-projects-qwen25-coder-7b-instruct")


@app.server(
    image=vllm_image,
    gpu="L4",
    target_concurrency=1,
    max_containers=1,
    scaledown_window=30,
    startup_timeout=STARTUP_TIMEOUT_SECONDS,
    volumes={
        "/root/.cache/huggingface": hf_cache_vol,
        "/root/.cache/vllm": vllm_cache_vol,
    },
    port=PORT,
    unauthenticated=True,
    secrets=[modal.Secret.from_name("modal-runtime-api-key")],
)
class Server:
    @modal.enter()
    def start(self) -> None:
        cmd = [
            "vllm",
            "serve",
            MODEL_NAME,
            "--revision",
            MODEL_REVISION,
            "--served-model-name",
            SERVED_MODEL_NAME,
            "--host",
            "0.0.0.0",
            "--port",
            str(PORT),
            "--max-model-len",
            "32768",
            "--enforce-eager",
            "--enable-auto-tool-choice",
            "--tool-call-parser",
            "hermes",
            "--disable-fastapi-docs",
            "--uvicorn-log-level=info",
        ]
        print("Starting vLLM:", " ".join(cmd))
        self.process = subprocess.Popen(cmd)

        deadline = time.time() + STARTUP_TIMEOUT_SECONDS
        import urllib.error
        import urllib.request

        while time.time() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError("vllm serve exited before becoming healthy")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2):
                    break
            except urllib.error.URLError:
                time.sleep(1)
        else:
            self.process.terminate()
            raise RuntimeError("vLLM failed to start within the startup timeout")

    @modal.exit()
    def stop(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
