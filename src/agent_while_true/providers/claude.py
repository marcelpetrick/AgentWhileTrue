# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Claude Code prompt recognition.

Every pattern below was taken from the strings shipped inside the Claude Code
2.1.261 and 2.1.270 executables and cross-checked against a screenshot of a real
five-hour limit event, rather than being guessed from documentation.

The most important entry is not a limit pattern at all: since 2.1.234 Claude
Code resumes itself when the limit resets, and advertises that with
"Continuing automatically when your limit resets". When that is on screen the
supervisor must stand down, because two things pressing Enter at the same
prompt is worse than neither.

The gap the supervisor genuinely fills is the opposite case, which Claude Code
also states explicitly: a reset more than 24 hours out, or a session that was
moved to the background, will *not* resume on its own.
"""

import re
from dataclasses import replace
from datetime import datetime
from typing import Final

from agent_while_true.logging_setup import fingerprint
from agent_while_true.providers.base import (
    DEFAULT_LIVE_LINES,
    ActionKind,
    PromptKind,
    PromptPattern,
    ProviderAdapter,
    Recognition,
    ResumeAction,
    normalise_typography,
)

NAME: Final = "claude"
PATTERNS_VERSION: Final = "claude-2.1.x/10"
#: The latest release whose screens and strings were read. Only the newest
#: Claude Code release is supported; older ones are not tracked.
VERIFIED_VERSIONS: Final = ("2.1.292",)
VERIFIED_AGAINST: Final = f"Claude Code {VERIFIED_VERSIONS[-1]}"


def _pattern(text: str) -> re.Pattern[str]:
    return re.compile(text, re.IGNORECASE)


#: Claude renders "·" between the headline and the reset time. It is matched
#: loosely because the separator is cosmetic and could change.
_RESETS = r"resets?\b"

PATTERNS: Final[tuple[PromptPattern, ...]] = (
    PromptPattern(
        id="claude/limit-session",
        provider=NAME,
        kind=PromptKind.LIMIT_BLOCKED,
        scope="session",
        all_of=(_pattern(r"You've hit your session limit"),),
        note="Rolling five-hour window exhausted.",
        verified_against=VERIFIED_AGAINST,
    ),
    PromptPattern(
        id="claude/limit-weekly",
        provider=NAME,
        kind=PromptKind.LIMIT_BLOCKED,
        scope="weekly",
        all_of=(_pattern(r"You've hit your weekly limit"),),
        note="Seven-day window exhausted; a five-hour reset must not unblock it.",
        verified_against=VERIFIED_AGAINST,
    ),
    PromptPattern(
        id="claude/limit-opus",
        provider=NAME,
        kind=PromptKind.LIMIT_BLOCKED,
        scope="opus",
        all_of=(_pattern(r"You've hit your Opus limit"),),
        verified_against=VERIFIED_AGAINST,
    ),
    PromptPattern(
        id="claude/limit-sonnet",
        provider=NAME,
        kind=PromptKind.LIMIT_BLOCKED,
        scope="sonnet",
        all_of=(_pattern(r"You've hit your Sonnet limit"),),
        verified_against=VERIFIED_AGAINST,
    ),
    PromptPattern(
        id="claude/limit-fast",
        provider=NAME,
        kind=PromptKind.LIMIT_BLOCKED,
        scope="fast",
        all_of=(_pattern(r"You've hit your fast limit"),),
        verified_against=VERIFIED_AGAINST,
    ),
    PromptPattern(
        id="claude/limit-fable",
        provider=NAME,
        kind=PromptKind.LIMIT_BLOCKED,
        scope="fable",
        all_of=(_pattern(r"You've (?:hit|reached) your Fable limit"),),
        note="The Fable model window; it resets like the weekly window.",
        verified_against=VERIFIED_AGAINST,
    ),
    PromptPattern(
        id="claude/limit-generic",
        provider=NAME,
        kind=PromptKind.LIMIT_BLOCKED,
        scope="session",
        # "limit" and "usage limit" only: "usage credit limit" is a cap below.
        all_of=(_pattern(r"You've hit your (?:usage )?limit\b"),),
        note="Claude names no window when the type is unknown; it still resets.",
        verified_against=VERIFIED_AGAINST,
    ),
    PromptPattern(
        id="claude/credits-exhausted",
        provider=NAME,
        kind=PromptKind.PAID_ACTION_REQUIRED,
        scope="credits",
        all_of=(
            _pattern(
                r"You've hit your usage credit limit|You're out of (?:usage credits|extra usage)"
                r"|Fable 5 requires usage credits"
            ),
        ),
        note="Credits, not a window: no wait ends it. Never automated.",
        verified_against=VERIFIED_AGAINST,
    ),
    PromptPattern(
        id="claude/admin-limit",
        provider=NAME,
        kind=PromptKind.PAID_ACTION_REQUIRED,
        scope="admin",
        all_of=(
            _pattern(
                r"You've hit your (?:org's|channel's|team's|individual) "
                r"|Your org is out of usage|Your seat type doesn't include"
                r"|Your usage allocation has been disabled|Your group's usage limit is set to \$0"
            ),
        ),
        note="An admin's or organisation's cap: only an admin or money lifts it. Never automated.",
        verified_against=VERIFIED_AGAINST,
    ),
    PromptPattern(
        id="claude/limit-banner",
        provider=NAME,
        kind=PromptKind.LIMIT_BLOCKED,
        scope="session",
        all_of=(_pattern(r"Usage limit reached"),),
        note="Generic banner; carries the reset time.",
        verified_against=VERIFIED_AGAINST,
    ),
    PromptPattern(
        id="claude/arm-automatic-wait",
        provider=NAME,
        kind=PromptKind.LIMIT_BLOCKED,
        scope="session",
        all_of=(
            _pattern(
                r"\N{HEAVY RIGHT-POINTING ANGLE QUOTATION MARK ORNAMENT}"
                r"\s*1\.\s*Stop and wait for limit to reset"
            ),
            _pattern(r"2\.\s*Wait here, then continue automatically"),
            _pattern(r"Enter to confirm"),
        ),
        action=ResumeAction(
            kind=ActionKind.ARROW_DOWN_THEN_ENTER,
            requires_policy="allow_claude_auto_wait",
        ),
        note="Exact menu and cursor position required; selects only Claude's own wait mode.",
        verified_against=VERIFIED_AGAINST,
    ),
    PromptPattern(
        id="claude/ready-press-enter",
        provider=NAME,
        kind=PromptKind.READY_TO_RESUME,
        scope="session",
        # Anchored to the whole rendered line. Claude prints this affordance as
        # a line of its own under the assistant marker; the same words inside a
        # sentence - an agent *talking about* the prompt, a quoted doc, a log
        # line - are not the prompt, and one such quote in a live session was
        # recognised as READY_TO_RESUME on 2026-09-18. The gate additionally
        # requires that this process was seen blocked first (policy.py).
        all_of=(
            re.compile(
                r"^\s*(?:\N{BLACK CIRCLE}\s*)?Usage limit (?:has reset|reset|available again)"
                r"\s*(?:\N{MIDDLE DOT}\s*)?press enter to continue\s*$",
                re.IGNORECASE | re.MULTILINE,
            ),
        ),
        # The provider states the expected input in so many words, so the action
        # is a bare Enter. The literal word "continue" is never typed: at this
        # prompt it would be echoed into the composer rather than accepted.
        action=ResumeAction(kind=ActionKind.ENTER),
        note="The reset headline and affordance must form one whole screen line.",
        verified_against=VERIFIED_AGAINST,
    ),
    PromptPattern(
        id="claude/self-healing",
        provider=NAME,
        kind=PromptKind.SELF_HEALING,
        scope="session",
        all_of=(_pattern(r"[Cc]ontinuing automatically when (?:your limit|it) resets"),),
        note="Claude Code 2.1.234+ resumes itself; the supervisor must stand down.",
        verified_against=VERIFIED_AGAINST,
    ),
    PromptPattern(
        id="claude/self-healing-timed",
        provider=NAME,
        kind=PromptKind.SELF_HEALING,
        scope="session",
        all_of=(
            # Claude drops zero minutes ("7pm") and prefixes a date to a reset
            # more than a day out ("Oct 3, 7pm"); both are the same armed wait.
            _pattern(
                r"(?:Claude Code will continue|continuing) automatically at "
                r"(?:[A-Z][a-z]{2} \d{1,2}, )?\d{1,2}(?:[:.]\d{2})?\s?(?:am|pm)"
            ),
        ),
        note="Timed automatic wait is already armed; the supervisor must stand down.",
        verified_against=VERIFIED_AGAINST,
    ),
    PromptPattern(
        id="claude/self-healing-soon",
        provider=NAME,
        kind=PromptKind.SELF_HEALING,
        scope="session",
        all_of=(_pattern(r"(?:Claude Code will continue|continuing) automatically shortly"),),
        note="2.1.278 arms its own wait without naming a time; the supervisor must stand down.",
        verified_against=VERIFIED_AGAINST,
    ),
    PromptPattern(
        id="claude/self-healing-status",
        provider=NAME,
        kind=PromptKind.SELF_HEALING,
        scope="session",
        # The status line of an already-armed wait. Matched separately from the
        # sentence above because the sentence scrolls away while this stays.
        all_of=(_pattern(r"continuing shortly.{0,4}esc to cancel"),),
        note="Status line of an armed 2.1.278 wait.",
        verified_against=VERIFIED_AGAINST,
    ),
    PromptPattern(
        id="claude/will-not-self-resume",
        provider=NAME,
        kind=PromptKind.WILL_NOT_SELF_RESUME,
        scope="session",
        all_of=(_pattern(r"will not resume on its own"),),
        note="Reset more than 24h out, or the session was backgrounded.",
        verified_against=VERIFIED_AGAINST,
    ),
    PromptPattern(
        id="claude/tool-approval",
        provider=NAME,
        kind=PromptKind.APPROVAL_REQUESTED,
        scope="approval",
        # "Do you want to proceed?", "... overwrite <file>?", "... create
        # <file>?" and the like. Both anchors are whole screen lines, so an
        # agent quoting the prompt
        # inside a sentence is not the prompt. Any menu shape counts here: this
        # pattern only names the state. Which shape an operator may answer is
        # decided by _approval_block below.
        all_of=(
            re.compile(r"^\s*Do you want to \S.{0,200}\?\s*$", re.IGNORECASE | re.MULTILINE),
            re.compile(
                r"^\s*(?:\N{HEAVY RIGHT-POINTING ANGLE QUOTATION MARK ORNAMENT}\s*)?1\.\s*Yes\b",
                re.IGNORECASE | re.MULTILINE,
            ),
        ),
        note="Tool permission request. Never answered automatically.",
        verified_against=VERIFIED_AGAINST,
    ),
    PromptPattern(
        id="claude/spend-limit",
        provider=NAME,
        kind=PromptKind.PAID_ACTION_REQUIRED,
        scope="spend",
        all_of=(_pattern(r"You've hit your monthly spend limit"),),
        note="Money. Never automated.",
        verified_against=VERIFIED_AGAINST,
    ),
    PromptPattern(
        id="claude/usage-credits-offer",
        provider=NAME,
        kind=PromptKind.PAID_ACTION_REQUIRED,
        scope="credits",
        all_of=(_pattern(r"(?<![\w/])/(?:upgrade|usage-credits|extra-usage)\b"),),
        note="Offers paid continuation. Never automated.",
        verified_against=VERIFIED_AGAINST,
    ),
    PromptPattern(
        id="claude/upgrade-plan-offer",
        provider=NAME,
        kind=PromptKind.PAID_ACTION_REQUIRED,
        scope="credits",
        all_of=(_pattern(r"Upgrade your plan"),),
        note="Interactive paid upgrade choice. Never selected automatically.",
        verified_against=VERIFIED_AGAINST,
    ),
    PromptPattern(
        id="claude/session-limit-reset",
        provider=NAME,
        kind=PromptKind.PAID_ACTION_REQUIRED,
        scope="reset-credit",
        all_of=(_pattern(r"Reset your session limit now"),),
        note="Consumes the provider's limited early-reset affordance. Never automated.",
        verified_against=VERIFIED_AGAINST,
    ),
    PromptPattern(
        id="claude/lower-priority",
        provider=NAME,
        kind=PromptKind.MODEL_DOWNGRADE_OFFER,
        scope="model",
        all_of=(_pattern(r"Continue now at lower priority"),),
        note="Changes service quality. Never automated.",
        verified_against=VERIFIED_AGAINST,
    ),
    PromptPattern(
        id="claude/model-downgrade",
        provider=NAME,
        kind=PromptKind.MODEL_DOWNGRADE_OFFER,
        scope="model",
        all_of=(_pattern(r"Switch to another model"),),
        note="Silently changes output quality. Never automated.",
        verified_against=VERIFIED_AGAINST,
    ),
)


class ClaudeAdapter(ProviderAdapter):
    """Recognises Claude Code's usage-limit prompts."""

    name = NAME
    patterns_version = PATTERNS_VERSION
    verified_versions = VERIFIED_VERSIONS

    @property
    def patterns(self) -> tuple[PromptPattern, ...]:
        return PATTERNS

    def executable_names(self) -> frozenset[str]:
        return frozenset({"claude"})

    def recognise(
        self,
        lines: list[str],
        *,
        now: datetime,
        live_lines: int = DEFAULT_LIVE_LINES,
    ) -> Recognition:
        """Recognise only the newest Claude turn or blocking prompt region.

        Konsole's visible screen can retain a complete paid-offer block above a
        later working turn. Claude's assistant marker or a submitted composer
        line starts a new region. An empty composer and the exact menu cursor
        do not: both belong to the blocking prompt immediately above them.
        Earlier limit scopes in one region remain useful, but command links
        before its newest limit headline are historical and cannot veto.
        """
        latest_turn = 0
        menu_cursor = re.compile(
            r"^\s*\N{HEAVY RIGHT-POINTING ANGLE QUOTATION MARK ORNAMENT}"
            r"\s*1\.\s*Stop and wait for limit to reset",
            re.IGNORECASE,
        )
        submitted = re.compile(r"^\s*\N{HEAVY RIGHT-POINTING ANGLE QUOTATION MARK ORNAMENT}\s+\S")
        # Any numbered item of a permission menu may carry the cursor, and
        # the menu belongs to the question just above it, not to a new turn.
        approval_cursor = re.compile(
            r"^\s*\N{HEAVY RIGHT-POINTING ANGLE QUOTATION MARK ORNAMENT}\s*[1-9]\.\s"
        )
        question = -APPROVAL_MENU_ROWS - 1
        limit_headline = re.compile(
            r"You've (?:hit|reached) your "
            r"(?:(?:session|weekly|Opus|Sonnet|fast|Fable|usage) )?limit",
            re.IGNORECASE,
        )
        for index, line in enumerate(lines):
            stripped = line.lstrip()
            if _APPROVAL_QUESTION.match(normalise_typography(line)):
                question = index
            in_menu = (
                bool(approval_cursor.search(line)) and 0 < index - question <= APPROVAL_MENU_ROWS
            )
            if stripped.startswith("●") or (
                submitted.search(line) and not menu_cursor.search(line) and not in_menu
            ):
                latest_turn = index
        live = lines[latest_turn:]
        latest_limit = 0
        for index, line in enumerate(live):
            if limit_headline.search(normalise_typography(line)):
                latest_limit = index
        scoped = [
            re.sub(r"/(?:upgrade|usage-credits|extra-usage)\b", "/historical-command", line)
            if index < latest_limit
            else line
            for index, line in enumerate(live)
        ]
        result = super().recognise(scoped, now=now, live_lines=live_lines)
        block = _approval_block(lines)
        return replace(
            result,
            composer_empty=_composer_empty(lines),
            approval_prompt=block is not None,
            approval_fingerprint=fingerprint(block) if block is not None else "",
        )


