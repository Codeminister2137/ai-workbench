"""Drive one development slice through the Baseten event model.

Thin provider driver over scripts/slice_develop_core.py (shared host loop).
Same CLI and bounds as before; orchestration lives in the core exactly once.

Proven 2026-11-06 (9 accepted slices). Usage:
    python scripts/baseten-slice-develop.py --slice NAME --brief BRIEF.txt
        --allow path/a.py [--allow ...] --pytest tests/test_x.py
        --phase-dir artifacts/<run>/<slice> [--max-calls 4] [--cap 16384]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, "packages/ai_provider/src")
sys.path.insert(0, "scripts")

from ai_provider.adapters.baseten import (  # noqa: E402
    BASETEN_BASE_URL,
    BasetenChatClient,
)
from ai_provider.config import BackendConfig, ProviderKind  # noqa: E402
from slice_develop_core import (  # noqa: E402
    TIMEOUT,
    drive_slice,
    print_summary,
    read_env_key,
    slice_arg_parser,
)

MODEL = "meta-models/muse-spark-open-1026"
ENV_NAME = "BASETEN_HACKATHON_API_KEY"


class LowReasoningClient(BasetenChatClient):
    """Baseten slice client: low reasoning effort for code edits."""

    def _chat_payload(self, request, *, stream):
        payload = super()._chat_payload(request, stream=stream)
        payload["reasoning_effort"] = "low"
        return payload


def main() -> int:
    """Parse slice args, build the Baseten client, drive the shared loop."""
    args = slice_arg_parser(__doc__).parse_args()
    root = Path.cwd()
    client = LowReasoningClient(
        BackendConfig(
            provider=ProviderKind.BASETEN,
            model=MODEL,
            base_url=BASETEN_BASE_URL,
            api_key=read_env_key(root, ENV_NAME, label="Baseten event credential"),
            timeout_seconds=TIMEOUT,
        )
    )
    receipt = drive_slice(
        root=root,
        client=client,
        model=MODEL,
        slice_name=args.slice,
        brief=args.brief.read_text(encoding="utf-8"),
        allow=set(args.allow),
        pytest_files=list(args.pytest),
        phase=args.phase_dir,
        max_calls=args.max_calls,
        cap=args.cap,
        purpose="baseten-slice",
    )
    print_summary(receipt)
    return 0 if receipt["status"] == "accepted" else 2


if __name__ == "__main__":
    raise SystemExit(main())
