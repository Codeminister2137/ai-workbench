"""Refresh-aware eval planning: propose explicit windows, never auto-run.

Takes an allowance-window snapshot (see ``allowance_windows``) and
proposes when to run route evals: on fresh quota right after each
bucket reset, paced per provider. Free/local routes carry no quota
and need no planning (schedule any time). The scheduler keeps
explicit-start doctrine: plans are proposals the owner starts, and
execution stops on observed spend (owner decision: observed
threshold, overshoot accepted).
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_provider.allowance_windows import AllowanceWindow

DEFAULT_EVAL_SHARE = 0.10
OPECODE_MONTHLY_WEEKS = 4.0


@dataclass(frozen=True, slots=True)
class EvalWindowProposal:
    """One proposed eval window for a single allowance bucket."""

    provider: str
    bucket_id: str
    window: str
    window_start_utc: str
    suggested_share: float
    stop_policy: str
    reason: str

    def to_json(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "bucket_id": self.bucket_id,
            "window": self.window,
            "window_start_utc": self.window_start_utc,
            "suggested_share": self.suggested_share,
            "stop_policy": self.stop_policy,
            "reason": self.reason,
        }


def _parse_instant(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _opencode_weekly_share(
    windows: list[AllowanceWindow], weekly: AllowanceWindow, now: datetime
) -> tuple[float, str]:
    """Pace opencode-go weekly evals against the monthly bucket.

    Monthly quota can burn in ~2 weeks at max pace, so the weekly
    eval share is bounded by the monthly remainder spread over the
    weeks left before its reset (at least one week).
    """
    monthly = next(
        (
            candidate
            for candidate in windows
            if candidate.provider == weekly.provider and candidate.window == "monthly"
        ),
        None,
    )
    if monthly is None or monthly.remaining_percent is None:
        return DEFAULT_EVAL_SHARE, "no monthly bucket; default share"
    reset = _parse_instant(monthly.resets_at_utc)
    if reset is None or reset <= now:
        return DEFAULT_EVAL_SHARE, "monthly reset unknown or passed; default share"
    weeks_left = max(1.0, (reset - now).total_seconds() / (7 * 24 * 3600))
    paced = (monthly.remaining_percent / 100) / weeks_left / OPECODE_MONTHLY_WEEKS
    share = max(0.0, min(DEFAULT_EVAL_SHARE, paced))
    return share, (f"monthly {monthly.remaining_percent:g}% over {weeks_left:.1f} weeks left")


def plan_eval_windows(
    windows: list[AllowanceWindow],
    *,
    now: datetime | None = None,
    eval_share: float = DEFAULT_EVAL_SHARE,
    min_remainder_percent: float = 0.0,
) -> list[EvalWindowProposal]:
    """Propose one eval window per usable bucket, earliest first.

    ``min_remainder_percent`` is the never-starve-product reserve: buckets
    with no future reset are skipped unless their current remainder meets
    it. Fresh-quota proposals are unaffected (they run after the reset).
    Zero disables the reserve; the owner sets the operating value.
    """
    moment = now or datetime.now(UTC)
    if not 0 < eval_share <= 1:
        raise ValueError("eval share must be within (0, 1]")
    if not 0 <= min_remainder_percent <= 100:
        raise ValueError("remainder reserve must be within [0, 100]")
    proposals: list[EvalWindowProposal] = []
    for window in windows:
        if window.remaining_percent is not None and window.remaining_percent <= 0:
            continue
        reset = _parse_instant(window.resets_at_utc)
        if reset is not None and reset > moment:
            start = reset
            reason = f"run on fresh quota after {window.window} reset"
            share = eval_share
        else:
            if (window.remaining_percent or 0) < min_remainder_percent:
                continue
            start = moment
            reason = "no future reset known; run on current remainder"
            share = eval_share
        if window.provider == "opencode-go" and window.window == "weekly":
            share, pace_reason = _opencode_weekly_share(windows, window, moment)
            reason = f"{reason}; paced: {pace_reason}"
        proposals.append(
            EvalWindowProposal(
                provider=window.provider,
                bucket_id=window.bucket_id,
                window=window.window,
                window_start_utc=start.isoformat(),
                suggested_share=round(share, 6),
                stop_policy="observed",
                reason=reason,
            )
        )
    proposals.sort(key=lambda proposal: proposal.window_start_utc)
    return proposals


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--windows", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--eval-share", type=float, default=DEFAULT_EVAL_SHARE)
    parser.add_argument("--min-remainder-percent", type=float, default=0.0)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("output already exists; preserve consumed plans")
    raw = json.loads(args.windows.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        parser.error("windows snapshot must be a JSON list")
    windows = [AllowanceWindow(**entry) for entry in raw]
    plan = plan_eval_windows(
        windows,
        eval_share=args.eval_share,
        min_remainder_percent=args.min_remainder_percent,
    )
    args.output.write_text(
        json.dumps([entry.to_json() for entry in plan], indent=1), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
