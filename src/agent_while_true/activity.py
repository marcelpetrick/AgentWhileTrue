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
    waits_armed: int = 0

    def line(self, *, compact: bool = False) -> str:
        if compact:
            return (
                f"RUN approvals:{self.approvals} restarts:{self.budget_restarts} "
                f"waits:{self.waits_armed}"
            )
        return (
            f"THIS RUN | Approvals sent: {self.approvals} | "
            f"Budget restarts: {self.budget_restarts} verified | Waits armed: {self.waits_armed}"
        )
