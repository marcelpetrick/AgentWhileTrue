# SPDX-FileCopyrightText: 2026 Marcel Petrick
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Screen fixtures reproducing what the real CLIs display.

The Claude blocks are transcribed from a screenshot of an actual five-hour limit
event on Claude Code 2.1.261 and from three live 2.1.278 sessions read on
2026-09-20; the wording of the other blocks comes from the strings shipped
inside the Claude Code 2.1.261/2.1.270 and Codex CLI 0.153.2 binaries. Keeping
them here, verbatim, is what makes the recognizer tests meaningful.
"""

from __future__ import annotations

CLAUDE_SESSION_LIMIT = [
    "  ⎿  You've hit your session limit · resets 8:10pm (Europe/Berlin)",
    "     /upgrade or /usage-credits to finish what you're working on.",
    "",
    "✳ Crunched for 0s · done 7:31 PM",
    "",
    "❯ ",
]

CLAUDE_LIMIT_MENU = [
    "  Ran 2 shell commands",
    "  └ You've hit your session limit · resets 3:20am (Europe/Berlin)",
    "",
    "* Sautéed for 35m 7s · done 11:07 PM",
    "",
    "   What do you want to do?",
    "",
    "   ❯ 1. Stop and wait for limit to reset",
    "     2. Wait here, then continue automatically at 3:20am",
    "     3. Upgrade your plan",
    "",
    "   Enter to confirm · Esc to cancel",
]

#: Transcribed from three live sessions on 2026-09-20, Claude Code 2.1.278.
#: Item 2 no longer names a time, the banner is indented with U+00A0 after the
#: "⎿" glyph, and a rule separates the transcript from the menu. All three
#: sessions sat on this screen through their 6:50pm reset without being armed.
CLAUDE_LIMIT_MENU_SHORTLY = [
    "  Ran 1 shell command",
    "  ⎿ \xa0You've hit your session limit · resets 6:50pm (Europe/Berlin)",
    "",
    "✻ Worked for 1h 27m 24s · done 6:43 PM",
    "▔" * 138,
    "   What do you want to do?",
    "",
    "   ❯ 1. Stop and wait for limit to reset",
    "     2. Wait here, then continue automatically shortly",
    "     3. Upgrade your plan",
    "",
    "   Enter to confirm · Esc to cancel",
]

#: The same menu while the banner's paid advertisement is still on screen.
#: Live sessions refused this with `paid-action-required:claude/usage-credits-offer`
#: on 2026-09-20, although arrow-down-then-Enter can only reach item 2.
CLAUDE_LIMIT_MENU_WITH_CREDIT_LINKS = [
    "  ⎿ \xa0You've hit your session limit · resets 6:50pm (Europe/Berlin)",
    "     /upgrade or /usage-credits to finish what you're working on.",
    "",
    "✻ Worked for 1h 27m 24s · done 6:43 PM",
    "▔" * 138,
    "   What do you want to do?",
    "",
    "   ❯ 1. Stop and wait for limit to reset",
    "     2. Wait here, then continue automatically shortly",
    "     3. Upgrade your plan",
    "",
    "   Enter to confirm · Esc to cancel",
]

#: The menu with the limit banner scrolled out of the live window. Nothing on
#: screen states that usage is spent, so arming must still fail closed unless a
#: quota source says so.
CLAUDE_LIMIT_MENU_WITHOUT_BANNER = [
    "   What do you want to do?",
    "",
    "   ❯ 1. Stop and wait for limit to reset",
    "     2. Wait here, then continue automatically shortly",
    "     3. Upgrade your plan",
    "",
    "   Enter to confirm · Esc to cancel",
]

#: Claude Code 2.1.278 arms its own wait from `/rate-limit-options` and then
#: says so without naming a time. Read live on 2026-09-20, where the supervisor
#: classified it LIMIT_BLOCKED because neither self-healing wording matched.
CLAUDE_CONTINUING_SHORTLY = [
    "✻ Cooked for 0s · done 6:49 PM",
    "",
    "❯ /rate-limit-options",
    "  ⎿  Claude Code will continue automatically shortly. Keep this session "
    "open; it may still pause for permission prompts. Press esc to",
    "     cancel the wait.",
    "",
    "❯",
    "  ⚠ Usage limit reached · continuing shortly · esc to cancel",
    "  Opus 5 ctx:5%",
]

CLAUDE_READY_TO_RESUME = [
    "  ⎿  You've hit your session limit · resets 8:10pm (Europe/Berlin)",
    "",
    "✳ Crunched for 0s · done 7:31 PM",
    "",
    "● Usage limit has reset · press enter to continue",
    "",
    "❯ ",
]

#: Reconstructed from the 2026-09-18 live false positive: an assistant turn in
#: an unrelated Claude Code session *quoting* the affordance strings. The
#: full-auto service read this as READY_TO_RESUME; only the quoted self-healing
#: sentence, which carries a veto, stopped an Enter. Nothing here is a prompt.
CLAUDE_QUOTED_AFFORDANCES = [
    "● Short answer: yes, it is active. Here is what it does on each dialog:",
    '  - Claude, "usage limit has reset · press enter to continue": presses Enter.',
    '  - Claude already saying "Continuing automatically when your limit resets":',
    "    stands down, because Claude resumes itself.",
    "",
    "❯ ",
]

#: The same quote without the vetoing sentence: the case that would have typed.
CLAUDE_QUOTED_READY_AFFORDANCE = [
    "● Short answer: yes, it is active. Here is what it does on each dialog:",
    '  - Claude, "usage limit has reset · press enter to continue": presses Enter.',
    "",
    "❯ ",
]

CLAUDE_SELF_HEALING = [
    "● Usage limit reached · resets 8:10pm",
    "  Continuing automatically when your limit resets",
    "",
    "❯ ",
]

CLAUDE_WEEKLY_LIMIT = [
    "  ⎿  You've hit your weekly limit · resets Mon 12:00am",
    "",
    "❯ ",
]

CLAUDE_WILL_NOT_SELF_RESUME = [
    "● Usage limit reached · resets in 30h",
    "  the usage limit now resets more than 24 hours out, so this task will not",
    "  resume on its own (/rate-limit-options to wait anyway)",
    "",
    "❯ ",
]

CLAUDE_SPEND_LIMIT = [
    "● You've hit your monthly spend limit. Run /usage-credits to manage your limit",
    "",
    "❯ ",
]

CLAUDE_MODEL_DOWNGRADE = [
    "● You've hit your Opus limit · resets 8:10pm",
    "  Switch to another model to keep going",
    "",
    "❯ ",
]

CLAUDE_EXTRA_USAGE = [
    "● Usage limit reached · resets 8:10pm",
    "  Run /extra-usage to continue now",
    "",
    "❯ ",
]

CLAUDE_SESSION_LIMIT_RESET = [
    "● Usage limit reached · resets 8:10pm",
    "  Reset your session limit now and keep working; once a week, still counts toward your weekly limit",
    "",
    "❯ ",
]

CLAUDE_LOWER_PRIORITY = [
    "● Usage limit reached · resets 8:10pm",
    "  Continue now at lower priority",
    "",
    "❯ ",
]

CLAUDE_ACTIVE = [
    "● Reading src/agent_while_true/policy.py",
    "",
    "❯ ",
    "  Opus 5 ctx:28% 5h:19% reset:4h51m",
]

CODEX_USAGE_LIMIT = [
    "▌ You've hit your usage limit. Try again at 8:10 PM.",
    "",
    "› ",
]

CODEX_APPROACHING = [
    "▌ Approaching rate limits",
    "",
    "› ",
]

CODEX_OUT_OF_CREDITS = [
    "▌ You're out of credits. Your workspace is out of credits. Add credits to continue.",
    "",
    "› ",
]

CODEX_MODEL_DOWNGRADE = [
    "▌ You've hit your usage limit.",
    "  Uses fewer credits for upcoming turns.",
    "  Keep current model",
    "",
    "› ",
]

CODEX_RESET_CREDIT = [
    "▌ Usage limit reached",
    "  Redeem usage limit reset",
    "",
    "› ",
]

#: Codex 0.159 replaced "Redeem usage limit reset" with a reset menu opened by
#: "$". Built from the strings of the 0.159.0 binary, not a live screen: the
#: heading, its subtitle, the confirmation choice and the tip.
CODEX_0_159_RESET_MENU = [
    "  Usage limit resets",
    "  Account usage and resets.",
    "",
    "› 1. Use a usage limit reset",
    "  2. Choose a different reset",
    "",
    "  Tip: press $ to open this list directly",
]
CODEX_0_159_RESETTING = ["  Resetting your usage...", "", "› "]

# Transcribed from media/agentWhileTrue_notWorking.png (Codex CLI 0.153.4).
# The paid paths are passive links in the ordinary limit banner; the composer
# is a separate control below them.
CODEX_USAGE_LIMIT_WITH_PURCHASE_LINKS = [
    "■ You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit",
    "  https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 3:36 PM.",
    "",
    "› Ask Codex to do anything",
]

# Shape observed live on Codex CLI 0.154.0 (2026-09-18, 220 columns): the
# banner is one long line, and the composer rows carry animated Braille
# "particles" that change every frame, on the placeholder row too. Only the
# chrome is transcribed; the particles' positions are illustrative.
CODEX_USAGE_LIMIT_WITH_PARTICLES = [
    "■ You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 3:23 PM.",
    "",
    "    ⠈                    ⠄                       ⠐ ⠈    ⠂⡀",
    "› Ask Codex to do anything   ⠈     ⠄    ⠐          ⠈  ⠐⢀⢀          ⠈                    ⢀",
    "       ⠁⠁                                    ⠐ ⠈    ⢀⠈⠐⢀",
    "  gpt-5-codex high · ~/project · 67% used · resets 3:23 PM",
]

# Shape observed live on Codex CLI 0.155.1 (2026-09-20, two blocked sessions):
# the same banner as CODEX_USAGE_LIMIT_WITH_PURCHASE_LINKS, but rendered with a
# typographic apostrophe (U+2019) where 0.154 used an ASCII one. That single
# character stopped `codex/limit-usage` from matching, so no action was proposed
# and the purchase-offer veto could not be suppressed.
CODEX_USAGE_LIMIT_TYPOGRAPHIC = [
    "\u25a0 You\u2019ve hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit",
    "  https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 3:42 AM.",
    "",
    "\u203a Ask Codex to do anything",
]

# Claude writes the same apostrophe in its own limit banners, so the fold has to
# be provider-independent rather than a Codex special case.
CLAUDE_SESSION_LIMIT_TYPOGRAPHIC = [
    "\u25b8 You\u2019ve hit your session limit \u00b7 resets 2:20 AM",
    "",
    '\u203a Try "continue" to pick up where you left off',
]

CODEX_COMPLETED_TURN_BELOW_OLD_LIMIT = [
    *CODEX_USAGE_LIMIT_WITH_PURCHASE_LINKS,
    "continue",
    "• Explored",
    "  └ Read controller.py",
    "• Ran tests",
    "  └ all checks passed",
    "• Finished the requested work",
    "",
    "› Ask Codex to do anything",
]

CODEX_ACTIVE = [
    "• Ran cargo test",
    "",
    "› ",
]

#: Claude Code's idle composer as read from live 2.x sessions on 2026-09-24: the
#: cursor row sits between two rules, with the status line underneath. Status
#: text is illustrative.
_RULE = "\u2500" * 60
CLAUDE_IDLE_COMPOSER = [
    "● Tests pass; the branch is pushed.",
    "✻ Worked for 33s · done 12:20 PM",
    _RULE,
    "❯ ",
    _RULE,
    "  Opus 5.5 ctx:33% 5h:58% reset:1h17m",
    "  ⏵⏵ bypass permissions on · 2 shells",
]

#: A multi-line draft that starts with Shift+Enter: the cursor row itself is
#: empty and the text sits on the continuation row inside the frame.
CLAUDE_DRAFT_AFTER_NEWLINE = [
    "● Tests pass; the branch is pushed.",
    _RULE,
    "❯ ",
    "  also rename the helper before you",
    _RULE,
    "  Opus 5.5 ctx:33% 5h:58% reset:1h17m",
]

#: Codex's idle composer above its footer, and the same Shift+Enter draft shape.
CODEX_IDLE_WITH_FOOTER = [
    "• Ran cargo test",
    "",
    "› Ask Codex to do anything",
    "",
    "  gpt-5-codex high · ~/code/tide-mapper · 38% used",
]

CODEX_DRAFT_AFTER_NEWLINE = [
    "• Ran cargo test",
    "",
    "› ",
    "  rename the helper before you",
]

#: The same Shift+Enter draft whose continuation row happens to contain a
#: middle dot, like the footer's separators. The dot alone is not a footer.
CODEX_DRAFT_AFTER_NEWLINE_WITH_DOT = [
    "• Ran cargo test",
    "",
    "› ",
    "  keep the API · but rename the helper",
    "",
    "  gpt-5-codex high · ~/code/tide-mapper · 38% used",
]

#: Codex CLI 0.158.0 read live over D-Bus on 2026-09-28: a working turn above
#: the placeholder composer, then the status line (now "Context N% left") and
#: a key-hint row. Text above the composer is shortened; the rows are verbatim.
CODEX_0_158_WORKING = [
    "• The benchmark blocker is gone. You can hibernate from KDE now.",
    "",
    "• Working (2m 44s • esc to interrupt)",
    "  └ Tip: Use /archive to archive the current session.",
    "",
    " ",
    "› Ask Codex to do anything",
    " ",
    "  GPT-6-Sol high · Context 93% left · ~/repos/codingWithGPT · master · Context 7% used",
    "  ← for agents · ? for shortcuts",
]

#: Codex 0.158 ships a second composer placeholder next to the first one
#: (strings of the 0.158.0 binary), and its status line may end on "N% left".
#: Constructed from those strings, not read from a live screen.
CODEX_0_158_FOLLOW_UP = [
    "• Ran cargo test",
    "",
    "› Ask a follow-up question",
    "",
    "  GPT-6-Sol high · Context 93% left · ~/repos/codingWithGPT",
]
CODEX_0_158_QUEUE_HINT = [
    "• Working (12s • esc to interrupt)",
    "",
    "› Ask Codex to do anything",
    "",
    "  tab to queue message",
]

#: Limit headlines Claude Code 2.1.283 builds at runtime ("You've hit your
#: ${limit}" plus an optional " · progress saved"), taken from the strings of
#: the 2.1.283 binary on 2026-09-29, not from a live screen.
CLAUDE_2_1_283_WINDOW_LIMITS = {
    "fable": "  ⎿  You've reached your Fable limit · resets 8:10pm (Europe/Berlin)",
    "fable-hit": "  ⎿  You've hit your Fable limit · progress saved · resets 8:10pm",
    "generic": "  ⎿  You've hit your limit · progress saved · resets 8:10pm (Europe/Berlin)",
    "usage": "  ⎿  You've hit your usage limit · resets 8:10pm (Europe/Berlin)",
}
#: The ones that no wait ends: credits, an admin's cap, a seat type.
CLAUDE_2_1_283_ADMIN_LIMITS = {
    "credit-limit": "  ⎿  You've hit your usage credit limit",
    "out-of-credits": "  ⎿  You're out of usage credits. /model to switch models.",
    "out-of-extra": "  ⎿  You're out of extra usage",
    "fable-credits": "  ⎿  Fable 5 requires usage credits.",
    "org-spend": "  ⎿  You've hit your org's monthly spend limit · ask your admin for a higher limit",
    "channel-usage": "  ⎿  You've hit your channel's monthly usage limit",
    "team-budget": "  ⎿  You've hit your team's shared budget. /model to switch models.",
    "individual": "  ⎿  You've hit your individual usage limit · ask your admin for a higher limit",
    "org-out": "  ⎿  Your org is out of usage · add funds to continue",
    "seat": "  ⎿  Your seat type doesn't include usage credits",
    "disabled": "  ⎿  Your usage allocation has been disabled by your admin",
    "zero": "  ⎿  Your group's usage limit is set to $0",
}

#: A person's unsent draft in each composer. Submitting anything here would
#: send their half-written message, so neither composer counts as empty.
CLAUDE_DRAFT = [
    "● Reading src/agent_while_true/policy.py",
    "",
    "❯ also check the lock handling and",
    "  Opus 5 ctx:28% 5h:19% reset:4h51m",
]

CODEX_DRAFT = [
    "• Ran cargo test",
    "",
    "› rename the helper before you",
]


#: Claude Code's tool-permission prompt, transcribed from a live screenshot on
#: 2026-09-28: a subagent's Bash command that cannot be allow-listed, so the
#: menu offers only Yes and No. The command is illustrative; the frame, the
#: menu and the footer are verbatim.
_PROMPT_RULE = "─" * 120
CLAUDE_APPROVAL_YES_NO = [
    "● Release files are ready. Now waiting for the frontend agent, which has items 1, 10.",
    "",
    "✻ Waiting for 1 background agent to finish",
    "",
    _PROMPT_RULE,
    " Bash command · from the general-purpose agent",
    "",
    "   │ cd /home/user/project; PYTHONPATH=src uv run --no-sync pytest -m e2e 2>&1 |",
    "   │ head -30",
    "   Run shell command",
    "",
    " This command requires approval",
    "",
    " Do you want to proceed?",
    " ❯ 1. Yes",
    "   2. No",
    "",
    " Esc to cancel · Tab to amend",
]

#: The same prompt read live from Claude Code 2.1.283 over D-Bus on
#: 2026-09-28. Konsole's getAllDisplayedTextList returned all 88 rows of the
#: window: this content on the top rows, then 53 blank rows of padding below
#: the footer. The command is shortened; the rows and glyphs are verbatim.
CLAUDE_APPROVAL_LIVE_2_1_283 = [
    "● Checking that GitHub access now works from the sandbox:",
    "",
    "● Look for settings that could block GitHub",
    "  ⎿  $ for f in ~/.claude-dmo/settings.json .claude/settings.json; do",
    '     echo "== $f"; cat "$f" 2>&1 | head -60; done',
    "",
    "\u2500" * 100,
    " Bash command",
    "",
    "   │ for f in ~/.claude-dmo/settings.json .claude/settings.json; do",
    '   │ echo "== $f"; cat "$f" 2>&1 | head -60; done',
    "   Look for settings that could block GitHub",
    "",
    " Contains simple_expansion",
    "",
    " Do you want to proceed?",
    " ❯ 1. Yes",
    "   2. No",
    "",
    " Esc to cancel · Tab to amend",
]
KONSOLE_PADDING_ROWS = 53

#: A subagent's permission box read live from Claude Code 2.1.285 over D-Bus on
#: 2026-09-30, after auto-yes had already sent its Enter: the box stayed, with
#: the very same fingerprint, and the once-per-appearance guard then left it
#: waiting for good. The window was 281 columns wide; the paths are anonymised,
#: every other row and glyph is verbatim.
CLAUDE_APPROVAL_STAYED_2_1_285 = [
    "✻ Waiting for 7 background agents to finish",
    "",
    "─" * 281,
    " Bash command · from the general-purpose agent",
    "",
    "   │ cd /home/user/project/tests; bash -c 'ls integration/ocr; grep -nE \"^def test|skipif"
    '|fixtures|playtest" integration/ocr/*.py | head -40; sed -n 1,40p e2e/test_e2e_playtest.py'
    ' | head -60; grep -rn "rotat" --include=*.py integration | head -5; grep -rnE "def',
    '   │ test.*(windows|case_insens|reserved)" --include=*.py unit/filesystem invariants'
    ' component | head; grep -rn "OCR_DISAGREEMENT" gui/test_gui_review_workflow.py | head -3\'',
    "   Run shell command",
    "",
    " │ bash names a path that is computed at run time, which cannot be checked against the"
    " read block (permissions.blockReadsOutsideWorkingDirectories)",
    "",
    " Do you want to proceed?",
    " ❯ 1. Yes",
    "   2. No",
    "",
    " Esc to cancel · Tab to amend",
]

#: File-edit prompts read live from Claude Code 2.1.283 on 2026-09-28. The
#: question names the file, a dashed rule separates it from the preview, and
#: item 2 is a session-scoped "Yes, and ...". File contents are shortened.
_DASHED = "\u254c" * 100
CLAUDE_APPROVAL_OVERWRITE_LIVE = [
    "● Write(.claude/settings.local.json)",
    "",
    "\u2500" * 100,
    " Overwrite file",
    " .claude/settings.local.json",
    _DASHED,
    "   1  {",
    '   2 +  "env": {',
    '   3 +    "GIT_CONFIG_COUNT": "2",',
    "   4 +  },",
    '   5    "sandbox": {',
    _DASHED,
    " Do you want to overwrite settings.local.json?",
    " ❯ 1. Yes" + " " * 100,
    "   2. Yes, and allow Claude to edit files in this project's .claude folder for this session",
    "   3. No",
    "",
    " Esc to cancel · Tab to amend",
]
#: A new file whose preview fills the window: the box's solid top rule has
#: scrolled away and only the dashed rule above the question is on screen.
CLAUDE_APPROVAL_CREATE_LIVE = [
    *[f"  {number}     print(f'line {number}')" for number in range(141, 172)],
    '  172 if __name__ == "__main__":',
    "  173     sys.exit(main())",
    _DASHED,
    " Do you want to create allow_github_in_claude_sandbox.py?",
    " ❯ 1. Yes" + " " * 100,
    "   2. Yes, and switch to accept edits (auto-approve file edits and common file commands)"
    " for this session (shi",
    "   3. No",
    "",
    " Esc to cancel · Tab to amend",
]

#: The common three-option form. Enter on the cursor selects item 1, the
#: one-time "Yes"; item 2, which would write an allow rule, is never reached.
CLAUDE_APPROVAL_DONT_ASK_AGAIN = [
    *CLAUDE_APPROVAL_YES_NO[:13],
    " Do you want to proceed?",
    " ❯ 1. Yes",
    "   2. Yes, and don't ask again for uv run commands in /home/user/project",
    "   3. No, and tell Claude what to do differently (esc)",
    "",
    " Esc to cancel · Tab to amend",
]

#: The exact menu with the operator's cursor moved onto No.
CLAUDE_APPROVAL_CURSOR_ON_NO = [
    *CLAUDE_APPROVAL_YES_NO[:14],
    "   1. Yes",
    " ❯ 2. No",
    "",
    " Esc to cancel · Tab to amend",
]

#: The three-option menu with the operator's cursor on item 2 or item 3.
CLAUDE_APPROVAL_CURSOR_ON_TWO = [
    *CLAUDE_APPROVAL_YES_NO[:14],
    "   1. Yes",
    " ❯ 2. Yes, and don't ask again for uv run commands in /home/user/project",
    "   3. No, and tell Claude what to do differently (esc)",
    "",
    " Esc to cancel · Tab to amend",
]

CLAUDE_APPROVAL_CURSOR_ON_THREE = [
    *CLAUDE_APPROVAL_YES_NO[:14],
    "   1. Yes",
    "   2. Yes, and don't ask again for uv run commands in /home/user/project",
    " ❯ 3. No, and tell Claude what to do differently (esc)",
    "",
    " Esc to cancel · Tab to amend",
]

#: The same words quoted inside an assistant turn are not the prompt.
CLAUDE_APPROVAL_QUOTED = [
    "● Claude Code asks 'Do you want to proceed?' and lists ❯ 1. Yes and 2. No;",
    "  Esc to cancel dismisses it.",
    _RULE,
    "❯ ",
    _RULE,
]


#: A limit banner that has scrolled far up the screen. It must not be able to
#: trigger anything (vision DANGER 3).
def scrolled_away(block: list[str], *, filler_lines: int = 60) -> list[str]:
    return [*block, *[f"  ... build output line {n}" for n in range(filler_lines)], "❯ "]
