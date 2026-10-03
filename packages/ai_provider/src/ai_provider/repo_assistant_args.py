"""Argument registration for the repo assistant; no execution or runtime discovery."""

from __future__ import annotations

import argparse
from pathlib import Path

from ai_agent.permissions import ApprovalPolicyPreset
from ai_orchestrator import AccessMethod, CostPolicyTier, QualityThreshold
from ai_orchestrator import PrivacyClass as OrchestratorPrivacyClass

from ai_provider.chat_transcripts import DEFAULT_CHAT_TRANSCRIPT_DB
from ai_provider.orchestrated_runs import DEFAULT_ORCHESTRATED_RUN_DB
from ai_provider.repo_context import DEFAULT_CONTEXT_BUDGET_CHARS, DEFAULT_CONTEXT_FILE_BUDGET_CHARS

DEFAULT_DELEGATION_CONTEXT_BUDGET_CHARS = 6_000
DEFAULT_CHAT_HISTORY_BUDGET_CHARS = 12_000
DEFAULT_CHAT_RECENT_MESSAGE_COUNT = 8
DEFAULT_VALIDATION_COMMAND = "python -m pytest -q"
CLI_MODES = ("ask", "review", "implement", "plan", "diagnose", "chat")
CHAT_CONTEXT_MODES = ("rolling_summary", "hard_fail", "full_history")
APPROVAL_POLICY_PRESETS = tuple(item.value for item in ApprovalPolicyPreset)


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the existing CLI surface without resolving config or contacting providers."""
    parser = argparse.ArgumentParser(
        description="Run a minimal repo-aware coding assistant request."
    )
    parser.add_argument("prompt", nargs="?", help="Coding prompt to prepare or execute.")
    parser.add_argument(
        "--mode",
        choices=CLI_MODES,
        default="ask",
        help=(
            "Execution mode: ask/review answer without actions, implement permits "
            "approved actions, plan never contacts a provider, diagnose prints capabilities, "
            "chat persists a provider-neutral local transcript."
        ),
    )
    parser.add_argument(
        "--local-capabilities",
        action="store_true",
        help="Print a local machine/provider capability report and exit.",
    )
    parser.add_argument(
        "--codex-mcp-setup",
        action="store_true",
        help=(
            "Create or update project-scoped .codex/config.toml so Codex can use "
            "this repository's read/search MCP tools."
        ),
    )
    parser.add_argument(
        "--codex-mcp-register-global",
        action="store_true",
        help=(
            "With --codex-mcp-setup, also run `codex mcp add` to persistently "
            "register the server in the user-level Codex MCP configuration."
        ),
    )
    parser.add_argument(
        "--codex-login",
        action="store_true",
        help=(
            "Run `codex login` so Codex can refresh its local ChatGPT/OAuth session. "
            "This mutates local Codex auth state and cannot be combined with a prompt."
        ),
    )
    parser.add_argument(
        "--codex-login-device",
        action="store_true",
        help=(
            "Run `codex login --device-auth` for device-code authentication. "
            "This mutates local Codex auth state and cannot be combined with a prompt."
        ),
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        help="Repository root. Defaults to the nearest parent containing .git.",
    )
    parser.add_argument(
        "--file",
        action="append",
        type=Path,
        default=[],
        help="Repo file to include in the prompt. May be passed more than once.",
    )
    parser.add_argument(
        "--context-budget-chars",
        type=int,
        default=DEFAULT_CONTEXT_BUDGET_CHARS,
        help=(
            "Maximum characters reserved for all repository context. Use 0 to disable the budget."
        ),
    )
    parser.add_argument(
        "--context-file-budget-chars",
        type=int,
        default=DEFAULT_CONTEXT_FILE_BUDGET_CHARS,
        help="Maximum characters included from any one context file.",
    )
    parser.add_argument(
        "--delegate-context",
        action="store_true",
        help=(
            "Extract bounded, source-cited repository context with a local model "
            "before the primary request."
        ),
    )
    parser.add_argument(
        "--delegation-context-budget-chars",
        type=int,
        default=DEFAULT_DELEGATION_CONTEXT_BUDGET_CHARS,
        help="Maximum characters sent to the local context-extraction model.",
    )
    parser.add_argument(
        "--allow-outside-files",
        action="store_true",
        help=(
            "Explicitly allow selected files and action paths outside the repository "
            "without prompting."
        ),
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path("packages/ai_orchestrator/examples/model_catalog.toml"),
        help="Path to a TOML model catalog.",
    )
    parser.add_argument(
        "--privacy",
        choices=[item.value for item in OrchestratorPrivacyClass],
        default=OrchestratorPrivacyClass.LOCAL_ONLY.value,
        help="Privacy class for the request.",
    )
    parser.add_argument(
        "--quality",
        choices=[item.value for item in QualityThreshold],
        default=QualityThreshold.STANDARD.value,
        help="Minimum quality threshold.",
    )
    parser.add_argument(
        "--provider",
        choices=["ollama", "openai", "requesty", "google"],
        help="Hard provider override.",
    )
    parser.add_argument("--route-id", help="Hard access-route override.")
    parser.add_argument(
        "--access-method",
        choices=[item.value for item in AccessMethod],
        help="Hard access-method override, such as local_runtime/provider_api.",
    )
    parser.add_argument("--model", help="Hard model override.")
    parser.add_argument(
        "--cost-policy",
        choices=[item.value for item in CostPolicyTier],
        default=None,
        help="Maximum billing boundary this task may cross.",
    )
    parser.add_argument(
        "--system",
        help="Additional provider-neutral system instruction appended to the tool prompt.",
    )
    parser.add_argument(
        "--approval-policy",
        choices=APPROVAL_POLICY_PRESETS,
        default=ApprovalPolicyPreset.INTERACTIVE.value,
        help=(
            "Model-neutral action approval preset. read_only denies writes/shell, "
            "interactive asks for writes/shell, workspace_write allows file writes "
            "but denies legacy shell actions, and trusted_local allows local writes/shell."
        ),
    )
    parser.add_argument("--max-latency-seconds", type=float, help="Hard latency constraint.")
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=180.0,
        help=(
            "Provider timeout. For external-agent routes, this is an inactivity "
            "timeout and model output resets the timer."
        ),
    )
    parser.add_argument(
        "--away-minutes",
        type=float,
        help=(
            "Visible foreground work budget for unattended runs. If --timeout-seconds "
            "is not supplied, provider and external-agent timeouts are set to this "
            "many minutes."
        ),
    )
    parser.add_argument(
        "--orchestrated",
        action="store_true",
        help=(
            "Plan or run the staged foreground unattended workflow. Requires "
            "--away-minutes and currently exposes a dry-run stage plan in plan mode."
        ),
    )
    parser.add_argument(
        "--away-run-db",
        type=Path,
        default=DEFAULT_ORCHESTRATED_RUN_DB,
        help=(
            "SQLite database path for durable orchestrated run and stage records. "
            "Relative paths are resolved from the repository root."
        ),
    )
    parser.add_argument(
        "--chat-db",
        type=Path,
        default=DEFAULT_CHAT_TRANSCRIPT_DB,
        help=(
            "SQLite database path for local provider-neutral chat transcripts. "
            "Relative paths are resolved from the repository root."
        ),
    )
    parser.add_argument(
        "--chat-session",
        help=(
            "Chat session to resume in --mode chat. Use 'new' or omit for a new "
            "session, 'last' for the latest session in this repository, or pass a session ID."
        ),
    )
    parser.add_argument(
        "--chat-title",
        help="Optional title for a new --mode chat transcript.",
    )
    parser.add_argument(
        "--chat-list",
        action="store_true",
        help="List recent local chat transcript sessions and exit without contacting a provider.",
    )
    parser.add_argument(
        "--chat-list-limit",
        type=int,
        default=20,
        help="Maximum number of sessions printed by --chat-list.",
    )
    parser.add_argument(
        "--chat-context-mode",
        choices=CHAT_CONTEXT_MODES,
        default="rolling_summary",
        help=(
            "How --mode chat handles transcript history that exceeds --chat-history-budget-chars."
        ),
    )
    parser.add_argument(
        "--chat-history-budget-chars",
        type=int,
        default=DEFAULT_CHAT_HISTORY_BUDGET_CHARS,
        help=("Maximum characters sent as assembled chat history. Use 0 to send full history."),
    )
    parser.add_argument(
        "--chat-recent-message-count",
        type=int,
        default=DEFAULT_CHAT_RECENT_MESSAGE_COUNT,
        help="Recent non-system transcript messages kept raw when rolling summaries are used.",
    )
    parser.add_argument(
        "--validation-command",
        action="append",
        default=[],
        metavar="CMD",
        help=(
            "Deterministic validation command to run during orchestrated executed runs. "
            f"May be repeated. Defaults to `{DEFAULT_VALIDATION_COMMAND}`."
        ),
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip deterministic validation in orchestrated executed runs.",
    )
    parser.add_argument(
        "--validation-timeout-seconds",
        type=float,
        default=300.0,
        help="Timeout for each deterministic validation command.",
    )
    parser.add_argument(
        "--max-repair-cycles",
        type=int,
        default=3,
        help=(
            "Maximum orchestrated repair cycles after failed validation. Use 0 to "
            "disable repairs and -1 to disable the cycle cap while preserving the "
            "--away-minutes wall-clock budget."
        ),
    )
    parser.add_argument(
        "--start-ollama",
        action="store_true",
        help="Start `ollama serve` before executing a local Ollama request.",
    )
    parser.add_argument(
        "--ollama-command",
        default="ollama",
        help="Ollama executable used with --start-ollama.",
    )
    parser.add_argument(
        "--ollama-startup-timeout-seconds",
        type=float,
        default=10.0,
        help="Seconds to wait for Ollama to become reachable after starting it.",
    )
    parser.add_argument(
        "--ollama-log-file",
        type=Path,
        default=Path("artifacts/ollama-runtime/ollama-serve.log"),
        help=(
            "File for Ollama serve output when --start-ollama is used. "
            "Use an empty value only by calling the Python CLI directly."
        ),
    )
    parser.add_argument(
        "--ollama-profile",
        choices=["gaming", "balanced", "full"],
        help=(
            "Resource profile used when this command starts Ollama. "
            "Restart Ollama for a changed profile to take effect."
        ),
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        help="Also save the complete CLI transcript to this local file.",
    )
    parser.add_argument(
        "--log-full-prompt",
        action="store_true",
        help=(
            "Include exact system and user prompts in --log-file transcripts. "
            "This can contain repository context and sensitive text."
        ),
    )
    parser.add_argument(
        "--skip-prompt-review",
        action="store_true",
        help="Bypass deterministic prompt review.",
    )
    parser.add_argument(
        "--codex-persist-session",
        action="store_true",
        help=(
            "For Codex CLI routes, omit --ephemeral so Codex can save a resumable session. "
            "This is opt-in because it writes Codex session state outside this repo."
        ),
    )
    parser.add_argument(
        "--codex-resume",
        help=(
            "For Codex CLI routes, resume a previous Codex exec session by id/name, "
            "or pass 'last' for the most recent session."
        ),
    )
    parser.add_argument(
        "--codex-output-last-message",
        type=Path,
        help=(
            "For Codex CLI routes, also ask Codex to write the final assistant message "
            "to this local file via --output-last-message."
        ),
    )
    parser.add_argument(
        "--codex-output-schema",
        type=Path,
        help=(
            "For Codex CLI routes, pass a JSON Schema file to Codex via --output-schema "
            "to constrain the final assistant message."
        ),
    )
    parser.add_argument(
        "--codex-search",
        action="store_true",
        help=(
            "For Codex CLI routes, enable Codex web search for this run. "
            "This is opt-in because it allows external web/search activity."
        ),
    )
    parser.add_argument(
        "--codex-mcp-tools",
        action="store_true",
        help=(
            "For Codex CLI routes, inject this repository's project-local MCP "
            "read/search/delegate tools into this run via Codex -c config overrides."
        ),
    )
    parser.add_argument(
        "--codex-image",
        action="append",
        default=[],
        type=Path,
        metavar="PATH",
        help=(
            "For Codex CLI routes, attach one local image to the initial prompt via "
            "--image. May be repeated."
        ),
    )
    parser.add_argument(
        "--codex-plugin-install",
        action="append",
        default=[],
        metavar="PLUGIN@MARKETPLACE",
        help=(
            "Install one exact Codex plugin selector through `codex plugin add`. "
            "May be repeated. Requires --execute and does not authorize external services."
        ),
    )
    parser.add_argument(
        "--codex-plugin-remove",
        action="append",
        default=[],
        metavar="PLUGIN@MARKETPLACE",
        help=(
            "Remove one exact Codex plugin selector through `codex plugin remove`. "
            "May be repeated. Requires --execute."
        ),
    )
    parser.add_argument(
        "--scrutinize-response",
        action="store_true",
        help=(
            "Run one additional response-quality pass after a completed ask/review "
            "response and include its report in the transcript."
        ),
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute the provider request. Without this, only print the prepared plan.",
    )
    parser.add_argument(
        "--apply-actions",
        action="store_true",
        help="Execute assistant-proposed local actions after a provider response.",
    )
    parser.add_argument(
        "--native-tools",
        action="store_true",
        help=(
            "Use provider-native tool calling with the ai-agent loop. This is the "
            "default for executed implement-mode provider routes; the flag is kept "
            "for explicitness and compatibility."
        ),
    )
    parser.add_argument(
        "--no-native-tools",
        action="store_true",
        help=(
            "Disable the default provider-native tool loop and use the older "
            "single-response provider execution path."
        ),
    )
    parser.add_argument(
        "--max-action-rounds",
        type=int,
        default=3,
        help="Maximum provider/action follow-up rounds when --apply-actions is set.",
    )
    parser.add_argument(
        "--command-timeout-seconds",
        type=float,
        default=60.0,
        help="Timeout for assistant-proposed local commands.",
    )
    parser.add_argument(
        "--user-config",
        type=Path,
        help="Private TOML preferences (default: <repo>/user-config.toml).",
    )
    from ai_provider.research_execution import add_research_arguments

    add_research_arguments(parser)
    return parser
