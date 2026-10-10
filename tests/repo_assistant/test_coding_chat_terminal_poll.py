"""Terminal input must retain pasted lines, partial Unicode and EOF across turns."""

import io
import os
from types import SimpleNamespace

import pytest
from ai_agent import coding_chat_input as channel


@pytest.fixture
def posix_pipe(monkeypatch):
    import select

    reader, writer = os.pipe()
    stream = io.TextIOWrapper(os.fdopen(reader, "rb"), encoding="utf-8")
    monkeypatch.setattr(channel.sys, "stdin", stream)
    monkeypatch.setattr(channel, "os", SimpleNamespace(name="posix", read=os.read))
    ready = [True]
    monkeypatch.setattr(
        select, "select", lambda *args: ([stream], [], []) if ready[0] else ([], [], [])
    )
    yield channel.TerminalLinePoll(lambda text: None), writer, ready
    os.close(writer)
    stream.close()


def test_pasted_follow_up_is_delivered_without_waiting_for_another_keystroke(posix_pipe):
    poll, writer, ready = posix_pipe
    os.write(writer, b"Keep local privacy\n/steer Preserve the tests\n")
    assert poll() == "Keep local privacy"
    ready[0] = False  # No more bytes arrive at the OS descriptor.
    assert poll() == "/steer Preserve the tests"
    assert poll() is None


def test_partial_line_and_utf8_survive_active_to_idle_reader_handoff(posix_pipe):
    poll, writer, ready = posix_pipe
    os.write(writer, b"Correction: za\xc5")
    assert poll() is None
    ready[0] = False
    assert poll() is None
    ready[0] = True
    os.write(writer, b"\xbc\xc3\xb3\xc5\x82\xc4\x87\r\n")
    assert poll() == "Correction: zażółć"


def test_incomplete_input_never_blocks_a_turn_cleanup(posix_pipe):
    poll, writer, ready = posix_pipe
    os.write(writer, b"unfinished correction")
    assert poll() is None
    ready[0] = False
    assert poll() is None


def test_buffered_crlf_and_blank_lines_remain_ordered(posix_pipe):
    poll, writer, ready = posix_pipe
    os.write(writer, b"/status\r\n\r\n/exit\r\n")
    assert poll() == "/status"
    ready[0] = False
    assert poll() == ""
    assert poll() == "/exit"


def test_eof_delivers_final_correction_once_and_then_closes(monkeypatch):
    import select

    reader, writer = os.pipe()
    stream = io.TextIOWrapper(os.fdopen(reader, "rb"), encoding="utf-8")
    try:
        os.write(writer, b"final correction")
        os.close(writer)
        monkeypatch.setattr(channel.sys, "stdin", stream)
        monkeypatch.setattr(channel, "os", SimpleNamespace(name="posix", read=os.read))
        monkeypatch.setattr(select, "select", lambda *args: ([stream], [], []))
        poll = channel.TerminalLinePoll(lambda text: None)
        assert poll() is None
        assert poll() == "final correction"
        with pytest.raises(EOFError):
            poll()
    finally:
        stream.close()
