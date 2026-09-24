# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Codex CLI prompt recognition.

Patterns were taken from the strings shipped inside the Codex CLI 0.153.2
binary. Codex differs from Claude Code in one way that matters a great deal
here: it offers no "press enter to continue" affordance. When a Codex turn is
cut short by a usage limit the TUI returns to its composer, so resuming means
*typing* rather than pressing a key.

Typing is strictly more dangerous than pressing Enter, because if the foreground
process changed in the meantime the text lands in a shell. Codex resume is
therefore gated behind its own policy flag and stays off in auto mode until the
user opts in, even though the rest of the machinery is identical.
"""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime
from typing import Final

from agent_while_true.providers.base import (
    ActionKind,
    PromptKind,
    PromptPattern,
    ProviderAdapter,
    Recognition,
    ResumeAction,
    normalise_typography,
)

NAME: Final = "codex"
PATTERNS_VERSION: Final = "codex-0.155.x/6"
#: Versions whose screens were actually read, oldest first.
VERIFIED_VERSIONS: Final = ("0.153.2", "0.153.4", "0.154.0", "0.155.1")
VERIFIED_AGAINST: Final = (
    f"Codex CLI {', '.join(VERIFIED_VERSIONS[:-1])} and {VERIFIED_VERSIONS[-1]}"
)

# Codex's compact blocking composer fits inside eight rows, including the
# wrapped purchase links seen in 0.153.4. A wider generic window retained the
# old banner after a continued turn and could propose duplicate input.
CODEX_LIVE_LINES: Final = 8

#: What is typed into the composer to pick the work back up. Deliberately a
#: plain instruction with no slash command: a slash command that has been
#: renamed would silently do something else.
DEFAULT_RESUME_TEXT: Final = "continue"


def _pattern(text: str) -> re.Pattern[str]:
    return re.compile(text, re.IGNORECASE)


#: Codex 0.154 animates a field of Braille-pattern "particles" (U+2800-U+28FF)
#: across the composer rows. They are decoration: they never carry a word of
#: the prompt, they sit on the same row as the placeholder so the composer no
#: longer strips to its tested text, and they change on every frame so the
#: screen fingerprint would never be stable. Removing the block before any
#: comparison restores both the exact composer match and a stable fingerprint.
_BRAILLE_PARTICLES = re.compile(r"[\u2800-\u28ff]")


def _without_particles(lines: list[str]) -> list[str]:
    return [_BRAILLE_PARTICLES.sub("", line) for line in lines]


PATTERNS: Final[tuple[PromptPattern, ...]] = (
    PromptPattern(
        id="codex/limit-usage",
        provider=NAME,
        kind=PromptKind.LIMIT_BLOCKED,
        scope="usage",
        all_of=(_pattern(r"You've hit your usage limit"),),
        action=ResumeAction(
            kind=ActionKind.TEXT_THEN_ENTER,
            text=DEFAULT_RESUME_TEXT,
            requires_policy="allow_codex_auto_resume",
        ),
        note="Codex returns to the composer; resuming means typing.",
        verified_against=VERIFIED_AGAINST,
    ),
    PromptPattern(
        id="codex/limit-banner",
        provider=NAME,
        kind=PromptKind.LIMIT_BLOCKED,
        scope="usage",
        all_of=(_pattern(r"Usage limit reached"),),
        action=ResumeAction(
            kind=ActionKind.TEXT_THEN_ENTER,
            text=DEFAULT_RESUME_TEXT,
            requires_policy="allow_codex_auto_resume",
        ),
        verified_against=VERIFIED_AGAINST,
    ),
    PromptPattern(
        id="codex/try-again-at",
        provider=NAME,
        kind=PromptKind.WILL_NOT_SELF_RESUME,
        scope="usage",
        all_of=(_pattern(r"Try again at\b"),),
        note="Carries the reset time; Codex never resumes on its own.",
        verified_against=VERIFIED_AGAINST,
    ),
    PromptPattern(
        id="codex/approaching-limit",
        provider=NAME,
        kind=PromptKind.LIMIT_WARNING,
        scope="usage",
        all_of=(_pattern(r"Approaching rate limits"),),
        verified_against=VERIFIED_AGAINST,
    ),
    PromptPattern(
        id="codex/out-of-credits",
        provider=NAME,
        kind=PromptKind.PAID_ACTION_REQUIRED,
        scope="credits",
        all_of=(_pattern(r"(?:You're|Your workspace is) out of credits"),),
        note="Money. Never automated.",
        verified_against=VERIFIED_AGAINST,
    ),
    PromptPattern(
        id="codex/workspace-credit-limit",
        provider=NAME,
        kind=PromptKind.PAID_ACTION_REQUIRED,
        scope="credits",
        all_of=(_pattern(r"reached your workspace credit limit"),),
        verified_against=VERIFIED_AGAINST,
    ),
    PromptPattern(
        id="codex/purchase-offer",
        provider=NAME,
        kind=PromptKind.PAID_ACTION_REQUIRED,
        scope="credits",
        all_of=(_pattern(r"purchase more credits|Upgrade to (?:Plus|Pro)\b"),),
        verified_against=VERIFIED_AGAINST,
    ),
    PromptPattern(
        id="codex/limit-increase-request",
        provider=NAME,
        kind=PromptKind.PAID_ACTION_REQUIRED,
        scope="credits",
        all_of=(_pattern(r"Request (?:a limit increase|an? increase)|Request increase\?"),),
        note="Sends a request to a workspace admin. Never automated.",
        verified_against=VERIFIED_AGAINST,
    ),
    PromptPattern(
        id="codex/reset-credit-offer",
        provider=NAME,
        kind=PromptKind.PAID_ACTION_REQUIRED,
        scope="reset-credit",
        all_of=(_pattern(r"Redeem usage limit reset|usage limit resets? available"),),
        note="Consumes a finite earned reset. Never automated.",
        verified_against=VERIFIED_AGAINST,
    ),
    PromptPattern(
        id="codex/model-downgrade",
        provider=NAME,
        kind=PromptKind.MODEL_DOWNGRADE_OFFER,
        scope="model",
        all_of=(_pattern(r"Keep current model|Uses fewer credits for upcoming turns"),),
        verified_against=VERIFIED_AGAINST,
    ),
)


class CodexAdapter(ProviderAdapter):
    """Recognises Codex CLI's usage-limit prompts."""

    name = NAME
    patterns_version = PATTERNS_VERSION
    verified_versions = VERIFIED_VERSIONS

    @property
    def patterns(self) -> tuple[PromptPattern, ...]:
        return PATTERNS

    def executable_names(self) -> frozenset[str]:
        return frozenset({"codex"})

    def recognise(
        self,
        lines: list[str],
        *,
        now: datetime,
        live_lines: int = CODEX_LIVE_LINES,
    ) -> Recognition:
        """Restrict Codex decisions to its immediate prompt area."""
        lines = _without_particles(lines)
        result = super().recognise(lines, now=now, live_lines=live_lines)
        live = lines[-live_lines:]
        # Timed trials require the tested empty composer (or its known
        # placeholder), not merely quoted limit words or a draft being edited.
        composer = next(
            (
                index
                for index in range(len(live) - 1, -1, -1)
                if live[index].strip().startswith("\N{SINGLE RIGHT-POINTING ANGLE QUOTATION MARK}")
            ),
            -1,
        )
        # Compare what follows the glyph, with whitespace normalised. A particle
        # drawn in the space after the glyph leaves the glyph glued to the
        # placeholder once removed, and one drawn next to that space leaves a
        # double space; the placeholder is the same placeholder either way.
        body = (
            " ".join(
                live[composer].split("\N{SINGLE RIGHT-POINTING ANGLE QUOTATION MARK}", 1)[1].split()
            )
            if composer >= 0
            else None
        )
        empty = body in {"", "Ask Codex to do anything"}
        banner = next(
            (
                index
                for index, line in enumerate(live)
                # Folded like every other comparison: 0.155 writes U+2019 here,
                # and an unfolded anchor silently disabled the bounded retry.
                if re.match(r"^\s*[▌■]\s+You've hit your usage limit\.", normalise_typography(line))
            ),
            -1,
        )
        exact = (
            empty
            and banner >= 0
            and banner < composer
            and result.reset_at is not None
            and {"codex/limit-usage", "codex/try-again-at"}.issubset(result.matched_ids)
            and not any(
                re.search(r"\b(?:Working|Explored|Ran|Thinking)\b", line)
                for line in live[banner + 1 :]
            )
        )
        active = any(
            re.match(r"^\s*[•●]\s+(?:Working|Explored|Ran|Thinking|Finished)\b", line)
            for line in live
        )
        active_rows = [index for index, line in enumerate(live) if re.match(r"^\s*[•●]\s+", line)]
        if active_rows and active_rows[-1] > banner:
            # New assistant output below a historical limit is a different
            # turn, even before that old banner scrolls out of the live window.
            result = super().recognise(live[active_rows[-1] :], now=now, live_lines=live_lines)
            exact = False
            active = True
        return replace(
            result,
            retry_prompt=exact,
            active_evidence=active,
            input_ready=empty,
            composer_empty=empty,
        )