#: Claude draws its composer cursor with this glyph; the menu cursor uses it too.
_COMPOSER_GLYPH = "\N{HEAVY RIGHT-POINTING ANGLE QUOTATION MARK ORNAMENT}"
#: The composer sits at the bottom, under at most a rule and a status line or
#: two. A cursor glyph further up is a submitted turn, not the input box.
CLAUDE_COMPOSER_ROWS: Final = 6
#: The horizontal rule Claude draws above and below its input box.
_RULE_ROW = re.compile(r"^\s*[\u2500\u2501\u2581\u2594]{8,}\s*$")
#: Claude Code 2.1.292 lists running subagents under its status lines: the
#: main thread row first, then one row per agent, the selected one filled.
_AGENT_PANEL_MAIN = re.compile(r"^\s*[\u25cf\u25ef]\s+main\s*$")
_AGENT_PANEL_ROW = re.compile(r"^\s*[\u25cf\u25ef]\s+\S")


def _without_agent_panel(lines: list[str], end: int) -> int:
    """The end of ``lines[:end]`` once a trailing background-agent panel is cut.

    Only the exact tested shape is cut: a blank row, the ``main`` row, then
    agent rows down to the bottom. Anything else leaves ``end`` unchanged, so
    an unknown panel row keeps the composer out of reach and fails closed.
    """
    index = end
    while (
        index
        and _AGENT_PANEL_ROW.match(lines[index - 1])
        and not _AGENT_PANEL_MAIN.match(lines[index - 1])
    ):
        index -= 1
    if index < 2 or not _AGENT_PANEL_MAIN.match(lines[index - 1]) or lines[index - 2].strip():
        return end
    index -= 2
    while index and not lines[index - 1].strip():
        index -= 1
    return index


