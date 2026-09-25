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


#: A limit banner that has scrolled far up the screen. It must not be able to
#: trigger anything (vision DANGER 3).
def scrolled_away(block: list[str], *, filler_lines: int = 60) -> list[str]:
    return [*block, *[f"  ... build output line {n}" for n in range(filler_lines)], "❯ "]
