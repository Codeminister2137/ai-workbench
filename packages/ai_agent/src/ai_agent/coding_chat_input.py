"""One foreground terminal reader, with distinct chat and approval channels."""

from __future__ import annotations

import codecs
import os
import sys
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StagedCodingInput:
    """Owner input already recorded while a previous turn was running."""

    text: str
    message_id: str
    session_id: str


class CodingChatInput:
    """Queue steering for the next turn; never interpret chat text as approval.

    Execution stays on its original thread, retaining signal and context-variable
    semantics. A joined reader thread polls only while a turn is active. Approval
    tickets expire when their prompt, invocation or foreground session closes.
    """

    def __init__(
        self,
        write: Callable[[str], None] = print,
        stage: Callable[[str], StagedCodingInput] | None = None,
    ) -> None:
        self.write = write
        self.stage = stage
        self.condition = threading.Condition()
        self.pending: deque[str | StagedCodingInput] = deque()
        self.closed = False
        self.ticket: str | None = None
        self.answer: str | None = None
        self.thread: threading.Thread | None = None
        self.stop = threading.Event()
        self.reader_error: BaseException | None = None
        self.deadline: float | None = None
        self.poll: Callable[[], str | None] = TerminalLinePoll(write)

    def _active(self) -> bool:
        return self.deadline is None or time.perf_counter() < self.deadline

    def _check_deadline(self) -> None:
        if not self._active():
            raise TimeoutError("Coding-chat allowance expired; no further turn admitted.")

    def feed(self, text: str) -> None:
        """Dispatch a complete terminal line, including explicitly scoped answers."""
        with self.condition:
            if self.closed:
                return
            if text.strip() in {"/exit", "/quit"}:
                self.close()
                self.write("coding_chat_exit_pending: finishes this turn; queued work will not run")
                return
            if text.strip() == "/multiline" or text.startswith("/history"):
                self.write(
                    "coding_chat_input: /multiline and /history require the idle You> prompt"
                )
                return
            if text.strip() == "/status":
                self.write(f"coding_chat_input: active turn; {len(self.pending)} queued messages")
                return
            if text.strip() == "/help":
                self.write(
                    "Text queues steering; /approve ID yes|no answers; /exit finishes this turn."
                )
                return
            if text.startswith("/approve "):
                parts = text.split()
                if (
                    len(parts) == 3
                    and self.ticket is not None
                    and parts[1] == self.ticket
                    and parts[2].lower() in {"yes", "no"}
                    and self.answer is None
                ):
                    self.answer = parts[2].lower()
                    self.condition.notify_all()
                else:
                    self.write("coding_chat_input: expired or invalid approval answer refused")
                return
            if text.strip():
                if text.startswith("/steer "):
                    text = text.removeprefix("/steer ")
                elif text.lstrip().startswith("/"):
                    # Idle input refuses unknown slash commands; queueing one here would
                    # hand a command-looking string to the model as a coding request.
                    self.write(
                        "coding_chat_input: unknown command during a turn; prefix a "
                        "request that begins with '/' with /steer"
                    )
                    return
                if not text.strip():
                    return
                pending_entry = (
                    self.stage(text) if self.stage and not text.startswith("/") else text
                )
                self.pending.append(pending_entry)
                if self.ticket is not None and text.strip().lower() in {"yes", "no"}:
                    self.write(
                        "coding_chat_input: bare yes/no is queued chat, not an approval. "
                        f"For this pending operation use /approve {self.ticket} "
                        f"{text.strip().lower()}"
                    )
                self.write(
                    "coding_chat_queued: applies after this turn; running effects may continue"
                )

    def read(self, prompt: str) -> str | StagedCodingInput:
        """Read idle chat input; queued steering has priority and remains ordered."""
        self._check_deadline()
        with self.condition:
            if self.reader_error is not None:
                raise self.reader_error
            if self.pending:
                entry = self.pending.popleft()
                # All earlier staged text is already in history. Deliver the latest
                # correction as the current request rather than executing stale ones.
                if isinstance(entry, StagedCodingInput):
                    while self.pending and isinstance(self.pending[0], StagedCodingInput):
                        entry = self.pending.popleft()
                return entry
            if self.closed:
                raise EOFError
        if not sys.stdin.isatty():
            line = input(prompt)
            self._check_deadline()
            return line
        self.write(prompt)
        while True:
            self._check_deadline()
            line = self.poll()
            if line is not None:
                self._check_deadline()
                return line
            time.sleep(0.02)

    def approve_scoped(self, prompt: str, active: Callable[[], bool]) -> str:
        """Shared approvals fail closed when there is no controlling reader."""
        if self.thread is None:
            return "no"
        return self.approve(prompt, active)

    def approve(self, prompt: str, active: Callable[[], bool] = lambda: True) -> str:
        """Return yes only for an answer naming this fresh, still-active prompt."""

        def approval_active() -> bool:
            return self._active() and active()

        with self.condition:
            if self.closed or self.ticket is not None or not approval_active():
                return "no"
            if self.thread is None:
                # Noninteractive streams/tests keep the existing sequential interface.
                answer = input(prompt)
                return answer if approval_active() else "no"
            ticket = uuid.uuid4().hex
            self.ticket, self.answer = ticket, None
            try:
                self.write(
                    prompt + f"\nReply /approve {ticket} yes (or no); other text queues steering."
                    "\nUse the complete command with this ID. Bare yes/no does not approve."
                )
                while not self.closed and approval_active() and self.answer is None:
                    self.condition.wait(0.05)
                return (
                    self.answer if not self.closed and approval_active() and self.answer else "no"
                )
            finally:
                self.ticket, self.answer = None, None

    def close(self) -> None:
        with self.condition:
            self.closed = True
            self.pending.clear()
            self.condition.notify_all()

    @contextmanager
    def in_flight(self, poll: Callable[[], str | None] | None = None):
        """Start a cancellable reader only for a controlling terminal or test poll."""
        if poll is None and not sys.stdin.isatty():
            yield
            return
        poll = poll or self.poll
        self.stop.clear()

        def collect() -> None:
            try:
                while not self.stop.is_set():
                    line = poll()
                    if line is not None:
                        self.feed(line)
                    self.stop.wait(0.02)
            except EOFError:
                self.close()
            except BaseException as exc:
                with self.condition:
                    self.reader_error = exc
                self.close()

        self.thread = threading.Thread(target=collect, name="coding-chat-terminal")
        self.thread.start()
        try:
            yield
        finally:
            self.stop.set()
            self.thread.join()
            self.thread = None