def _composer_empty(lines: list[str]) -> bool:
    """True only when the newest cursor row near the bottom is an empty composer.

    A draft, a placeholder suggestion and a menu cursor all carry text after
    the glyph and are therefore not empty; so is a screen without the glyph.
    The row right below the cursor must be the input box's closing rule: a
    multi-line draft begun with Shift+Enter leaves the cursor row empty and puts
    its text on continuation rows, which only that rule tells apart from the
    status line. A background-agent panel below the status lines is chrome
    and is cut first.
    """
    end = len(lines)
    while end and not lines[end - 1].strip():
        end -= 1
    end = _without_agent_panel(lines, end)
    for index in range(end - 1, max(0, end - CLAUDE_COMPOSER_ROWS) - 1, -1):
        stripped = lines[index].strip()
        if stripped.startswith(_COMPOSER_GLYPH):
            if stripped[len(_COMPOSER_GLYPH) :].strip():
                return False
            return index + 1 < end and bool(_RULE_ROW.match(lines[index + 1]))
    return False


#: How many rows below the question a menu item may sit: three items, one
#: wrapped row of item 2, and room for a blank row.
APPROVAL_MENU_ROWS: Final = 6
#: How far above the menu the permission box's top rule may sit. The box holds
#: a tool header, the command or diff, and a sentence or two; a rule further up
#: belongs to something else, and then the shape is not the tested one.
APPROVAL_BOX_ROWS: Final = 40
_APPROVAL_FOOTER = re.compile(
    r"^\s*Esc to cancel(?:\s*\N{MIDDLE DOT}\s*Tab to amend)?\s*$", re.IGNORECASE
)
_APPROVAL_YES = re.compile(rf"^\s*{_COMPOSER_GLYPH}\s*1\.\s*Yes\s*$")
_APPROVAL_YES_AND = re.compile(r"^\s*2\.\s*Yes, and\s+\S")
_APPROVAL_NO = re.compile(r"^\s*(?P<number>[23])\.\s*No(?:\s*$|,\s)")
_APPROVAL_ITEM = re.compile(r"^\s*\d+\.\s")
#: "Do you want to proceed?", "... overwrite settings.local.json?",
#: "... create notes.md?", "... make this edit to cli.py?": one whole row.
_APPROVAL_QUESTION = re.compile(r"^\s*Do you want to \S.{0,200}\?\s*$")
#: The dashed rule Claude draws between a file preview and the question.
_DASHED_ROW = re.compile(r"^\s*[\u254c\u2504\u2508]{8,}\s*$")


