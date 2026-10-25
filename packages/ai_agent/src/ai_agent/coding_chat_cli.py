"""Foreground CLI composition for continuous coding; no protocol-output parsing."""

from __future__ import annotations

import argparse
import copy
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from ai_provider.chat_transcripts import DEFAULT_CHAT_TRANSCRIPT_DB, SQLiteChatTranscriptStore
from ai_provider.coding_sessions import ACTIVE_SESSION, CodingSession
from ai_provider.foreground_tools import ACTIVE_FOREGROUND, ForegroundTools
from ai_provider.repo_context import find_repo_root
from ai_provider.user_config import UserConfig, apply_user_defaults, load_user_config

from ai_agent.coding_chat import (
    CodingChatController,
    CodingTurnRequest,
    CodingTurnResult,
    run_terminal_conversation,
)
from ai_agent.coding_chat_input import CodingChatInput
from ai_agent.repo_assistant_args import (
    DEFAULT_CHAT_HISTORY_BUDGET_CHARS,
    DEFAULT_CHAT_RECENT_MESSAGE_COUNT,
)


def run_coding_chat(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    execute: Callable[[argparse.Namespace, UserConfig], int],
) -> int:
    """Bind one owner/session and execute every turn with fresh route scopes."""
    if not args.execute:
        parser.error("--mode coding-chat requires --execute; no conversation was created")
    if args.coding_chat_history_budget_chars < 0:
        parser.error("--coding-chat-history-budget-chars must be zero or greater")
    if any(
        (
            args.list_skills,
            args.fallback_readiness,
            args.local_capabilities,
            args.codex_login,
            args.codex_login_device,
            args.codex_plugin_install,
            args.codex_plugin_remove,
            args.codex_mcp_setup,
            args.codex_mcp_register_global,
            args.chat_list,
            args.chat_session is not None,
            args.chat_title is not None,
            args.chat_db != DEFAULT_CHAT_TRANSCRIPT_DB,
            args.chat_context_mode != "rolling_summary",
            args.chat_history_budget_chars != DEFAULT_CHAT_HISTORY_BUDGET_CHARS,
            args.chat_recent_message_count != DEFAULT_CHAT_RECENT_MESSAGE_COUNT,
        )
    ):
        parser.error("coding-chat cannot be combined with setup, diagnostics or --chat-* options")
    if args.apply_actions or args.no_native_tools or args.codex_mcp_tools:
        parser.error("coding-chat requires common coding tools, not legacy or disabled tools")
    if args.shared_tools == "inspection" or args.tool_profile != "coding":
        parser.error("coding-chat requires the coding tool profile")
    if args.scrutinize_response:
        parser.error(
            "--scrutinize-response is for ask/review; use orchestrated scrutiny for coding"
        )
    if args.codex_persist_session or args.codex_resume:
        parser.error(
            "coding-chat uses --coding-session, not independent native Codex session history"
        )
    if args.orchestrated and args.away_minutes is None:
        parser.error("--orchestrated requires --away-minutes (a fixed session allowance)")
    if args.max_repair_cycles < -1:
        parser.error("--max-repair-cycles must be -1 or greater")
    root = (args.repo_root or find_repo_root(Path.cwd())).resolve()
    config_path = args.user_config or root / "user-config.toml"
    try:
        config = load_user_config(config_path, required=args.user_config is not None)
    except (OSError, ValueError, TypeError) as exc:
        parser.error(f"Invalid user config {config_path}: {exc}")
    apply_user_defaults(args, config)
    args.cost_policy = args.cost_policy or config.cost_policy.value
    session_deadline = (
        time.perf_counter() + args.away_minutes * 60 if args.away_minutes is not None else None
    )
    args.shared_tools = "coding"
    args.repo_root = root
    args.system = (
        (args.system + "\n\n" if args.system else "")
        + "You are in a continuous coding conversation. A turn may be a question, "
        "clarification, plan, review or implementation request. Having coding tools "
        "does not authorize unrequested edits. Act on the current user's request, "
        "retain explicit owner decisions, and ask at material decision boundaries. "
        "Treat previous conversation as history; refresh repository evidence before "
        "acting. Do not claim tests or tool effects you did not observe."
    )
    identifier = args.coding_session or "new"
    if identifier == "new" and args.coding_session_reconciled:
        parser.error("Reconciliation is for an existing coding session")
    database = args.coding_session_db
    if not database.is_absolute():
        database = root / database
    store = SQLiteChatTranscriptStore(database)
    # Verify linkage before changing the coding-session status on resume.
    if identifier != "new":
        try:
            CodingChatController(
                store,
                identifier,
                root,
                args.privacy,
                history_budget_chars=args.coding_chat_history_budget_chars,
            )
        except (ValueError, OSError) as exc:
            print(f"failure_reason: {exc}")
            return 1
    try:
        session = CodingSession.open(
            database,
            identifier,
            root,
            args.prompt or "Continuous coding conversation",
            args.session_decision,
            reconciled=args.coding_session_reconciled,
            privacy_class=args.privacy,
            cost_policy=args.cost_policy,
        )
        if identifier == "new":
            CodingChatController.create(
                store,
                session.session_id,
                root,
                args.privacy,
                args.prompt or "Continuous coding conversation",
            )
        controller = CodingChatController(
            store,
            session.session_id,
            root,
            args.privacy,
            history_budget_chars=args.coding_chat_history_budget_chars,
        )
    except (ValueError, OSError) as exc:
        print(f"failure_reason: {exc}")
        return 1
    print(f"coding_session_id: {session.session_id}")
    print(f"coding_chat_db: {database}")
    args.shared_task_id = session.session_id
    foreground = ForegroundTools(root, session)
    terminal = CodingChatInput(stage=controller.stage)
    terminal.deadline = session_deadline
    if args.away_minutes is not None:
        print(f"coding_chat_away_minutes: {args.away_minutes:g}")
        print("coding_chat_away_scope: fixed_launch; resume_requires_explicit_new_allowance")
    foreground.approval_reader = terminal.approve_scoped
    session_token = ACTIVE_SESSION.set(session)
    foreground_token = ACTIVE_FOREGROUND.set(foreground)

    def turn(request: CodingTurnRequest) -> CodingTurnResult:
        now = time.perf_counter()
        if session_deadline is not None and now >= session_deadline:
            return CodingTurnResult(1, None, "failed", "Coding-chat allowance expired.")
        turn_args = copy.deepcopy(args)
        limits = [session_deadline] if session_deadline is not None else []
        if args.turn_timeout_seconds is not None:
            limits.append(now + args.turn_timeout_seconds)
        turn_deadline = min(limits) if limits else None
        turn_args._execution_deadline = turn_deadline
        if session_deadline is not None:
            turn_args.away_minutes = (session_deadline - now) / 60
        turn_args.mode = "implement"
        turn_args.prompt = request.text
        turn_args._coding_chat_history = request.history
        observed: list[CodingTurnResult] = []
        turn_args._coding_chat_observer = observed.append
        turn_args._coding_chat_approval_read = terminal.approve
        if args.log_file is not None:
            turn_args.log_file = args.log_file.with_name(
                f"{args.log_file.stem}.turn-{request.message_id}{args.log_file.suffix}"
            )
        # _main reloads selected files/instructions and creates fresh fallback/run scopes.
        terminal.deadline = turn_deadline
        try:
            with terminal.in_flight():
                returncode = execute(turn_args, config)
        finally:
            terminal.deadline = session_deadline
        if returncode == 0 and turn_deadline is not None and time.perf_counter() >= turn_deadline:
            return replace(
                observed[-1] if observed else CodingTurnResult(1, None, "failed"),
                returncode=1,
                response_text=None,
                execution_status="failed",
                failure_reason="Execution allowance expired; inspect completed effects.",
            )
        if observed:
            return replace(observed[-1], returncode=returncode)
        return CodingTurnResult(
            returncode or 1, None, "failed", "Execution ended without a final CLI report"
        )

    status = 130
    try:
        status = run_terminal_conversation(
            controller, turn, initial_prompt=args.prompt, read=terminal.read
        )
        return status
    finally:
        cleanup_complete = False
        try:
            try:
                terminal.close()
            finally:
                foreground.close()
                for handle in session.supervisor.processes:
                    session.observe_process(session.supervisor.status(handle))
            cleanup_complete = True
        finally:
            try:
                session.status(
                    "interrupted"
                    if status == 130 or not cleanup_complete
                    else "completed"
                    if status == 0
                    else "failed"
                )
            finally:
                ACTIVE_FOREGROUND.reset(foreground_token)
                ACTIVE_SESSION.reset(session_token)
