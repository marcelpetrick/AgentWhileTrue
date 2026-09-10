"""Bounded, redacted measurements between consecutive live observations."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from agent_watch.fsm import SupervisedSession
from agent_watch.logging_setup import EventLogger

_BLOCKED = {"LIMIT_BLOCKED", "WAITING_FOR_RESET", "RESET_GRACE_PERIOD", "READY_TO_RESUME"}
_KNOWN = _BLOCKED | {"ACTIVE", "LIMIT_WARNING"}


@dataclass
class _Sample:
    at: datetime
    monotonic: float
    blocked: bool
    start: datetime


class ObservationMetrics:
    """Batch homogeneous sampled intervals; exclude pauses, gaps and unknown state.

    These intervals measure sampled supervision, not provider execution time.
    The last unflushed minute can be lost on a crash; reports disclose partial
    coverage. No raw observation or terminal content is retained.
    """

    def __init__(self, log: EventLogger) -> None:
        self.log = log
        self.samples: dict[str, _Sample] = {}

    def _flush(self, sample: _Sample) -> None:
        if sample.at > sample.start:
            self.log.info(
                "supervision_interval", start=sample.start, end=sample.at, blocked=sample.blocked
            )
        sample.start = sample.at

    def reset(self) -> None:
        for sample in self.samples.values():
            self._flush(sample)
        self.samples.clear()

    def record(
        self, sessions: Iterable[SupervisedSession], *, monotonic: float, max_gap: float
    ) -> None:
        live: set[str] = set()
        for session in sessions:
            key = session.ref.key() + session.identity.key()
            live.add(key)
            previous = self.samples.get(key)
            at = session.observed_at
            if at is None or session.observed_state not in _KNOWN:
                if previous:
                    self._flush(previous)
                    del self.samples[key]
                continue
            if previous and at == previous.at:
                # Waiting on a timer is not a new live observation.
                continue
            blocked = session.observed_state in _BLOCKED
            if previous:
                elapsed = (at - previous.at).total_seconds()
                clock_elapsed = monotonic - previous.monotonic
                contiguous = (
                    0 < elapsed <= max_gap
                    and clock_elapsed > 0
                    and abs(elapsed - clock_elapsed) <= 1
                    and previous.blocked == blocked
                )
                if contiguous:
                    previous.at = at
                    previous.monotonic = monotonic
                    if (at - previous.start).total_seconds() >= 60:
                        self._flush(previous)
                    continue
                self._flush(previous)
            self.samples[key] = _Sample(at, monotonic, blocked, at)
        for key in self.samples.keys() - live:
            self._flush(self.samples.pop(key))