def _approval_block(lines: list[str]) -> list[str] | None:
    """The exact tested permission box at the bottom of the screen, or None.

    Reading upwards from the last non-blank row it must find, each on rows of
    their own: the "Esc to cancel" footer, blank rows, the last item "No"
    (item 2, or item 3 with "No, and tell Claude ..."), for three items a
    "2. Yes, and ..." item whose text may wrap, the cursor on "1. Yes", and a
    "Do you want to ...?" question. Above the question sits the box's solid
    top rule, or - when a file preview fills the window - the dashed rule
    right above the question. The cursor anywhere else, a fourth item, a
    reworded item or text below the footer is another shape and yields None.
    Enter on this shape selects item 1, the one-time "Yes"; a "Yes, and ..."
    item is never reached.
    """
    end = len(lines)
    while end and not lines[end - 1].strip():
        end -= 1
    if end < 4 or not _APPROVAL_FOOTER.match(normalise_typography(lines[end - 1])):
        return None
    row = end - 2
    while row >= 0 and not lines[row].strip():
        row -= 1
    last = _APPROVAL_NO.match(lines[row]) if row >= 0 else None
    if last is None:
        return None
    row -= 1
    if last.group("number") == "3":
        # Item 2 and the rows it wrapped onto, none of which is an item.
        while row >= 0 and not _APPROVAL_YES_AND.match(lines[row]):
            if _APPROVAL_ITEM.match(lines[row]) or _COMPOSER_GLYPH in lines[row]:
                return None
            if not lines[row].strip() or end - row > APPROVAL_MENU_ROWS + 2:
                return None
            row -= 1
        if row < 0 or _COMPOSER_GLYPH in lines[row]:
            return None
        row -= 1
    if row < 1 or not _APPROVAL_YES.match(lines[row]):
        return None
    question = row - 1
    if not _APPROVAL_QUESTION.match(normalise_typography(lines[question])):
        return None
    for top in range(question - 1, max(-1, question - 1 - APPROVAL_BOX_ROWS), -1):
        if _RULE_ROW.match(lines[top]):
            return lines[top:end]
    if question >= 1 and _DASHED_ROW.match(lines[question - 1]):
        # The preview fills the window, so nothing above it can redraw: the
        # visible preview rows are part of what is being approved.
        return lines[max(0, question - 1 - APPROVAL_BOX_ROWS) : end]
    return None
