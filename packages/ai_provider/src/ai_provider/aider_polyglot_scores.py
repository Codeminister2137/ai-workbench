"""Published Aider polyglot results as a dated selection prior.

Reads the public Aider leaderboard page and normalizes each published run into
the shared :class:`CapabilityScore` record.

This source has two properties that make it the better capability prior for a
gateway route set, and both shape the record:

- **One harness.** Every row was produced by the same tool under the same
  harness, so scores are comparable model-to-model. The harness is recorded on
  every record for that reason, and a score must still never be read as a
  model-only claim.
- **A specific model id, not a family name.** Each run publishes the exact
  ``--model`` argument used, such as ``openrouter/openai/gpt-oss-120b``. That
  id becomes ``model``, so the record grades one model rather than a family,
  and the published display name is kept separately.

Each run also publishes the failure modes that decide whether a model is
usable in practice rather than merely accurate: the share of cases that
produced a well-formed answer, syntax errors, and exhausted context windows.

Parsed with the Python standard library only. No dependency, no prompt, no
credential and no model call are involved. The page is a dated publication, so
the records carry both the run's own date and the time they were read; they
are a selection prior, not acceptance evidence for this repository.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from html.parser import HTMLParser
from urllib.error import HTTPError
from urllib.request import Request

from ai_provider.http_transport import urlopen
from ai_provider.source_info import CapabilityPrior, CapabilityScore, _utc_now

SOURCE = "aider_polyglot"
BENCHMARK = "Aider polyglot"
SPLIT = "polyglot"
AGENT = "aider"
AGENT_ORG = "Aider AI"
LEADERBOARD_URL = "https://aider.chat/docs/leaderboards/"
MAX_BYTES = 2_097_152
_USER_AGENT = "ai-provider-capability-prior/1.0 (read-only metadata)"
_MODEL_FLAG = re.compile(r"--model\s+(\S+)")


class _PolyglotParser(HTMLParser):
    """Collect the published label/value pairs of one polyglot run.

    The leaderboard page holds one summary row and one collapsible details row
    per run. Only the details row carries the full published record, so the
    parser collects ``<li>`` items while inside a details row and ignores
    every other part of the page.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None
        self._label: list[str] = []
        self._value: list[str] = []
        self._in_li = False
        self._in_strong = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "tr":
            classes = (attributes.get("class") or "").split()
            identifier = attributes.get("id") or ""
            if "details-row" in classes or identifier.startswith("details-"):
                self._current = {}
                self.rows.append(self._current)
        elif self._current is not None and tag == "li":
            self._in_li = True
            self._label = []
            self._value = []
        elif self._in_li and tag == "strong":
            self._in_strong = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "tr":
            self._current = None
            self._in_li = False
        elif self._in_strong and tag == "strong":
            self._in_strong = False
        elif self._in_li and tag == "li":
            label = _clean_label("".join(self._label))
            value = " ".join("".join(self._value).split())
            if self._current is not None and label and value:
                self._current[label] = value
            self._in_li = False
            self._label = []
            self._value = []

    def handle_data(self, data: str) -> None:
        if not self._in_li:
            return
        if self._in_strong:
            self._label.append(data)
        else:
            self._value.append(data)


def _clean_label(text: str) -> str:
    return " ".join(text.split()).rstrip(":").strip()


def _count(fields: dict[str, str], label: str) -> int | None:
    raw = fields.get(label)
    if raw is None:
        return None
    try:
        value = float(raw.replace(",", ""))
    except ValueError:
        return None
    if not math.isfinite(value) or value < 0:
        return None
    return int(value)


def _percent(fields: dict[str, str], label: str) -> float | None:
    raw = fields.get(label)
    if raw is None:
        return None
    try:
        value = float(raw.rstrip("%").replace(",", ""))
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _text(fields: dict[str, str], label: str) -> str | None:
    raw = fields.get(label)
    return raw if raw else None