class TerminalLinePoll:
    """Nonblocking console input; no detached blocking readline survives a turn."""

    def __init__(self, write: Callable[[str], None]) -> None:
        self.write = write
        self.characters = ""
        self.extended_key = False
        self.high_surrogate: int | None = None
        self.decoder: codecs.IncrementalDecoder | None = None
        self.eof = False

    def __call__(self) -> str | None:
        if os.name != "nt":
            import select

            if "\n" in self.characters:
                line, self.characters = self.characters.split("\n", 1)
                return line.removesuffix("\r")
            if self.eof:
                if self.characters:
                    line, self.characters = self.characters, ""
                    return line
                raise EOFError
            if select.select([sys.stdin], [], [], 0)[0]:
                if self.decoder is None:
                    self.decoder = codecs.getincrementaldecoder(sys.stdin.encoding or "utf-8")(
                        errors=sys.stdin.errors or "strict"
                    )
                data = os.read(sys.stdin.fileno(), 4096)
                self.eof = not data
                self.characters += self.decoder.decode(data, final=self.eof)
                if "\n" in self.characters:
                    line, self.characters = self.characters.split("\n", 1)
                    return line.removesuffix("\r")
                if self.eof:
                    if self.characters:
                        line, self.characters = self.characters, ""
                        return line
                    raise EOFError
            return None
        import msvcrt

        while msvcrt.kbhit():
            character = msvcrt.getwch()
            if self.extended_key:
                self.extended_key = False
                continue
            # getwch returns one Windows UTF-16 code unit, including paired input
            # split between polls. Echo only after combining the full character.
            code_unit = ord(character)
            if 0xD800 <= code_unit <= 0xDBFF:
                self.high_surrogate = code_unit
                continue
            if 0xDC00 <= code_unit <= 0xDFFF and self.high_surrogate is not None:
                character = chr(
                    0x10000 + ((self.high_surrogate - 0xD800) << 10) + code_unit - 0xDC00
                )
            self.high_surrogate = None
            if character in {"\0", "\xe0"}:
                self.extended_key = True
            elif character in {"\r", "\n"}:
                line, self.characters = self.characters, ""
                sys.stdout.write("\n")
                sys.stdout.flush()
                return line
            elif character == "\x03":
                # Deliver SIGINT to the main execution thread, where cleanup lives.
                import _thread

                _thread.interrupt_main()
            elif character == "\x1a":
                raise EOFError
            elif character == "\b":
                if self.characters:
                    self.characters = self.characters[:-1]
                    sys.stdout.write("\b \b")
            elif character.isprintable():
                self.characters += character
                sys.stdout.write(character)
            sys.stdout.flush()
        return None
