"""Steering and approvals share one reader without sharing authorization."""

from __future__ import annotations

import os
import threading
from queue import Empty, Queue

import pytest
from ai_agent.coding_chat_input import CodingChatInput
from ai_agent.contracts import ToolCall, ToolCategory
from ai_agent.shared_approvals import TerminalApproval


def test_queued_yes_and_steering_cannot_approve_a_fresh_operation():
    output = []
    terminal = CodingChatInput(output.append)
    terminal.feed("yes")
    terminal.feed("/steer Keep the original privacy decision")
    ready = threading.Event()
    lines: Queue[str] = Queue()

    def write(text):
        output.append(text)
        if "Reply /approve" in text:
            ready.set()

    terminal.write = write

    def poll():
        try:
            return lines.get_nowait()
        except Empty:
            return None

    answers = []
    with terminal.in_flight(poll):
        worker = threading.Thread(
            target=lambda: answers.append(terminal.approve("Exact operation"))
        )
        worker.start()
        assert ready.wait(2)
        ticket = terminal.ticket
        assert ticket
        terminal.feed("/approve stale-ticket yes")
        terminal.feed("yes")
        assert worker.is_alive()
        assert any(
            "bare yes/no is queued chat, not an approval" in text
            and f"/approve {ticket} yes" in text
            for text in output
        )
        terminal.feed(f"/approve {ticket} no")
        worker.join(2)
        assert not worker.is_alive()
    assert answers == ["no"]
    assert terminal.read("unused") == "yes"
    assert terminal.read("unused") == "Keep the original privacy decision"
    assert terminal.read("unused") == "yes"
    assert terminal.thread is None


def test_ticket_expires_after_answer_and_revocation(tmp_path):
    terminal = CodingChatInput(lambda text: None)
    active = threading.Event()
    active.set()
    ready = threading.Event()
    terminal.write = lambda text: ready.set() if "Reply /approve" in text else None
    answers = []
    with terminal.in_flight(lambda: None):
        approval = TerminalApproval("task", "run", tmp_path, active.is_set, terminal.approve_scoped)
        worker = threading.Thread(
            target=lambda: answers.append(approval(ToolCall("create_file", {}), ToolCategory.WRITE))
        )
        worker.start()
        assert ready.wait(2)
        ticket = terminal.ticket
        active.clear()
        terminal.feed(f"/approve {ticket} yes")
        worker.join(2)
        assert not worker.is_alive()
        assert terminal.ticket is None
        terminal.feed(f"/approve {ticket} yes")
    assert answers == [False]
    assert not terminal.pending


def test_reader_exception_denies_approval_and_is_reported_on_next_read():
    import pytest

    terminal = CodingChatInput(lambda text: None)

    def poll():
        raise OSError("terminal lost")

    with terminal.in_flight(poll):
        assert terminal.approve("Operation") == "no"
    with pytest.raises(OSError, match="terminal lost"):
        terminal.read("You> ")


def test_noninteractive_shared_approval_does_not_read_piped_stdin(monkeypatch):
    terminal = CodingChatInput()
    monkeypatch.setattr("builtins.input", lambda prompt: (_ for _ in ()).throw(AssertionError()))
    assert terminal.approve_scoped("Operation", lambda: True) == "no"


def test_approval_close_wakes_waiter_and_joins_reader():
    terminal = CodingChatInput(lambda text: None)
    ready = threading.Event()
    terminal.write = lambda text: ready.set() if "Reply /approve" in text else None
    answers = []
    with terminal.in_flight(lambda: None):
        worker = threading.Thread(target=lambda: answers.append(terminal.approve("Operation")))
        worker.start()
        assert ready.wait(2)
        terminal.close()
        worker.join(2)
        assert not worker.is_alive()
    assert answers == ["no"]
    assert terminal.thread is None


def test_successive_prompts_require_distinct_tickets():
    terminal = CodingChatInput(lambda text: None)
    ready = threading.Event()
    terminal.write = lambda text: ready.set() if "Reply /approve" in text else None
    answers = []
    tickets = []
    with terminal.in_flight(lambda: None):
        for index in range(2):
            ready.clear()
            worker = threading.Thread(target=lambda: answers.append(terminal.approve("Operation")))
            worker.start()
            assert ready.wait(2)
            tickets.append(terminal.ticket)
            if index:
                terminal.feed(f"/approve {tickets[0]} yes")
                assert worker.is_alive()
            terminal.feed(f"/approve {tickets[-1]} yes")
            worker.join(2)
            assert not worker.is_alive()
    assert answers == ["yes", "yes"]
    assert tickets[0] != tickets[1]


def test_exit_suppresses_queued_execution_and_denies_new_approvals():
    import pytest

    terminal = CodingChatInput(lambda text: None)
    terminal.feed("Continue the edit")
    terminal.feed("/exit")
    assert not terminal.pending
    assert terminal.approve("Operation") == "no"
    with pytest.raises(EOFError):
        terminal.read("You> ")


@pytest.mark.skipif(os.name != "nt", reason="Windows console input")
def test_windows_poll_preserves_partial_unicode_input_between_turns(monkeypatch):
    import msvcrt
    from collections import deque

    from ai_agent.coding_chat_input import TerminalLinePoll

    characters = deque("zażół")
    monkeypatch.setattr(msvcrt, "kbhit", lambda: bool(characters))
    monkeypatch.setattr(msvcrt, "getwch", lambda: characters.popleft())
    poll = TerminalLinePoll(lambda text: None)
    assert poll() is None
    characters.extend("\bć\r")
    assert poll() == "zażóć"


@pytest.mark.skipif(os.name != "nt", reason="Windows console input")
def test_windows_poll_combines_utf16_pairs_across_turns_and_backspace(monkeypatch):
    import msvcrt
    from collections import deque

    from ai_agent.coding_chat_input import TerminalLinePoll

    characters = deque("Keep \ud83d")
    monkeypatch.setattr(msvcrt, "kbhit", lambda: bool(characters))
    monkeypatch.setattr(msvcrt, "getwch", lambda: characters.popleft())
    poll = TerminalLinePoll(lambda text: None)
    assert poll() is None
    characters.extend("\ude80\r")
    assert poll() == "Keep 🚀"
    characters.extend("\ud83d\ude80\bReplace with \ud840\udc00\r")
    assert poll() == "Replace with 𠀀"
