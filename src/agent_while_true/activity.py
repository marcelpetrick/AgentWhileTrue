# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Current watcher outcomes; never a quota or authorization source."""

from dataclasses import dataclass


@dataclass(slots=True)
class RunActivity:
    approvals: int = 0
    approval_resends: int = 0
    resume_attempts: int = 0
    budget_restarts: int = 0
    capacity_recoveries: int = 0
    waits_armed: int = 0

    @property
    def unblock_actions(self) -> int:
        """Count own unblock actions, never retries or unverified work."""
        return self.approvals + self.budget_restarts + self.capacity_recoveries

    def line(self, *, compact: bool = False, narrow: bool = False) -> str:
        if narrow:
            return (
                f"RUN unblocks:{self.unblock_actions} budget:{self.budget_restarts} "
                f"capacity:{self.capacity_recoveries}"
            )
        if compact:
            return (
                f"RUN unblocks:{self.unblock_actions} approvals:{self.approvals} "
                f"budget:{self.budget_restarts} capacity:{self.capacity_recoveries} "
                f"waits:{self.waits_armed}"
            )
        return (
            f"THIS RUN | Unblock actions: {self.unblock_actions} | "
            f"Approvals sent: {self.approvals} | "
            f"Budget restarts: {self.budget_restarts} verified | "
            f"Capacity recoveries: {self.capacity_recoveries} verified | "
            f"Waits armed: {self.waits_armed}"
        )