def _model_id(command: str) -> str | None:
    match = _MODEL_FLAG.search(command)
    return match.group(1).rstrip(",.") if match else None


def _configuration(fields: dict[str, str]) -> str | None:
    """Return the published run configuration as one comparable value.

    Edit format and reasoning effort each change the result on their own, so
    both are kept. Without them, repeated runs of the same model look like
    contradictory scores rather than different configurations.
    """

    parts = []
    edit_format = _text(fields, "Edit format")
    if edit_format is not None:
        parts.append(f"edit={edit_format}")
    reasoning = _text(fields, "Reasoning effort")
    if reasoning is not None:
        parts.append(f"reasoning={reasoning}")
    return "; ".join(parts) if parts else None


def _parse_run(
    fields: dict[str, str], *, source_url: str, observed_at_utc: str
) -> CapabilityScore | None:
    command = _text(fields, "Command")
    display = _text(fields, "Model")
    if command is None or display is None:
        return None
    model = _model_id(command)
    if model is None:
        return None
    return CapabilityScore(
        source=SOURCE,
        benchmark=BENCHMARK,
        split=SPLIT,
        model=model,
        model_display=display,
        agent=AGENT,
        agent_org=AGENT_ORG,
        score=_percent(fields, "Pass rate 2"),
        scale="percent_correct",
        configuration=_configuration(fields),
        measured_at=_text(fields, "Date"),
        cost_usd=_percent(fields, "Total cost"),
        source_url=source_url,
        observed_at_utc=observed_at_utc,
        test_cases=_count(fields, "Test cases"),
        well_formed_percent=_percent(fields, "Percent cases well formed"),
        syntax_errors=_count(fields, "Syntax errors"),
        context_exhausted=_count(fields, "Exhausted context windows"),
        prompt_tokens=_count(fields, "Prompt tokens"),
        completion_tokens=_count(fields, "Completion tokens"),
    )


def read_aider_polyglot_scores(
    *, timeout_seconds: float = 30, source_url: str = LEADERBOARD_URL
) -> CapabilityPrior:
    """Read every published polyglot run from the Aider leaderboard.

    The page is public and needs no credential. Socket timeouts bound the
    single request; callers own the total process deadline. A page that
    contains no published run is reported as unavailable rather than guessed.
    """

    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (float, int))
        or not math.isfinite(timeout_seconds)
        or timeout_seconds <= 0
    ):
        raise ValueError("Metadata timeout must be finite and positive")

    observed_at = _utc_now()
    request = Request(
        source_url, headers={"Accept": "text/html", "User-Agent": _USER_AGENT}, method="GET"
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError("Leaderboard response exceeded byte bound")
        parser = _PolyglotParser()
        parser.feed(body.decode("utf-8", "replace"))
        scores = tuple(
            score
            for score in (
                _parse_run(fields, source_url=source_url, observed_at_utc=observed_at)
                for fields in parser.rows
            )
            if score is not None
        )
        if not scores:
            raise ValueError("No published run found in the leaderboard page")
    except (OSError, ValueError, TypeError) as error:
        reason = "metadata_request_failed"
        if isinstance(error, HTTPError):
            if error.code == 404:
                reason = "source_not_found"
            elif error.code == 401:
                reason = "authentication_failed"
            elif error.code == 403:
                reason = "permission_denied"
        return CapabilityPrior(
            status="unavailable",
            source=SOURCE,
            benchmark=BENCHMARK,
            split=SPLIT,
            observed_at_utc=observed_at,
            reason=reason,
            source_url=source_url,
        )
    return CapabilityPrior(
        status="observed",
        source=SOURCE,
        benchmark=BENCHMARK,
        split=SPLIT,
        scores=scores,
        observed_at_utc=observed_at,
        reason=None,
        source_url=source_url,
    )


def main() -> int:
    """Print closed capability fields only; no raw page output."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout-seconds", type=float, default=30)
    args = parser.parse_args()
    result = read_aider_polyglot_scores(timeout_seconds=args.timeout_seconds)
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.status == "observed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
