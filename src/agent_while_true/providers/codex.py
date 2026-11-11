# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Codex CLI prompt recognition.

Patterns are checked against recorded Codex CLI strings and live screens.
Codex differs from Claude Code in one way that
matters a great deal here: it offers no "press enter to continue" affordance.
When a Codex turn is cut short by a usage limit the TUI returns to its
composer, so resuming means *typing* rather than pressing a key.

Typing is strictly more dangerous than pressing Enter, because if the foreground
process changed in the meantime the text lands in a shell. Codex resume is
therefore gated behind its own policy flag and stays off in auto mode until the
user opts in, even though the rest of the machinery is identical.
"""

import re
from dataclasses import replace
from datetime import datetime
from typing import Final

from agent_while_true.logging_setup import fingerprint
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
PATTERNS_VERSION: Final = "codex-0.167-keep-model/14"
#: The latest release whose screens and strings were read. Only the newest
#: Codex CLI release is supported; older ones are not tracked.
VERIFIED_VERSIONS: Final = ("0.162.1",)
VERIFIED_AGAINST: Final = f"Codex CLI {VERIFIED_VERSIONS[-1]}"

# Codex's compact blocking composer fits inside eight rows, including the
# wrapped purchase links seen in 0.153.4. A wider generic window retained the
# old banner after a continued turn and could propose duplicate input.
CODEX_LIVE_LINES: Final = 8

#: What is typed into the composer to pick the work back up. Deliberately a
#: plain instruction with no slash command: a slash command that has been
#: renamed would silently do something else.
DEFAULT_RESUME_TEXT: Final = "continue"
_MENU_GLYPH = "\N{SINGLE RIGHT-POINTING ANGLE QUOTATION MARK}"

_APPROVAL_TITLE_TEXT = (
    r"Would\s+you\s+like\s+to\s+run\s+the\s+following\s+command\?"
    r"|Would\s+you\s+like\s+to\s+make\s+the\s+following\s+edits\?"
    r"|Would\s+you\s+like\s+to\s+send\s+input\s+to\s+(?:the\s+existing\s+)?"
    r"terminal(?:\s+\d+)?\?"
    r'|Do\s+you\s+want\s+to\s+approve\s+network\s+access\s+to\s+"[^"\r\n]{1,253}"\?'
    r"|Would\s+you\s+like\s+to\s+grant\s+these\s+permissions\?"
)
_APPROVAL_FOOTER_TEXT = (
    r"Press\s+enter\s+to\s+confirm\s+or\s+esc\s+to\s+cancel"
    r"(?:\s+or\s+o\s+to\s+open\s+thread)?"
)


def _pattern(text: str) -> re.Pattern[str]:
    return re.compile(text, re.IGNORECASE)


#: Codex 0.154 animates a field of Braille-pattern "particles" (U+2800-U+28FF)
#: across the composer rows. They are decoration: they never carry a word of
#: the prompt, they sit on the same row as the placeholder so the composer no
#: longer strips to its tested text, and they change on every frame so the
#: screen fingerprint would never be stable. Recognition can remove particles
#: for observation, but input refuses particles in the current prompt area
#: because they can obscure text or be draft text. Approval previews use
#: the original screen for recognition and fingerprinting.
_BRAILLE_PARTICLES = re.compile(r"[\u2800-\u28ff]")


#: What Codex prints under its composer: the model/directory footer with its
#: usage figure, or the key hints. A middle dot alone is not enough - a draft's
#: continuation row can contain one - so anything else below an empty composer
#: refuses a whip.
#: 0.158 also writes "Context 93% left" and, while a turn runs, the
#: "tab to queue message" hint. 0.160 can append its exact warning counter to
#: the shortcuts row, or show its exact Plan-mode cycle hint without a context
#: percentage. Those are status chrome, not composer text.
_CODEX_FOOTER = re.compile(
    r"^\s*(?:(?:gpt|codex|o\d)[\w.-]*\s+(?:default|low|medium|high|xhigh|max|ultra)"
    r"\s+·\s+(?:~|/)\S+\s+·\s+\d{1,3}% (?:used|left|context left)"
    r"(?:\s+·\s+resets\s+\d{1,2}:\d{2}\s*[AP]M)?"
    r"|(?:← for agents\s+·\s+)?\? for shortcuts"
    r"(?:\s+⚠\s+\d+\s+warnings?\s+·\s+f2 to view)?"
    r"|tab to queue message"
    r"|(?:gpt[\w.-]*\s+(?:default|low|medium|high|xhigh|max|ultra)\s+)?"
    r"Plan mode \(shift\+tab to cycle\)(?:\s+·\s+IDE context)?"
    r")\s*$",
    re.IGNORECASE,
)
#: Codex can omit context/usage from the ordinary status row. The current
#: shipped snapshots render an empty composer above just
#: ``MODEL EFFORT · DIRECTORY``. This row is anchored end to end. A
#: model-looking draft, an unbounded middle-dot row or any further continuation
#: still fails closed.
_CODEX_STATUS_FOOTER = re.compile(
    r"^\s*(?:gpt|codex|o\d)[\w.-]*(?:\s+\([^\r\n)]+\))?"
    r"\s+(?:default|low|medium|high|xhigh|max|ultra)"
    r"\s+·\s+(?:~|/)\S+"
    # 0.167.0 appends the thread title and the main agent's exact label.
    r"(?:(?:\s+·\s+[^·\r\n]{1,120}?)?\s+·\s+Main \[default\])?"
    r"\s*$",
    re.IGNORECASE,
)
_LEGACY_STATUS_FOOTER = re.compile(
    r"^\s*(?:gpt|codex|o\d)[\w.-]*\s+(?:default|low|medium|high|xhigh|max|ultra)"
    r"\s+·\s+(?:~|/)\S+\s+·\s+\d{1,3}% (?:used|left|context left)"
    r"(?:\s+·\s+resets\s+\d{1,2}:\d{2}\s*[AP]M)?\s*$",
    re.IGNORECASE,
)
_CONTEXT_STATUS_FOOTER = re.compile(
    r"^\s*(?:gpt|codex|o\d)[\w.-]*\s+(?:default|low|medium|high|xhigh|max|ultra)"
    r"\s+·\s+Context \d{1,3}% left\s+·\s+(?:~|/)\S+"
    r"(?:\s+·\s+[\w./-]+\s+·\s+Context \d{1,3}% used)?\s*$",
    re.IGNORECASE,
)
#: What an empty composer shows: nothing, or one of Codex's placeholders. 0.158
#: added "Ask a follow-up question" beside "Ask Codex to do anything"; without
#: it an idle composer read as a draft and the whip skipped it.
CODEX_PLACEHOLDERS: Final = frozenset({"", "Ask Codex to do anything", "Ask a follow-up question"})

_CAPACITY_BANNER = re.compile(
    r"^\s*■ Selected model is at capacity\. Please try a different model\.\s*$"
)
# The maintainer's custom status line, read live with Codex 0.163.0. Match the
# complete row, never merely a percentage somewhere in a possible draft.
_CAPACITY_STATUS_FOOTER = re.compile(
    r"^\s*(?:GPT|codex|o\d)[\w.-]+\s+(?:low|medium|high|xhigh|max|ultra)"
    r" · Context \d{1,3}% left · (?:~|/)\S+ · (?:GPT|codex|o\d)[\w.-]+"
    r" · [\w.-]+ · [\w./-]+ · Context \d{1,3}% used · 5h \d{1,3}% left (?:· )?…\s*$",
    re.IGNORECASE,
)

_LIMIT_BANNER = re.compile(
    r"^[▌■] You've hit your usage limit\. "
    r"(?:Upgrade to Pro \(https://chatgpt\.com/explore/pro\), visit "
    r"https://chatgpt\.com/(?:codex/)?settings/usage to purchase more credits or )?"
    # Codex writes an absolute date ("%b %-d" + ordinal ", %Y") when the
    # reset is not today; 0.167.0 showed "Nov 11th, 2026 2:48 AM" overnight.
    r"[Tt]ry again at (?:[A-Z][a-z]{2} \d{1,2}(?:st|nd|rd|th), \d{4} )?"
    r"\d{1,2}:\d{2}\s*[AP]M\.?$"
)

#: Codex 0.167.0 prints a model-written conversation recap between the limit
#: banner and the composer: "  ↳ Recap: ..." followed by rows indented to the
#: text column. Only that exact shape directly above the blank rows of the
#: composer is recognised, and only when its text matches no prompt pattern.
_RECAP_FIRST = re.compile(r"^  ↳ Recap: \S.*$")
_RECAP_CONTINUATION = re.compile(r"^ {11}\S.*$")
_MAX_RECAP_ROWS: Final = 12


#: Codex's rate-limit model-switch dialog ("rate-limit-switch-prompt"), read
#: live from 0.167.0 and confirmed in its binary strings. Every row is matched
#: whole; the switch target must be the same model in subtitle and item 1.
_KEEP_MODEL_TITLE = re.compile(r"^  Approaching rate limits$")
_KEEP_MODEL_SUBTITLE = re.compile(r"^  Switch to (?P<model>[\w.-]+) for lower credit usage\?$")
_KEEP_MODEL_SWITCH = re.compile(
    rf"^{_MENU_GLYPH} 1\. Switch to (?P<model>[\w.-]+)(?: {{2,}}\S.*)?$"
)
_KEEP_MODEL_KEEP = re.compile(r"^  2\. Keep current model$")
_KEEP_MODEL_NEVER = re.compile(
    r"^  3\. Keep current model \(never show again\)"
    r"(?: {2,}Hide future rate limit reminders about switching models)?$"
)
_KEEP_MODEL_FOOTER = re.compile(r"^  enter select · esc back$")
_MAX_DIALOG_GAP: Final = 3


def _keep_model_dialog(lines: list[str]) -> int | None:
    """Row index of the exact model-switch dialog's title, or None.

    The dialog must be the last thing on screen: title, subtitle, one to three
    blank rows, the three exact items with the cursor on item 1, one blank row
    and the footer. Any other row, wording, cursor position or model fails
    closed, so Down-then-Enter can only ever reach "Keep current model".
    """
    rows = [line.rstrip() for line in lines]
    end = len(rows)
    while end and not rows[end - 1]:
        end -= 1
    if end < 8 or not _KEEP_MODEL_FOOTER.fullmatch(rows[end - 1]) or rows[end - 2]:
        return None
    if not (
        _KEEP_MODEL_NEVER.fullmatch(rows[end - 3]) and _KEEP_MODEL_KEEP.fullmatch(rows[end - 4])
    ):
        return None
    switch = _KEEP_MODEL_SWITCH.fullmatch(rows[end - 5])
    if switch is None:
        return None
    index = end - 6
    gap = 0
    while index >= 0 and not rows[index] and gap < _MAX_DIALOG_GAP:
        index -= 1
        gap += 1
    if not gap or index < 1:
        return None
    subtitle = _KEEP_MODEL_SUBTITLE.fullmatch(rows[index])
    if (
        subtitle is None
        or subtitle.group("model") != switch.group("model")
        or not _KEEP_MODEL_TITLE.fullmatch(rows[index - 1])
    ):
        return None
    return index - 1


def _without_particles(lines: list[str]) -> list[str]:
    return [_BRAILLE_PARTICLES.sub("", line) for line in lines]


PATTERNS: Final[tuple[PromptPattern, ...]] = (
    PromptPattern(
        id="codex/model-capacity",
        provider=NAME,
        kind=PromptKind.CAPACITY_BLOCKED,
        scope="capacity",
        all_of=(re.compile(_CAPACITY_BANNER.pattern, re.MULTILINE),),
        action=ResumeAction(
            kind=ActionKind.TEXT_THEN_ENTER,
            text=DEFAULT_RESUME_TEXT,
            requires_policy="allow_codex_capacity_retry",
        ),
        note="Exact service-capacity error; retry the same model, never select another.",
        verified_against="Codex CLI 0.163.0 capacity screenshot and native binary literal",
    ),
    PromptPattern(
        id="codex/tool-approval",
        provider=NAME,
        kind=PromptKind.APPROVAL_REQUESTED,
        scope="approval",
        all_of=(
            re.compile(rf"^\s*(?:{_APPROVAL_TITLE_TEXT})\s*$", re.MULTILINE),
            re.compile(rf"^\s*{_MENU_GLYPH}\s*1\.\s*Yes,\s", re.MULTILINE),
            re.compile(rf"^\s*{_APPROVAL_FOOTER_TEXT}\s*$", re.MULTILINE),
        ),
        note="Exact one-turn Codex tool permission. Only the selected first item is eligible.",
        verified_against=VERIFIED_AGAINST,
    ),
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
        all_of=(
            _pattern(
                r"reached your workspace credit limit"
                r"|You hit your spend cap set (?:in|by the owner of) your workspace"
            ),
        ),
        verified_against=VERIFIED_AGAINST,
    ),
    PromptPattern(
        id="codex/purchase-offer",
        provider=NAME,
        kind=PromptKind.PAID_ACTION_REQUIRED,
        scope="credits",
        all_of=(
            _pattern(r"purchase more credits|Upgrade to (?:Plus|Pro)\b|start a free trial of\b"),
        ),
        verified_against=VERIFIED_AGAINST,
    ),
    PromptPattern(
        id="codex/limit-increase-request",
        provider=NAME,
        kind=PromptKind.PAID_ACTION_REQUIRED,
        scope="credits",
        all_of=(
            _pattern(
                r"Request (?:a limit increase|an? increase)|Request increase\?"
                r"|send a request to your admin"
            ),
        ),
        note="Sends a request to a workspace admin. Never automated.",
        verified_against=VERIFIED_AGAINST,
    ),
    PromptPattern(
        id="codex/reset-credit-offer",
        provider=NAME,
        kind=PromptKind.PAID_ACTION_REQUIRED,
        scope="reset-credit",
        # 0.159 replaced the "Redeem" line with a menu opened by "$": its
        # heading row, its choices and its progress line are all this offer.
        all_of=(
            re.compile(
                r"Redeem usage limit reset|usage limit resets? available"
                r"|^\s*Usage limit resets\s*$|Choose a different reset|Resetting your usage"
                r"|press \$ to open this list",
                re.IGNORECASE | re.MULTILINE,
            ),
        ),
        note="Consumes a finite earned reset. Never automated.",
        verified_against=VERIFIED_AGAINST,
    ),
    PromptPattern(
        id="codex/model-downgrade",
        provider=NAME,
        kind=PromptKind.MODEL_DOWNGRADE_OFFER,
        scope="model",
        all_of=(
            _pattern(
                r"Keep current model|Uses fewer credits for upcoming turns"
                r"|Switch to another model now"
            ),
        ),
        verified_against=VERIFIED_AGAINST,
    ),
)


def _without_recap(lines: list[str]) -> list[str]:
    """Drop Codex's exact recap block (and its trailing blanks) above the composer.

    Anything else - a misindented row, a question, a menu, a draft, recap text
    that reads like any recognised prompt - leaves the screen unchanged, so the
    recap keeps the limit banner out of the live window and nothing is typed.
    """
    composer = next(
        (
            index
            for index in range(len(lines) - 1, -1, -1)
            if lines[index].strip().startswith("\N{SINGLE RIGHT-POINTING ANGLE QUOTATION MARK}")
        ),
        -1,
    )
    if composer < 0:
        return lines
    end = composer
    while end and not lines[end - 1].strip():
        end -= 1
    start = end
    while (
        start and end - start < _MAX_RECAP_ROWS and _RECAP_CONTINUATION.fullmatch(lines[start - 1])
    ):
        start -= 1
    if not start or not _RECAP_FIRST.fullmatch(lines[start - 1]):
        return lines
    start -= 1
    if start and lines[start - 1].strip():
        return lines
    text = " ".join(line.strip() for line in lines[start:end])
    folded = normalise_typography(text)
    if any(
        regex.search(candidate)
        for pattern in PATTERNS
        for regex in pattern.all_of
        for candidate in (text, folded)
    ):
        return lines
    return [*lines[:start], *lines[composer:]]


class CodexAdapter(ProviderAdapter):
    """Recognises Codex CLI's usage-limit prompts."""

    name = NAME
    patterns_version = PATTERNS_VERSION
    verified_versions = VERIFIED_VERSIONS
    # Codex formats a reset as a bare clock only when it falls on the day the
    # banner is printed, and with its full date otherwise.
    undated_reset_is_same_day = True

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
        original_lines = _without_recap(lines)
        lines = _without_particles(original_lines)
        dialog = _keep_model_dialog(original_lines)
        if dialog is not None:
            return self._keep_model(original_lines, dialog, now=now)
        block = _approval_block(original_lines)
        if block is not None:
            result = super().recognise(block, now=now, live_lines=len(block))
            return replace(
                result,
                input_ready=False,
                composer_empty=False,
                approval_prompt=True,
                approval_fingerprint=fingerprint(block),
            )
        end = len(lines)
        while end and not lines[end - 1].strip():
            end -= 1
        footer_visible = any(
            end >= width and _APPROVAL_FOOTER.fullmatch(_joined_rows(lines[end - width : end]))
            for width in (1, 2)
        )
        manual = (
            super().recognise(lines, now=now, live_lines=_MAX_APPROVAL_ROWS + 12)
            if footer_visible
            else None
        )
        if manual is not None and "codex/tool-approval" in manual.matched_ids:
            # A current overlay with an incomplete/hidden preview still blocks
            # work. Keep it visible as manual approval, without an answerable
            # fingerprint or any composer/resume input path.
            return replace(manual, input_ready=False, composer_empty=False)
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
        # Compare what follows the glyph, with whitespace normalised. Particle
        # removal supports observation; the original composer is checked below
        # and cannot authorize input while any particle is visible there.
        body = (
            " ".join(
                live[composer].split("\N{SINGLE RIGHT-POINTING ANGLE QUOTATION MARK}", 1)[1].split()
            )
            if composer >= 0
            else None
        )
        empty = body in CODEX_PLACEHOLDERS
        # A multi-line draft begun with Shift+Enter leaves the composer row
        # empty and continues below it. For typing a fresh message, only the
        # footer may follow; the resume path keeps its tested ``input_ready``.
        trailing = [line for line in live[composer + 1 :] if line.strip()] if empty else []
        original_live = original_lines[-live_lines:]
        ambiguous_particles = any(_BRAILLE_PARTICLES.search(line) for line in original_live)
        status_rows = [
            bool(
                _CODEX_STATUS_FOOTER.fullmatch(line)
                or _LEGACY_STATUS_FOOTER.fullmatch(line)
                or _CONTEXT_STATUS_FOOTER.fullmatch(line)
                or _CAPACITY_STATUS_FOOTER.fullmatch(line)
            )
            for line in trailing
        ]
        composer_empty = (
            empty
            and not ambiguous_particles
            and len(trailing) <= 2
            and (len(trailing) != 2 or status_rows == [True, False])
            and all(
                _CODEX_FOOTER.fullmatch(line)
                or _CODEX_STATUS_FOOTER.fullmatch(line)
                or _CONTEXT_STATUS_FOOTER.fullmatch(line)
                or _CAPACITY_STATUS_FOOTER.fullmatch(line)
                for line in trailing
            )
        )
        banner = next(
            (
                index
                for index in range(len(live) - 1, -1, -1)
                # Folded like every other comparison: 0.155 writes U+2019 here,
                # and an unfolded anchor silently disabled the bounded retry.
                if re.match(
                    r"^\s*[▌■]\s+You've hit your usage limit\.",
                    normalise_typography(live[index]),
                )
            ),
            -1,
        )
        exact = (
            composer_empty
            and banner >= 0
            and banner < composer
            and bool(
                _LIMIT_BANNER.fullmatch(
                    " ".join(
                        normalise_typography(line).strip()
                        for line in original_live[banner:composer]
                        if line.strip()
                    )
                )
            )
            and result.reset_at is not None
            and {"codex/limit-usage", "codex/try-again-at"}.issubset(result.matched_ids)
            and not any(
                re.search(r"\b(?:Working|Explored|Ran|Thinking)\b", line)
                for line in live[banner + 1 :]
            )
        )
        active = not ambiguous_particles and any(
            re.match(r"^\s*[•●]\s+(?:Working|Explored|Ran|Thinking|Finished)\b", line)
            for line in live
        )
        active_rows = [index for index, line in enumerate(live) if re.match(r"^\s*[•●]\s+", line)]
        capacity_banner = next(
            (index for index, line in enumerate(live) if _CAPACITY_BANNER.fullmatch(line)), -1
        )
        if capacity_banner >= 0:
            active = not ambiguous_particles and any(
                index > capacity_banner for index in active_rows
            )
        if (
            not ambiguous_particles
            and active_rows
            and active_rows[-1] > max(banner, capacity_banner)
        ):
            # New assistant output below a historical limit is a different
            # turn, even before that old banner scrolls out of the live window.
            result = super().recognise(live[active_rows[-1] :], now=now, live_lines=live_lines)
            exact = False
            active = True
        capacity_footer = (
            bool(trailing)
            and len(trailing) <= 2
            and all(
                _CAPACITY_STATUS_FOOTER.fullmatch(line)
                or _CODEX_STATUS_FOOTER.fullmatch(line)
                or line.strip() == "? for shortcuts"
                for line in trailing
            )
        )
        capacity = (
            result.matched_ids == ("codex/model-capacity",)
            and not result.vetoes
            and not active
            and composer_empty
            and capacity_footer
            and capacity_banner >= 0
            and capacity_banner < composer
            and _CAPACITY_BANNER.fullmatch(original_live[capacity_banner]) is not None
            and all(not line.strip() for line in original_live[capacity_banner + 1 : composer])
            and not any(
                re.search(rf"\?\s*$|^\s*[{_MENU_GLYPH}]?\s*\d+\.\s", line)
                for line in original_live[:capacity_banner]
            )
        )
        return replace(
            result,
            retry_prompt=exact,
            capacity_prompt=capacity,
            active_evidence=active,
            input_ready=composer_empty
            and ("codex/model-capacity" not in result.matched_ids or capacity),
            composer_empty=composer_empty,
        )

    def _keep_model(self, lines: list[str], title: int, *, now: datetime) -> Recognition:
        """The model-switch dialog, plus the limit banner directly above it.

        The banner is recognised with the dialog so its printed reset is
        anchored while the dialog is up; otherwise the first sighting after
        the dialog closes could come after the reset. Nothing here is input
        ready: the only keypress allowed is the supervisor's keep-model choice.
        """
        block = lines[title:]
        above = title
        while above and not lines[above - 1].strip():
            above -= 1
        banner = next(
            (
                start
                for start in (above - 1, above - 2)
                if start >= 0
                and _LIMIT_BANNER.fullmatch(
                    " ".join(normalise_typography(line).strip() for line in lines[start:above])
                )
            ),
            None,
        )
        window = lines[banner:] if banner is not None else block
        result = super().recognise(window, now=now, live_lines=len(window))
        return replace(
            result,
            retry_prompt=False,
            capacity_prompt=False,
            active_evidence=False,
            input_ready=False,
            composer_empty=False,
            keep_model_fingerprint=fingerprint(block),
        )


