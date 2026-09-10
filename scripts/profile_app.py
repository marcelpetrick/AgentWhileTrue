# SPDX-FileCopyrightText: 2026 Marcel Petrick
# SPDX-License-Identifier: GPL-3.0-or-later
"""Reproducible, privacy-safe profile of representative application work."""

from __future__ import annotations

import argparse
import cProfile
import json
import os
import pstats
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent_watch.config import Config  # noqa: E402
from agent_watch.fsm import SupervisedSession  # noqa: E402
from agent_watch.logging_setup import read_history  # noqa: E402
from agent_watch.proc import ProcessIdentity  # noqa: E402
from agent_watch.quota import ClaudeStatuslineSource, _last_rate_limits  # noqa: E402
from agent_watch.simulate import run_all  # noqa: E402
from agent_watch.summary import render_summary  # noqa: E402
from agent_watch.terminal.base import SessionRef  # noqa: E402
from agent_watch.ui import render_status  # noqa: E402

NOW = datetime(2026, 9, 5, 20, 0, tzinfo=UTC)


def _sessions() -> list[SupervisedSession]:
    return [
        SupervisedSession(
            ref=SessionRef("konsole", "org.kde.konsole-1", f"/Sessions/{index}"),
            identity=ProcessIdentity(index + 15000, 1, f"pts/{index}", "/opt/claude"),
            provider_name="claude",
            title=f"synthetic-project-{index}-" + "x" * 80,
        )
        for index in range(12)
    ]


def workload(
    iterations: int,
    directory: Path,
    render_frames: int | None = None,
    render_width: int | None = None,
) -> dict[str, float]:
    """Exercise scans, dashboard widths, and bounded local-state reads."""
    timings: dict[str, float] = {}
    sessions = _sessions()
    events = [
        f"event=observed provider=claude id={index} result=safe-summary" for index in range(50)
    ]
    history = directory / "history.log"
    log_rows = [
        f"2026-09-05 19:{index % 60:02d}:00,000 INFO event=resume_sent provider=claude"
        for index in range(10_000)
    ]
    history.write_text("\n".join(log_rows) + "\n", encoding="utf-8")
    quota = directory / "quota.json"
    quota.write_text(
        json.dumps(
            {
                "updated_at": int(NOW.timestamp()),
                "five_hour": {"used_percentage": 57, "resets_at": int(NOW.timestamp()) + 3600},
                "seven_day": {"used_percentage": 40, "resets_at": int(NOW.timestamp()) + 86400},
            }
        ),
        encoding="utf-8",
    )
    rollout = directory / "rollout-synthetic.jsonl"
    filler = json.dumps({"type": "event_msg", "payload": {"message": "synthetic"}})
    limit_event = json.dumps(
        {
            "timestamp": NOW.isoformat(),
            "payload": {
                "rate_limits": {
                    "primary": {"used_percent": 57, "window_minutes": 300},
                    "secondary": {"used_percent": 40, "window_minutes": 10080},
                }
            },
        }
    )
    rollout.write_text("\n".join([filler] * 49_999 + [limit_event]), encoding="utf-8")

    started = time.perf_counter()
    for index in range(iterations):
        results = run_all(directory / f"scan-{index}")
        assert all(result.passed for result in results)
    timings["safety_simulations"] = time.perf_counter() - started

    started = time.perf_counter()
    widths = (render_width,) if render_width is not None else (40, 100, 168, 220)
    frames = render_frames if render_frames is not None else iterations * 10 * len(widths)
    for frame in range(frames):
        for width in (widths[frame % len(widths)],):
            rendered = render_status(
                sessions,
                now=NOW,
                config=Config(),
                width=width,
                events=events,
                history_length=50,
                show_help=True,
                show_details=True,
            )
            assert rendered
    timings["rendering"] = time.perf_counter() - started

    started = time.perf_counter()
    source = ClaudeStatuslineSource(quota)
    for _ in range(iterations * 100):
        assert len(read_history(history, limit=50)) == 50
        assert source.snapshot().windows
        assert _last_rate_limits(rollout)
    timings["quota_history_reads"] = time.perf_counter() - started

    started = time.perf_counter()
    for _ in range(iterations):
        summary = render_summary(history, now=NOW, days=1)
        assert "sent=10000" in summary
    timings["retained_log_summary"] = time.perf_counter() - started
    return timings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--render-frames", type=int)
    parser.add_argument("--render-width", type=int)
    parser.add_argument("--profile", type=Path, help="optionally retain cProfile data")
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("--iterations must be positive")
    if args.render_frames is not None and args.render_frames < 1:
        parser.error("--render-frames must be positive")
    if args.render_width is not None and args.render_width < 1:
        parser.error("--render-width must be positive")
    with tempfile.TemporaryDirectory(prefix="agent-watch-profile-") as temporary:
        profiler = cProfile.Profile()
        timings = profiler.runcall(
            workload,
            args.iterations,
            Path(temporary),
            args.render_frames,
            args.render_width,
        )
    if args.profile:
        args.profile.parent.mkdir(parents=True, exist_ok=True)
        profiler.dump_stats(args.profile)
    stats = pstats.Stats(profiler).strip_dirs().sort_stats("cumulative")
    root_note = " Running as root remains synthetic/read-only." if os.geteuid() == 0 else ""
    print(
        "Synthetic inputs only; no terminal text, environment, or credentials were read."
        + root_note
    )
    rendered_timings = " ".join(f"{name}={seconds:.6f}" for name, seconds in timings.items())
    print("timings_seconds " + rendered_timings)
    stats.print_stats(15)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
