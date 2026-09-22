<!--
SPDX-FileCopyrightText: 2026 Marcel Petrick

SPDX-License-Identifier: GPL-3.0-or-later
-->

Release: Agent While True

Image you are doing a barbecue with your friends, but there is also a heavy agentic software-engineering task going and and you know you'll run out of the budget in 10 minutes, but the window will reset in an hour.
What now?
Slip from the party to enter in a terminal "continue" (and "get all done and make no msitakes, haha) or wait until the guests have left?

Agent While True to the resucue. A Linux system service for KDE-environments, written in Python with zero dependencies, together with a nice TUI (includes CGA grapjic mode theme out of nostalgic reasons).
It will auto-disvoer and track all your running Codex CLI and Claude Code sessions and when necessary, restart the task whenever it was waiting with "you ran out of budge, do you want to upgrade, wait or ..".

Actually I started the implementation foruteeen days ago. Quite naive I thought: this is solved within 24 hours. Getting the software done was less of a challenge, understanding all constraints and what states are possible with both agentic systems and working in a moving target enviroment (thanks anthropic and openai), it took some time to get it done. Of course simulate and test "ran out of budget and the 5h/weekly reset later", but only the real situation gives you the proof if the AWT works. So it took some nights to get it right.

Code under GPLv3, RE-USE-compliant, SPDX-compliant, SBOMS for CycloneDX and SPDX, GitHub Actions for release, yada yada.
Fork and have fun: url

-----------


Release: 𝐀𝐠𝐞𝐧𝐭 𝐖𝐡𝐢𝐥𝐞 𝐓𝐫𝐮𝐞

Imagine you are doing a 𝐛𝐚𝐫𝐛𝐞𝐜𝐮𝐞 with your friends, but there is also a heavy #agentic software-engineering task going on and you know you'll run out of budget in 10 minutes, but the window will reset in an hour.
What now?
Slip away from the party to enter "continue" in a terminal (and "get it all done and make no mistakes, haha") or wait until the guests have left?

Agent While True to the rescue. A #Linux system-service for #KDE environments, written in #Python with zero dependencies, together with a nice #TUI (includes a 𝐂𝐆𝐀 graphic-mode theme for nostalgic reasons).
It will auto-discover and track all your running #Codex CLI and #Claude Code sessions and, when necessary, resume the pending session in terminal whenever it is waiting with "you ran out of budget, do you want to upgrade or wait".

Actually, I started the implementation fourteen days ago. Quite naively, I thought: this is solved within 24 hours 🙈. Getting the software done was less of a challenge; 𝐮𝐧𝐝𝐞𝐫𝐬𝐭𝐚𝐧𝐝𝐢𝐧𝐠 all the 𝐜𝐨𝐧𝐬𝐭𝐫𝐚𝐢𝐧𝐭𝐬 and what states are possible with both agentic systems, while working in a moving-target environment (thanks @Anthropic and @OpenAI), took some time. Of course, you can simulate and test "ran out of budget" and the subsequent 5-hour/weekly reset, but only the real situation gives you proof that AWT works. So it took some nights to get it right.

Code under GPLv3, REUSE-compliant, SPDX-compliant, SBOMs for CycloneDX and SPDX, GitHub Actions for releases, yada yada.
Fork and have fun: https://github.com/marcelpetrick/AgentWhileTrue 