_APPROVAL_TITLE = re.compile(rf"^\s*(?P<title>{_APPROVAL_TITLE_TEXT})\s*$")
_APPROVAL_FOOTER = re.compile(rf"^\s*{_APPROVAL_FOOTER_TEXT}\s*$")
_SELECTED_OPTION = re.compile(rf"^\s*{_MENU_GLYPH}\s*1\.\s*(?P<label>\S.*)\s*$")
_OPTION = re.compile(r"^\s*(?P<number>[1-4])\.\s*(?P<label>\S.*)\s*$")
_ANY_OPTION = re.compile(r"^\s*\d+\.\s")
_MAX_APPROVAL_ROWS: Final = 40
_CLIPPED_APPROVAL_CONTENT = re.compile(
    r"^\s*\[…\s+\d+\s+lines\].*$",
    re.IGNORECASE,
)


def _joined_rows(lines: list[str]) -> str:
    """Undo Codex's soft wrapping for one exact bounded overlay field."""
    return " ".join(normalise_typography(line).strip() for line in lines)


def _approval_block(lines: list[str]) -> list[str] | None:
    """Return one exact Codex 0.162.1 one-turn approval overlay.

    The visible cursor must already select item 1. Every remaining choice is
    matched as part of a title-specific complete menu, so Enter cannot select a
    persistent rule, session mode, strict-review mode, denial or arbitrary
    question. Command, path, reason and input preview rows are deliberately
    opaque but bounded and fingerprinted with the menu.
    """
    end = len(lines)
    while end and not lines[end - 1].strip():
        end -= 1
    footer = next(
        (
            end - width
            for width in (1, 2)
            if end >= width and _APPROVAL_FOOTER.fullmatch(_joined_rows(lines[end - width : end]))
        ),
        -1,
    )
    if footer < 0:
        return None

    last = footer - 1
    while last >= 0 and not lines[last].strip():
        last -= 1
    selected = -1
    for row in range(last, max(-1, last - 12), -1):
        if _SELECTED_OPTION.fullmatch(normalise_typography(lines[row])):
            selected = row
            break
        if not lines[row].strip():
            return None
    if selected < 0:
        return None

    items: list[str] = []
    expected = 1
    row = selected
    while row <= last:
        folded = normalise_typography(lines[row])
        match = _SELECTED_OPTION.fullmatch(folded) if expected == 1 else _OPTION.fullmatch(folded)
        if match is None:
            return None
        if expected > 1 and int(match.group("number")) != expected:
            return None
        label = match.group("label").strip()
        row += 1
        continuations: list[str] = []
        while row <= last and not _OPTION.fullmatch(normalise_typography(lines[row])):
            if not lines[row].strip() or _MENU_GLYPH in lines[row] or _ANY_OPTION.match(lines[row]):
                return None
            continuations.append(normalise_typography(lines[row]).strip())
            row += 1
        items.append(" ".join((label, *continuations)))
        expected += 1
    if not 2 <= len(items) <= 4:
        return None

    title_row = -1
    title = ""
    for row in range(selected - 1, max(-1, selected - _MAX_APPROVAL_ROWS), -1):
        for width in (1, 2):
            if row + width > selected:
                continue
            title_match = _APPROVAL_TITLE.fullmatch(_joined_rows(lines[row : row + width]))
            if title_match is not None:
                title_row = row
                title = title_match.group("title")
                break
        if title_row >= 0:
            break
        if _MENU_GLYPH in lines[row] or _ANY_OPTION.match(lines[row]):
            return None
    if title_row < 0:
        return None
    block = lines[title_row:end]
    if any(_CLIPPED_APPROVAL_CONTENT.fullmatch(line) for line in block):
        # The hidden command is not available to fingerprint. A changed command
        # can render the same line-count placeholder, so this cannot be bound
        # to the operator-visible prompt and must stay manual.
        return None

    exec_middle = (
        re.compile(
            r"Yes, and don't ask again for commands that start with `[^`\r\n]{1,500}` \(p\)"
        ),
        re.compile(r"Yes, and don't ask again for this command in this session \(a\)"),
        re.compile(r"Yes, and allow these permissions for this session \(a\)"),
    )
    network_middle = (
        re.compile(r"Yes, and allow this host for this conversation \(a\)"),
        re.compile(r"Yes, and allow this host in the future \(p\)"),
    )

    if title == "Would you like to run the following command?":
        valid = (
            items[0] == "Yes, proceed (y)"
            and items[-1]
            in {
                "No, continue without running it (n)",
                "No, and tell Codex what to do differently (esc)",
            }
            and all(any(pattern.fullmatch(item) for pattern in exec_middle) for item in items[1:-1])
        )
    elif title == "Would you like to make the following edits?":
        valid = items == [
            "Yes, proceed (y)",
            "Yes, and don't ask again for these files (a)",
            "No, and tell Codex what to do differently (esc)",
        ]
    elif title.startswith("Would you like to send input to "):
        valid = items == [
            "Yes, proceed (y)",
            "No, and tell Codex what to do differently (esc)",
        ]
    elif title.startswith("Do you want to approve network access to "):
        valid = (
            items[0] == "Yes, just this once (y)"
            and items[-1] == "No, and tell Codex what to do differently (esc)"
            and all(
                any(pattern.fullmatch(item) for pattern in network_middle) for item in items[1:-1]
            )
        )
    else:
        valid = items == [
            "Yes, grant these permissions for this turn (y)",
            "Yes, grant for this turn with strict auto review (r)",
            "Yes, grant these permissions for this session (a)",
            "No, continue without permissions (d)",
        ]
    return block if valid else None
