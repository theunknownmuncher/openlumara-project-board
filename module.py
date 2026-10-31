# -- AI-GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-26) status:reviewed harness:openlumara --
# project-board module for OpenLumara — a kanban / scrum board you drive from the WebUI while your AI drives it with tools
# Copyright (C) 2026 theunknownmuncher <theunknownmuncher@protonmail.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-26) harness:openlumara status:reviewed
import core
import channels.webui.api as webui

import asyncio
import datetime
import os
import re
import secrets
import ulid

CARD_TYPES = ("epic", "story", "task", "bug", "chore")
PRIORITIES = ("critical", "high", "medium", "low")

# card ids are short and board-unique rather than full ulids: they end up in the AI's
# listings and in chat ("move 7QK3MZ to done"), so they have to stay cheap and speakable.
# crockford's base32, minus the letters people mix up.
ID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
ID_LENGTH = 6

# columns whose cards count towards "done" in the progress / stats math
DONE_COLUMN_NAMES = ("done", "closed", "complete", "completed")

# name of the board a fresh install starts with, and what the first board is called when
# storage from before boards existed gets migrated
DEFAULT_BOARD_NAME = "General"

# ----------------------------------------------------------------------
# prompt actions: templates you write yourself, with the card's fields in them
# ----------------------------------------------------------------------

# what a template can reach for. replacement is plain string replacement rather than
# str.format on purpose: a template full of json, code or just braces in prose survives
# untouched, nothing can reach into python objects, and an unknown {thing} stays exactly as
# it was written instead of blowing up on someone's hand written prose.
CARD_PLACEHOLDERS = ("id", "title", "description", "column", "board", "type", "priority",
                     "assignee", "labels", "points", "due", "comments", "change", "date")
SPEC_PLACEHOLDERS = ("title", "spec", "board", "backlog", "date")

# the templates the action editor offers as a starting point. they are never created on
# their own - picking one fills the editor, and what you save is yours from then on.
ACTION_EXAMPLES = [
    {
        "name": "Implement this task",
        "column": "",
        "blurb": "read what you need, plan, implement, move the card to done when tests pass",
        "template": """Work on card {id} ("{title}") on the {board} board, which sits in {column}.

{description}

Read the parts of the repository you need first, then plan briefly and implement it. Keep the
change small and coherent, run the tests your work touches, and move the card to Done with
project-board_move_card once they pass. If you turn up more work, put it on the board as cards of
its own instead of quietly doing it. Tell me what changed and where.""",
    },
    {
        "name": "Plan this task first",
        "column": "Backlog",
        "blurb": "a step by step plan and open questions, no code changes",
        "template": """Plan card {id} ("{title}") on the {board} board. Do not write or edit any code.

{description}

Read what you need to, then give me a step by step plan: the files you would touch, the order,
the risks, and how each step gets verified. Ask the questions you would need answered before
starting, and suggest a points estimate.""",
    },
    {
        "name": "Break this into subtasks",
        "column": "",
        "blurb": "split the card into one-sitting cards right below it",
        "template": """Break card {id} ("{title}") on the {board} board into smaller cards you could each
finish in one sitting, in the order they should be done.

{description}

Add them with project-board_add_cards in one call, directly below this card in {column}, and name
this card's id in each of their descriptions. Do not implement anything yet.""",
    },
    {
        "name": "Draft acceptance criteria",
        "column": "Backlog",
        "blurb": "measurable criteria written into the card's description",
        "template": """Card {id} ("{title}") on the {board} board has no usable acceptance criteria yet:

{description}

Write measurable acceptance criteria for it - what has to be observably true when the card is done
- and put them into the card's description with project-board_edit_card. Keep what the
description already gets right. Cover the edge cases and say what is out of scope.""",
    },
    {
        "name": "Estimate this",
        "column": "Backlog",
        "blurb": "story points plus the reasoning, as points on the card and a comment",
        "template": """Estimate card {id} ("{title}") on the {board} board:

{description}

Give me a story point value with your reasoning, and name the thing that makes the estimate
uncertain. Then set the points with project-board_edit_card and leave the reasoning as a comment
on the card.""",
    },
    {
        "name": "Triage this bug",
        "column": "Backlog",
        "blurb": "reproduce, narrow the cause, set priority - without fixing it",
        "template": """Triage card {id} ("{title}") on the {board} board:

{description}

Reproduce it, narrow down the cause, and say how big the fix looks. Do not fix it yet. Set a
realistic priority on the card, mark it blocked if it waits on something, and comment what you
found plus the first thing the next person should try.""",
    },
    {
        "name": "Fix this bug",
        "column": "In Progress",
        "blurb": "root cause, minimal fix, regression test, then move it to done",
        "template": """Fix card {id} ("{title}") on the {board} board:

{description}

Find the root cause rather than the symptom, keep the fix minimal, and add the regression test
that would have caught it. Run the tests. Move the card to Done with project-board_move_card and
comment on what the cause was and what you changed.""",
    },
    {
        "name": "Write tests for this",
        "column": "In Progress",
        "blurb": "cover the behaviour the card describes and report the gaps",
        "template": """Card {id} ("{title}") on the {board} board needs test coverage:

{description}

Cover the behaviour the card describes - happy path, the edges, the failure modes - in the
project's own test style. Tell me which gaps you could not cover and why. Do not fix bugs you
find on the way; write them onto the board as bug cards instead.""",
    },
    {
        "name": "Review this change",
        "column": "In Review",
        "blurb": "compare what is on disk against what the card asked for",
        "template": """Review the work behind card {id} ("{title}") on the {board} board:

{description}

Compare what is actually in the working tree against what the card asks for. List must-fix issues
separately from nice-to-have ones, say whether the tests cover it, and go through the acceptance
criteria one by one. Change nothing yourself.""",
    },
    {
        "name": "Finish this card",
        "column": "In Review",
        "blurb": "address the review comments, move to done, note what changed",
        "template": """Wrap up card {id} ("{title}") on the {board} board:

{description}

Work through the open review comments on the card and fix what they ask for, then move the card to
Done with project-board_move_card and leave a short note about what changed and where.""",
    },
    {
        "name": "Write session notes",
        "column": "",
        "blurb": "a comment on the card for whoever picks this up next",
        "template": """You are working on card {id} ("{title}") on the {board} board.

When you stop - now or later - write a comment on this card with project-board_add_comment saying
what you actually did: files touched, decisions taken and why, what is still open, and the first
thing worth doing next session. Short, factual, written for whoever picks this up next, possibly
you with no context.""",
    },
    {
        "name": "Unblock this",
        "column": "",
        "blurb": "say what it waits on, split off what could start today",
        "template": """Card {id} ("{title}") on the {board} board is stuck:

{description}

Say plainly what it waits on, and split off the part of it that could be started today as a card of
its own. Mark this card blocked with project-board_edit_card if it truly cannot move, and suggest
which card on the board is the best one to do instead right now.""",
    },
    {
        "name": "Summarise this column",
        "column": "",
        "blurb": "a status read-out of the column, with nothing changed",
        "template": """Give me a status read-out of the {column} column on the {board} board, with card {id}
("{title}") as the one you were asked about. Read the board, group the cards, and say what is
moving, what is stalled and what looks risky. Change nothing.""",
    },
    {
        "name": "Sync the board",
        "column": "",
        "blurb": "compare board against repository reality and propose moves",
        "template": """Compare the {board} board against what the repository actually looks like, starting from card
{id} ("{title}").

Find work that is finished but not marked done, cards describing work nobody is doing, and missing
steps for work in progress. Propose the moves and the new cards as a list first - do not touch the
board until I agree.""",
    },
    {
        "name": "Import OpenSpec stories",
        "column": "",
        "blurb": "re-read the change this card came from and land what is missing",
        "template": """Card {id} ("{title}") came from the OpenSpec change {change}. Re-read
openspec/changes/{change}/ and land whatever is not on the {board} board yet with
project-board_import_openspec, so the cards come from the files rather than from your memory of
them. Then tell me which requirements have no scenario, since those are not testable yet. Do not
implement anything.""",
    },
    {
        "name": "Check off OpenSpec tasks",
        "column": "",
        "blurb": "tick the boxes you really finished, then let the board follow the file",
        "template": """Card {id} ("{title}") came from the OpenSpec change {change}. Tick the boxes in
openspec/changes/{change}/tasks.md for the tasks you actually completed - and only those - and
leave the file's numbering and wording otherwise alone. If what you did matches no task, add the
task you really did. Then run project-board_import_openspec again so the board follows the file.""",
    },
    {
        "name": "Archive this change",
        "column": "",
        "blurb": "merge the specs and archive the folder once its cards are done",
        "template": """Card {id} ("{title}") came from the OpenSpec change {change}. Once every card from it sits on a
done column of the {board} board, archive the change the way this project does it: delta specs
merged into the main specs, the change folder moved under openspec/changes/archive with its date.
Check nothing from it is left open first, and tell me what you merged.""",
    },
]

# the prompt the process-spec button fills into the chat. deliberately OpenSpec shaped: the
# stories your board ends up with come out of reviewed files rather than out of the middle of
# a chat turn. it is a setting, so rewrite it however your project plans.
DEFAULT_SPEC_PROMPT = """Turn the spec below into an OpenSpec change, then land its stories on the '{board}' board.

1. If the project has an openspec/ folder, follow it. If the openspec CLI is available, use it
   (openspec new change, or the opsx skills); otherwise write the same artifacts by hand under
   openspec/changes/<change-id>/: proposal.md, one specs/<capability>/spec.md per capability
   using '### Requirement:' with at least one '#### Scenario:' (- WHEN / - THEN) each, design.md
   when the approach is not obvious, and tasks.md as a numbered checklist where every item says
   how it gets verified.
2. Check your own work before landing anything: every requirement has a scenario, every scenario
   has a WHEN and a THEN, and every task is finishable in one sitting.
3. Land the stories with project-board_import_openspec so the cards come from the files rather
   than from your memory of them. They go into '{backlog}' and nowhere else. Do not start
   implementing, and do not put the spec itself on the board - only the stories.
4. Tell me the change id, how many cards you added, and which requirements you were unsure about.

Spec: {title}

{spec}
"""

# ----------------------------------------------------------------------
# openspec: reading openspec/changes/<change>/ and turning it into cards
# ----------------------------------------------------------------------

# cards that came out of a change carry this label ("openspec/add-dark-mode") so a whole
# batch is filterable in the panel, and a hidden "source" field so re-importing updates
# them instead of duplicating them
OPENSPEC_LABEL = "openspec"
OPENSPEC_UNITS = ("requirements", "tasks", "both")
OPENSPEC_ARCHIVE = "archive"

# the shapes OpenSpec actually writes. plain markdown on purpose, so a change stays
# readable when nobody has the CLI installed - and so we can read it without the CLI.
TASK_BOX_RE = re.compile(r"^\s*[-*+]\s*\[(?P<mark>.)\]\s*(?P<body>.*?)\s*$")
TASK_NUMBER_RE = re.compile(r"^(?P<number>\d+(?:\.\d+)*)[.)]?\s+(?P<title>\S.*)$")
HEADING_RE = re.compile(r"^#{1,4}\s*(?P<name>.+?)\s*$")
DELTA_KIND_RE = re.compile(r"^#{1,4}\s*(?P<kind>added|modified|removed|renamed)\s+requirements?\s*$",
                           re.IGNORECASE)
REQUIREMENT_RE = re.compile(r"^#{1,5}\s*Requirement:\s*(?P<name>.+?)\s*$", re.IGNORECASE)
SCENARIO_RE = re.compile(r"^#{1,6}\s*Scenario[s]?\s*:\s*(?P<name>.+?)\s*$", re.IGNORECASE)


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _slug(value):
    return str(value or "").strip().lower()


def _today():
    return datetime.date.today()


def _is_overdue(card):
    """a card is overdue when its due date passed (only meaningful for unfinished work)"""
    due = str(card.get("due") or "")
    if not due:
        return False

    try:
        return datetime.date.fromisoformat(due) < _today()
    except ValueError:
        return False


def _requirement_markdown(change, requirement):
    """a card description out of one requirement: the SHALL sentence, then its scenarios as
    acceptance criteria. that second part is the whole reason to read the specs rather than the
    task list - a story you cannot check off against a scenario is just a todo item"""
    capability = requirement.get("capability") or ""

    lines = [f"Requirement: {requirement['name']}"]

    if requirement.get("text"):
        lines.append("")
        lines.append(requirement["text"])

    lines.append("")
    lines.append("Acceptance criteria, from "
                 f"openspec/changes/{change['id']}/specs/{capability or '?'}/spec.md:")

    if requirement.get("scenarios"):
        for scenario in requirement["scenarios"]:
            lines.append(f"- Scenario: {scenario['name']}")
            if scenario["lines"]:
                lines.extend(f"  - {entry}" for entry in scenario["lines"])
            else:
                lines.append("  - (no GIVEN/WHEN/THEN written)")
    else:
        lines.append("- this requirement has no scenario, so nothing about it is verifiable yet")

    lines.append("")
    lines.append(f"OpenSpec change: {change['id']} ({requirement.get('kind', 'added')}"
                 + (f", capability: {capability}" if capability else "") + ")")

    return "\n".join(lines)


def _openspec_change_of(card):
    """the openspec change id a card came from, "" when it did not come from one.

    read from the import source first (that one is authoritative) and from an
    "openspec/<change>" label after that, so a card filed by hand with the label on it
    behaves the same as an imported one"""
    source = str(card.get("source") or "")
    if source.startswith("openspec:"):
        head = source[len("openspec:"):].split("#", 1)[0].strip()
        if head:
            return head

    for label in card.get("labels") or []:
        text = str(label)
        if text.startswith(OPENSPEC_LABEL + "/"):
            return text[len(OPENSPEC_LABEL + "/"):].strip()

    return ""


def _render(text, values):
    """{placeholder} replacement for prompt templates. plain replacement rather than
    str.format(**..): unknown {things} stay as their author wrote them, prose with braces in
    it survives, and no template can reach into a python object through it"""
    output = str(text or "")

    # longest key first, so a {title} inside a hypothetical {title_part} cannot be eaten by it
    for key in sorted(values, key=len, reverse=True):
        output = output.replace("{" + key + "}", str(values[key]))

    return output


def _labelify(text, limit=28):
    """a short label out of prose: lowercase, dashes instead of spaces, group numbering gone"""
    cleaned = re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")
    cleaned = re.sub(r"^\d+-", "", cleaned)

    return cleaned[:limit].strip("-")


def _shorten(text, limit=100):
    """a card title out of a line of spec prose, cut at a word boundary.

    real tasks.md lines run to 700+ characters, and a card title that long is unreadable on a
    board - the whole line still goes into the description, so shortening loses nothing. returns
    (title, shortened) so the caller knows it has to keep the original somewhere.
    """
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text, False

    cut = text[:limit]
    if " " in cut[limit // 2:]:
        cut = cut[:cut.rfind(" ")]

    return f"{cut.rstrip(' ,;:-')}\u2026", True


def _parse_openspec_tasks(text):
    """tasks.md -> [{number, group, title, done}].

    OpenSpec writes one checkbox per task, numbered hierarchically under `## 1. Group`
    headings, and checks a box off as the work lands:

        ## 1. Theme Infrastructure
        - [ ] 1.1 Create ThemeContext with light/dark state
        - [x] 1.2 Add CSS custom properties for colors

    Anything that is not a checkbox is prose and gets left alone.
    """
    tasks = []
    group = ""

    for line in str(text or "").splitlines():
        heading = HEADING_RE.match(line.strip())
        if heading:
            group = heading.group("name").strip()
            continue

        box = TASK_BOX_RE.match(line)
        if not box:
            continue

        body = box.group("body").strip()
        numbered = TASK_NUMBER_RE.match(body)

        tasks.append({
            "number": numbered.group("number") if numbered else "",
            "group": group,
            "title": (numbered.group("title") if numbered else body).strip(),
            # "[x]" and "[X]" mean done, "[!]" is what a few projects write for partial work -
            # still unfinished, so only x counts
            "done": box.group("mark").lower() == "x",
        })

    return tasks


def _parse_openspec_spec(text, capability=""):
    """a delta spec -> requirement dicts with their scenarios attached.

        ## ADDED Requirements
        ### Requirement: Two-Factor Authentication
        The system MUST support TOTP-based two-factor authentication.

        #### Scenario: 2FA login
        - GIVEN a user with 2FA enabled
        - WHEN the user submits valid credentials
        - THEN an OTP challenge is presented

    The scenarios are the point: they are the acceptance criteria a card gets, which is what
    makes an imported story testable instead of a vibe.
    """
    requirements = []
    kind = ""
    requirement = None
    scenario = None

    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line:
            continue

        delta = DELTA_KIND_RE.match(line)
        if delta:
            kind = delta.group("kind").lower()
            requirement, scenario = None, None
            continue

        scenario_match = SCENARIO_RE.match(line)
        if scenario_match and requirement is not None:
            scenario = {"name": scenario_match.group("name").strip(), "lines": []}
            requirement["scenarios"].append(scenario)
            continue

        requirement_match = REQUIREMENT_RE.match(line)
        if requirement_match:
            requirement = {
                "name": requirement_match.group("name").strip(),
                "text": "",
                "kind": kind or "added",
                "capability": capability,
                "scenarios": [],
            }
            requirements.append(requirement)
            scenario = None
            continue

        # a heading we do not model ("# Delta for Auth", "## Purpose", ..)
        if line.startswith("#"):
            continue

        body = line[1:].strip() if line.startswith("-") else line

        if scenario is not None:
            scenario["lines"].append(body)
        elif requirement is not None:
            requirement["text"] = f"{requirement['text']} {body}".strip()

    return requirements


def _parse_openspec_proposal(text, limit=14):
    """proposal.md -> the part worth putting on an epic card: intent, scope, approach"""
    blocks = []
    current = None

    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line:
            continue

        heading = HEADING_RE.match(line)
        if heading:
            name = heading.group("name").lower()
            wanted = ("intent", "scope", "approach", "why", "what")
            current = {"name": name, "lines": []} if name.startswith(wanted) else None
            if current is not None:
                blocks.append(current)
            continue

        if current is not None and len(current["lines"]) < limit:
            current["lines"].append(line)

    if blocks:
        return "\n\n".join(f"{block['name'].title()}\n" + "\n".join(block["lines"]) for block in blocks)

    # a proposal that does not follow the template is still worth showing, truncated
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip() and not line.startswith("#")]
    return "\n".join(lines[:limit])


class ProjectBoard(core.module.Module):
    """Gives you kanban / scrum project boards, one per project: you drag the cards around in the WebUI, your AI runs the same board with tools. Your play buttons are prompt templates you wrote yourself, and if the project uses OpenSpec the board can turn a change's requirements into testable stories."""

    category = "life"

    settings = {
        "insert_system_prompt": {
            "description": "Whether to keep the board in your AI's system prompt so it always knows what is on it without having to look it up first. Only open cards are listed; cards in done columns are left out to save tokens.",
            "default": True
        },
        "max_cards_in_prompt": {
            "description": "Maximum amount of cards listed in the system prompt. Board totals are always included, so your AI still knows when a big backlog is waiting.",
            "default": 40,
            "depends": "insert_system_prompt"
        },
        "default_columns": {
            "description": "Columns every new board starts out with. A column named Done, Closed, Complete or Completed is treated as a done column, which is what progress percentages are counted from. Changing this later does not touch existing boards - rename or delete columns in the WebUI instead, or ask your AI to.",
            "default": ["Backlog", "To Do", "In Progress", "Done"]
        },
        "default_board_name": {
            "description": "Name of the board your AI creates the first time the module runs, and the name the first project gets when it takes over board-less storage from an older install. Every board after that is one you or your AI name yourself.",
            "default": DEFAULT_BOARD_NAME
        },
        "keep_chat_input": {
            "description": "Keep the chat input bar at the bottom while the board is open, so you can tell your AI to change the board without leaving it. Turn this off for a full-screen board.",
            "default": True,
            "depends": "enable_webui_extension"
        },
        "enable_prompt_actions": {
            "description": "Prompt actions: prompt templates you write yourself, with {placeholders} for a card's fields in them, that the panel's play buttons drop into the chat input. Your AI can set the actions up, but pressing play stays your gesture. Turn this off to hide the play buttons and the action editor.",
            "default": True
        },
        "spec_action_prompt": {
            "description": "The prompt the panel's 'process spec' button fills into the chat, with the spec you pasted in it. Placeholders: {title}, {spec}, {board}, {backlog}, {date}. The default sends your AI off to turn the spec into an OpenSpec change and import its stories into the backlog - rewrite it if your project plans differently.",
            "default": DEFAULT_SPEC_PROMPT
        },
        "enable_openspec": {
            "description": "OpenSpec support: read openspec/changes/<change>/ and turn its requirements (each scenario becoming acceptance criteria) or its tasks.md checklist into board cards. Strictly read-only - the board never writes into your project and the openspec CLI is never run.",
            "default": True
        },
        "openspec_roots": {
            "description": "Folders your OpenSpec projects live in, so import_openspec knows where to look. Point them at the repository root that contains openspec/, or straight at the openspec folder, or at a sandbox the coder module already works in - the way coder's sandbox_paths has it. Nothing is read from anywhere outside this list.",
            "default": [],
            "depends": "enable_openspec"
        },
        "openspec_default_unit": {
            "description": "What one card stands for when a change is imported: 'requirements' makes one story per requirement with its scenarios as acceptance criteria (the testable unit), 'tasks' mirrors tasks.md with one checkbox per card, 'both' does the stories plus the task checklist.",
            "default": "requirements",
            "depends": "enable_openspec"
        },
        "openspec_max_cards": {
            "description": "How many cards one import may create in one go, so a monster spec cannot flood the backlog. Cards that are already on the board get their text refreshed regardless.",
            "default": 60,
            "depends": "enable_openspec"
        },
    }

    async def on_ready(self):
        self._broadcast_tasks = set()

        # one file per concern, each of them holding the items of *every* board: what
        # makes a card or a column belong to a board is its "board" field. one file per
        # kind keeps the data folder small and the json still easy to eyeball by hand.
        self.boards = core.storage.StorageList("project_board_boards", "json")
        self.card_store = core.storage.StorageList("project_board_cards", "json")
        self.column_store = core.storage.StorageList("project_board_columns", "json")
        self.actions = core.storage.StorageList("project_board_actions", "json")

        self.board = None

        self._migrate()

        # a fresh install gets a single board, with its columns from the settings
        if not len(self.boards):
            self._new_board(self._default_board_name())

        self._select_active()

    # ------------------------------------------------------------------
    # boards
    # ------------------------------------------------------------------

    @property
    def cards(self):
        """the cards of the active board. reads go through here so a tool can never
        reach into another project's cards by accident"""
        return self._cards_of(self.board)

    @property
    def columns(self):
        """the columns of the active board, top to bottom"""
        return self._columns_of(self.board)

    def _cards_of(self, board):
        if not board:
            return []
        return [card for card in self.card_store if card.get("board") == board["id"]]

    def _columns_of(self, board):
        if not board:
            return []

        owned = [column for column in self.column_store if column.get("board") == board["id"]]
        return sorted(owned, key=lambda column: (int(column.get("order") or 0), str(column.get("created") or "")))

    def _default_board_name(self):
        return str(self.config.get("default_board_name") or DEFAULT_BOARD_NAME).strip() or DEFAULT_BOARD_NAME

    def _new_board(self, name, description="", columns=None, activate=True):
        """creates a board with its column layout and returns it. `columns` defaults to
        the layout from the settings, which is what a fresh project starts out with"""
        names = columns if columns is not None else (self.config.get("default_columns") or [])

        board = {
            "id": self._new_id(self.boards),
            "name": str(name).strip(),
            "description": str(description or "").strip(),
            "active": False,
            "created": _now(),
            "updated": _now(),
        }
        self.boards.append(board)

        position = 0
        for column_name in names:
            column_name = str(column_name).strip()
            if not column_name:
                continue
            if any(_slug(existing["name"]) == _slug(column_name) for existing in self._columns_of(board)):
                continue

            self.column_store.append(self._new_column(column_name, board["id"], position,
                                                      done=_slug(column_name) in DONE_COLUMN_NAMES))
            position += 1

        # the first board is always the active one, after that it is your call
        if activate or not any(other.get("active") for other in self.boards):
            self.set_active(board)

        return board

    def set_active(self, board):
        """marks exactly one board as active. no storage write and no broadcast here, so
        tools and routes stay in charge of when that happens"""
        for other in self.boards:
            other["active"] = other is board

        self.board = board

    def _board_ref(self, ref):
        """board reference -> (board, problem), resolved like every other reference"""
        index, problem = self._lookup(self.boards, ref, "name")
        if index < 0:
            return None, problem

        return self.boards[index], ""

    def _boards_overview(self):
        """live counts per board, for the WebUI switcher and for list_boards"""
        overview = []

        for board in self.boards:
            cards = self._cards_of(board)
            columns = self._columns_of(board)
            done_ids = {column["id"] for column in columns if column.get("done")}

            overview.append({
                "id": board["id"],
                "name": board["name"],
                "description": board.get("description", ""),
                "active": bool(board.get("active")),
                "cards": len(cards),
                "done": len([card for card in cards if card.get("column") in done_ids]),
                "columns": len(columns),
                "points": sum(int(card.get("points") or 0) for card in cards
                              if card.get("column") not in done_ids),
            })

        return overview

    def _board_summary(self, board):
        """one line of numbers about a board, for the replies after switching or creating"""
        cards = self._cards_of(board)
        columns = self._columns_of(board)
        done_ids = {column["id"] for column in columns if column.get("done")}

        done = len([card for card in cards if card.get("column") in done_ids])
        blocked = len([card for card in cards if card.get("blocked") and card.get("column") not in done_ids])
        overdue = len([card for card in cards if card.get("column") not in done_ids and _is_overdue(card)])

        return (f"{len(cards)} cards ({done} done, {blocked} blocked, {overdue} overdue), columns: "
                + (" -> ".join(column["name"] for column in columns) or "none yet"))

    # ------------------------------------------------------------------
    # storage helpers
    # ------------------------------------------------------------------

    def _save(self):
        self.card_store.save()
        self.column_store.save()
        self.boards.save()
        self.actions.save()

    def _drop_card(self, index):
        """removes the card at an index of the active board's listing from storage"""
        entry = self.cards[index]
        self._drop_cards([entry])
        return entry

    def _drop_cards(self, entries):
        doomed = {id(entry) for entry in entries}
        self.card_store[:] = [card for card in self.card_store if id(card) not in doomed]

    def _reload(self):
        """pick up edits made by other processes / a previous session"""
        self.boards.load()
        self.card_store.load()
        self.column_store.load()
        self.actions.load()

        if not len(self.boards):
            self._new_board(self._default_board_name())

        changed = self._heal()
        self._select_active()

        if changed:
            self._save()

    def _migrate(self):
        """storage from before boards existed has no 'board' field at all: that pile of
        columns and cards becomes the first board instead of silently disappearing"""
        stray_columns = [column for column in self.column_store if not column.get("board")]
        stray_cards = [card for card in self.card_store if not card.get("board")]

        if not stray_columns and not stray_cards:
            return None

        # the migrated board keeps its own layout, so it must not be handed the default one
        board = self._new_board(self._default_board_name(), columns=[], activate=not len(self.boards))

        # the old file order was the layout, and columns had no order field of their own
        by_age = sorted(stray_columns, key=lambda entry: str(entry.get("created") or ""))
        for position, column in enumerate(by_age):
            column["board"] = board["id"]
            column["order"] = position

        for card in stray_cards:
            card["board"] = board["id"]

        self.log(self.name, f"moved {len(stray_cards)} card(s) and {len(stray_columns)} column(s) "
                            f"onto the new '{board['name']}' board")
        return board

    def _heal(self):
        """adopt items that point at a board or a column that is gone. returns whether
        anything was repaired, so the caller knows it has to write"""
        if not len(self.boards):
            return False

        changed = False
        known = {board["id"] for board in self.boards}

        for entry in list(self.column_store) + list(self.card_store):
            if entry.get("board") not in known:
                entry["board"] = self.boards[0]["id"]
                changed = True

        if changed:
            self.log(self.name, "adopted item(s) whose board no longer exists")

        # _adopt_orphans works on the active board, so take each board in turn
        restore = self.board
        for board in self.boards:
            self.board = board
            if self._adopt_orphans():
                changed = True
        self.board = restore

        if self._heal_actions():
            changed = True

        return changed

    def _heal_actions(self):
        """prompt actions that point at a board or a column that is gone. a board is adopted
        the way every other item's is; a column reference that no longer exists is dropped,
        which leaves the action doing what it still can: working board-wide"""
        if not len(self.boards):
            return False

        changed = False
        known = {board["id"] for board in self.boards}

        for action in self.actions:
            if action.get("board") not in known:
                action["board"] = self.boards[0]["id"]
                changed = True

        for board in self.boards:
            columns = {column["id"] for column in self._columns_of(board)}

            for action in self._actions_of(board):
                for key in ("column", "move_to"):
                    if action.get(key) and action[key] not in columns:
                        action[key] = ""
                        changed = True

        if changed:
            self.log(self.name, "repaired prompt action(s) pointing at a board or column that is gone")

        return changed

    def _adopt_orphans(self):
        """heal cards on the active board pointing at a column that no longer exists"""
        orphans = self._orphan_cards()
        if not orphans or not len(self.columns):
            return False

        target = self.columns[0]
        for card in orphans:
            self._place(card, target["id"])

        name = self.board["name"] if self.board else "?"
        self.log(self.name, f"moved {len(orphans)} orphan card(s) on '{name}' to {target['name']}")
        return True

    def _select_active(self):
        """self.board is the board the tools and the panel work on. a board list with no
        active flag (hand-edited storage) falls back to the first board"""
        active = next((board for board in self.boards if board.get("active")), None)
        if active is None and len(self.boards):
            active = self.boards[0]

        if active is not None and not active.get("active"):
            self.set_active(active)
        else:
            self.board = active

    def _new_column(self, name, board_id, order=0, done=False, wip_limit=0):
        return {
            "id": str(ulid.ULID()),
            "board": board_id,
            "order": int(order or 0),
            "name": str(name).strip(),
            "done": bool(done),
            "wip_limit": max(0, int(wip_limit or 0)),
            "created": _now(),
        }

    def _new_id(self, items):
        """a short id that no card on the board uses yet"""
        taken = {str(item.get("id", "")).upper() for item in items}

        while True:
            candidate = "".join(secrets.choice(ID_ALPHABET) for _ in range(ID_LENGTH))
            if candidate not in taken:
                return candidate

    def _new_card(self, title, column_id, description="", card_type="task", priority="medium",
                  assignee="", labels=None, points=0, due="", order=0, source=""):
        return {
            "id": self._new_id(self.card_store),
            "title": str(title).strip(),
            "description": str(description or ""),
            "type": str(card_type or "task").strip().lower(),
            "priority": str(priority or "medium").strip().lower(),
            "board": self.board["id"] if self.board else None,
            "column": column_id,
            "order": int(order or 0),
            "assignee": str(assignee or "").strip(),
            "labels": self._clean_labels(labels),
            "points": max(0, int(points or 0)),
            "due": str(due or "").strip(),
            "blocked": False,
            # what this card was imported from, e.g. "openspec:add-dark-mode#req:ui:theme-selection".
            # hidden from the listings - it is how re-importing updates a card instead of
            # adding a second one, not information you read
            "source": str(source or ""),
            "comments": [],
            "created": _now(),
            "updated": _now(),
        }

    def _clean_labels(self, labels):
        """normalizes a label list (or a comma / space separated string) into clean, unique labels"""
        if labels is None:
            return []
        if isinstance(labels, str):
            labels = labels.replace(",", " ").split()

        cleaned = []
        for label in labels:
            label = str(label).strip().lstrip("#")
            if label and label not in cleaned:
                cleaned.append(label)
        return cleaned

    # ------------------------------------------------------------------
    # prompt actions: templates you wrote, played from the panel
    # ------------------------------------------------------------------

    def _actions_of(self, board):
        """the prompt actions of one board, in the order the panel shows them. actions belong
        to a board the way cards do, so two projects can want completely different buttons"""
        if not board:
            return []

        owned = [action for action in self.actions if action.get("board") == board["id"]]
        return sorted(owned, key=lambda action: (int(action.get("order") or 0),
                                                 str(action.get("created") or "")))

    def _action(self, ref):
        """prompt action reference -> (index, problem), inside the active board's actions"""
        return self._lookup(self._actions_of(self.board), ref, "name")

    def _new_action(self, name, template, board_id, column="", move_to="",
                    log_as_comment=False, order=0):
        return {
            "id": self._new_id(self.actions),
            "board": board_id,
            "name": str(name).strip(),
            # the template is yours. the module only substitutes the card's fields into it,
            # so it stays plain text you can read, diff and rewrite
            "template": str(template or ""),
            # "" means the whole board; a column id means the button only shows up on cards in
            # that stage, which is how play can mean something different in review than in the
            # backlog
            "column": str(column or "").strip(),
            "move_to": str(move_to or "").strip(),
            "log_as_comment": bool(log_as_comment),
            "order": int(order or 0),
            "created": _now(),
            "updated": _now(),
        }

    def _drop_actions_of(self, board_id):
        """a board's prompt actions go with the board"""
        self.actions[:] = [action for action in self.actions if action.get("board") != board_id]

    def _card_values(self, card):
        """what {placeholders} in a template can reach for on this card"""
        column = next((entry for entry in self.columns if entry["id"] == card.get("column")), None)
        comments = card.get("comments") or []

        return {
            "id": card["id"],
            "title": card.get("title", ""),
            "description": card.get("description", ""),
            "column": column["name"] if column else "",
            "board": self.board["name"] if self.board else "",
            "type": card.get("type", ""),
            "priority": card.get("priority", ""),
            "assignee": card.get("assignee", ""),
            "labels": " ".join(f"#{label}" for label in card.get("labels") or []),
            "points": str(card.get("points") or ""),
            "due": card.get("due", ""),
            "comments": "\n".join(f"- {comment.get('author', 'ai')}: {comment.get('text', '')}"
                                  for comment in comments),
            "change": _openspec_change_of(card),
            "date": _today().isoformat(),
        }

    def _backlog_column(self):
        """where imported work waits, named {backlog} in templates: the first column that is
        not a done column, which is the same place a new card lands by default"""
        index = self._default_column_index()

        return self.columns[index]["name"] if 0 <= index < len(self.columns) else ""

    def _ui_actions(self):
        """prompt actions as the panel needs them. the panel decides per card whether an action
        applies (no column means the whole board), so it gets the references plus their names"""
        names = {column["id"]: column["name"] for column in self.columns}

        actions = []
        for action in self._actions_of(self.board):
            entry = dict(action)
            entry["column_name"] = names.get(action.get("column") or "", "")
            entry["move_to_name"] = names.get(action.get("move_to") or "", "")
            actions.append(entry)

        return actions

    def _lookup(self, items, ref, name_key="name"):
        """
        resolves a reference into an index of `items`: exact id, then exact name (card
        title), then an unambiguous name substring. short ids are how the board prints
        card ids, so the AI can copy them straight out of a listing.

        returns (index, problem), where problem is "", "unknown" or "ambiguous".
        """
        ref = str(ref or "").strip()
        if not ref:
            return -1, "unknown"

        needle = ref.lower()

        for index, item in enumerate(items):
            if str(item.get("id", "")).lower() == needle:
                return index, ""

        exact = [index for index, item in enumerate(items) if _slug(item.get(name_key)) == needle]
        if exact:
            return exact[0], ""

        partial = [index for index, item in enumerate(items) if needle in _slug(item.get(name_key))]
        if len(partial) == 1:
            return partial[0], ""
        if len(partial) > 1:
            return -1, "ambiguous"

        return -1, "unknown"

    def _column(self, ref):
        """column reference -> (index, problem)"""
        return self._lookup(self.columns, ref, "name")

    def _card(self, ref):
        """card reference -> (index, problem)"""
        return self._lookup(self.cards, ref, "title")

    def _not_found(self, kind, ref, problem):
        if problem == "ambiguous":
            return f"several {kind}s match '{ref}', please use the exact id instead"

        listing = "list_boards" if kind == "board" else "read_board"
        return f"no {kind} matching '{ref}' was found (use {listing} to list them)"

    def _column_cards(self, column_id):
        """cards of a column, in board order"""
        cards = [card for card in self.cards if card.get("column") == column_id]
        return sorted(cards, key=lambda card: (card.get("order", 0), str(card.get("created") or "")))

    def _place(self, card, column_id, index=None, before_id=None):
        """
        moves a card into a column at a position, then renumbers both the column it
        lands in and the one it leaves, so order values stay dense (0..n-1).
        index=None appends to the bottom, before_id wins over index.
        """
        previous = card.get("column")
        cards = [entry for entry in self._column_cards(column_id) if entry["id"] != card["id"]]

        if before_id:
            ids = [entry["id"] for entry in cards]
            position = ids.index(before_id) if before_id in ids else len(cards)
        elif index is None:
            position = len(cards)
        else:
            position = max(0, min(int(index), len(cards)))

        cards.insert(position, card)
        card["column"] = column_id

        for position, entry in enumerate(cards):
            entry["order"] = position

        if previous and previous != column_id:
            for offset, entry in enumerate(self._column_cards(previous)):
                entry["order"] = offset

        card["updated"] = _now()
        return position

    def _set_column_layout(self, ordered):
        """writes a top-to-bottom column order back onto the column items. columns keep
        their own order field so several boards can share one storage file"""
        for position, entry in enumerate(ordered):
            entry["order"] = position

    def _default_column_index(self):
        """where new cards land when nobody says otherwise: the first column that isn't done"""
        for index, column in enumerate(self.columns):
            if not column.get("done"):
                return index
        return 0 if len(self.columns) else -1

    def _column_is_done(self, column):
        return bool(column and column.get("done"))

    def _orphan_cards(self):
        """cards pointing at a column that no longer exists (hand-edited storage, etc)"""
        known = {column["id"] for column in self.columns}
        return [card for card in self.cards if card.get("column") not in known]

    def _wip_note(self, column):
        """warning text when a column is over its work in progress limit, empty otherwise"""
        limit = int(column.get("wip_limit") or 0)
        if limit <= 0:
            return ""

        count = len(self._column_cards(column["id"]))
        if count <= limit:
            return ""

        return f"note: {column['name']} is now over its wip limit ({count}/{limit})"

    # ------------------------------------------------------------------
    # prompts
    # ------------------------------------------------------------------

    async def on_system_prompt(self):
        if not self.config.get("insert_system_prompt"):
            return None

        self._reload()

        if not len(self.columns):
            return None

        max_cards = int(self.config.get("max_cards_in_prompt") or 0)
        listed = []
        skipped = 0
        points_open = 0

        for column in self.columns:
            cards = self._column_cards(column["id"])
            if column.get("done"):
                # done work is history: the totals above are enough for the AI
                continue

            for card in cards:
                if max_cards and len(listed) >= max_cards:
                    skipped += 1
                    continue

                points_open += int(card.get("points") or 0)

                flags = [card["id"], column["name"], f"{card.get('priority')}/{card.get('type')}"]
                line = f"[{' | '.join(flags)}] {card['title']}"

                extras = []
                if int(card.get("points") or 0):
                    extras.append(f"{card['points']}p")
                if card.get("due"):
                    extras.append(f"due {card['due']}")
                    if _is_overdue(card):
                        extras[-1] = f"OVERDUE since {card['due']}"
                if card.get("assignee"):
                    extras.append(f"@{card['assignee']}")
                if card.get("blocked"):
                    extras.append("BLOCKED")
                if card.get("labels"):
                    extras.append(" ".join(f"#{label}" for label in card["labels"]))

                if extras:
                    line += f" ({', '.join(extras)})"

                listed.append(line)

        stats = self._stats()
        intro = f"You manage the '{self.board['name']}' project board with your project-board tools."
        if "webui" in self.manager.channels:
            intro += " The user can see the board in the webui, so your changes show up for them right away."

        header = (
            f"{intro} "
            f"{stats['total']} cards, {stats['done']} done, {stats['blocked']} blocked, {stats['overdue']} overdue, "
            f"{points_open} points still open. Columns: "
            + " -> ".join(column["name"] for column in self.columns) + "."
        )

        if len(self.boards) > 1:
            others = [f"{board['id']} {board['name']}" for board in self.boards if board is not self.board]
            header += (" This is one board of several - the others are " + ", ".join(others) +
                       ". Cards never move between boards on their own; switch with activate_board "
                       "when the user means another project.")

        notes = self._prompt_notes()
        if notes:
            header += " " + " ".join(notes)

        if not len(self.cards):
            return header + "\nThe board is empty."

        output = [header, "Open cards (id | column | priority/type | title):", *listed]

        if skipped:
            output.append(f".. and {skipped} more open cards, use read_board to see them all.")

        return "\n".join(output)

    def _prompt_notes(self):
        """lines that go after the board header in the system prompt: what the user's play
        buttons are, and whether the cards here came from an openspec change. Kept short, since
        they ride along in every session"""
        notes = []

        if self.config.get("enable_prompt_actions", True):
            actions = self._actions_of(self.board)
            if actions:
                notes.append(
                    f"{len(actions)} prompt action(s) the user wrote sit on this board "
                    "(" + ", ".join(action["name"] for action in actions) + "). Pressing play only "
                    "fills their chat input, so when they say they played a card they are about to "
                    "ask you to do what that template says - list_prompt_actions shows them.")

        if self.config.get("enable_openspec", True) and self._openspec_roots():
            changes = sorted({_openspec_change_of(card) for card in self.cards} - {""})
            if changes:
                notes.append(
                    "Some cards here came from openspec changes ("
                    + ", ".join(sorted(changes)) + "). Those files are the truth about those "
                    "requirements, so import_openspec refreshes the cards instead of you retyping them.")

        return notes

    # ------------------------------------------------------------------
    # shared mutations
    # ------------------------------------------------------------------

    def _stats(self):
        """board totals, shared by the tools, the prompt and the webui"""
        done_ids = {column["id"] for column in self.columns if column.get("done")}

        stats = {
            "total": len(self.cards),
            "done": 0,
            "points_total": 0,
            "points_done": 0,
            "blocked": 0,
            "overdue": 0,
            "unassigned": 0,
            "priorities": {name: 0 for name in PRIORITIES},
            "types": {},
            "assignees": {},
            "labels": {},
            "columns": [],
        }

        for column in self.columns:
            cards = self._column_cards(column["id"])
            points = sum(int(card.get("points") or 0) for card in cards)

            stats["columns"].append({
                "id": column["id"],
                "name": column["name"],
                "cards": len(cards),
                "points": points,
                "wip_limit": int(column.get("wip_limit") or 0),
                "over_wip": int(column.get("wip_limit") or 0) > 0 and len(cards) > int(column["wip_limit"]),
            })

        for card in self.cards:
            points = int(card.get("points") or 0)
            done = card.get("column") in done_ids

            stats["points_total"] += points
            if done:
                stats["done"] += 1
                stats["points_done"] += points
            else:
                if card.get("blocked"):
                    stats["blocked"] += 1
                if _is_overdue(card):
                    stats["overdue"] += 1
                if not str(card.get("assignee") or "").strip():
                    stats["unassigned"] += 1

            if card.get("priority") in stats["priorities"]:
                stats["priorities"][card["priority"]] += 1

            card_type = str(card.get("type") or "task")
            stats["types"][card_type] = stats["types"].get(card_type, 0) + 1

            assignee = str(card.get("assignee") or "").strip()
            if assignee:
                stats["assignees"][assignee] = stats["assignees"].get(assignee, 0) + 1

            for label in card.get("labels") or []:
                stats["labels"][label] = stats["labels"].get(label, 0) + 1

        stats["progress"] = round(stats["done"] / stats["total"] * 100) if stats["total"] else 0
        return stats

    def _card_line(self, card, include_description=False):
        """one line of a board listing, for the AI and for /board"""
        flags = [f"{card.get('priority')}/{card.get('type')}"]

        line = f"  {card['id']} [{' | '.join(flags)}] {card['title']}"

        extras = []
        if int(card.get("points") or 0):
            extras.append(f"{card['points']} pts")
        if card.get("due"):
            extras.append(f"due {card['due']}")
        if str(card.get("assignee") or "").strip():
            extras.append(f"assigned to {card['assignee']}")
        if card.get("labels"):
            extras.append("labels: " + ", ".join(card["labels"]))
        if card.get("blocked"):
            extras.append("BLOCKED")
        if len(card.get("comments") or []):
            extras.append(f"{len(card['comments'])} comments")

        if extras:
            line += f" ({'; '.join(extras)})"

        if include_description and str(card.get("description") or "").strip():
            line += f"\n      {card['description'].strip().replace(chr(10), ' ')}"

        return line

    def _matches(self, card, query="", assignee="", priority="", label="", card_type=""):
        if query:
            haystack = " ".join([
                str(card.get("title") or ""),
                str(card.get("description") or ""),
                " ".join(str(text.get("text", "")) for text in card.get("comments") or []),
                " ".join(card.get("labels") or []),
            ]).lower()
            if query.lower() not in haystack:
                return False

        if assignee and _slug(card.get("assignee")) != _slug(assignee):
            return False
        if priority and _slug(card.get("priority")) != _slug(priority):
            return False
        if card_type and _slug(card.get("type")) != _slug(card_type):
            return False
        if label:
            wanted = _slug(label).lstrip("#")
            if wanted not in [_slug(entry).lstrip("#") for entry in card.get("labels") or []]:
                return False

        return True

    def broadcast_board(self, reason: str = "update"):
        """fire-and-forget push so open WebUI boards reload themselves. no-op on other channels"""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        task = loop.create_task(self._broadcast(reason))
        self._broadcast_tasks.add(task)
        task.add_done_callback(self._broadcast_tasks.discard)

    async def _broadcast(self, reason: str):
        websocket_manager = getattr(getattr(self.manager, "channel", None), "websocket_manager", None)
        if websocket_manager is None:
            return  # the active channel isn't the webui (or isn't up yet)

        try:
            await websocket_manager.broadcast({"type": "project_board", "reason": reason})
        except Exception as e:
            self.log(self.name, f"could not broadcast board update: {core.detail_error(e)}")

    # ------------------------------------------------------------------
    # tools: boards (one board per project)
    # ------------------------------------------------------------------

    @core.module.tool
    async def list_boards(self):
        """Lists every project board with its card counts and marks the active one. The
        active board is what the other tools and the panel the user sees work on.

        Returns:
            one line per board: id, name, cards (done), open points, column count
        """
        self._reload()

        if not len(self.boards):
            return self.result("no project boards were found", success=False)

        lines = ["project boards:"]
        for entry in self._boards_overview():
            line = (f"  [{entry['id']}] {entry['name']} - {entry['cards']} cards "
                    f"({entry['done']} done), {entry['points']} points open, "
                    f"{entry['columns']} columns" + (" [ACTIVE]" if entry["active"] else ""))
            lines.append(line)

            if entry["description"]:
                lines.append(f"        {entry['description']}")

        lines.append("")
        lines.append("switch with activate_board, the user can also switch it in the board's header.")

        return self.result("\n".join(lines))

    @core.module.tool
    async def create_board(self, name: str, description: str = None, columns: list = None,
                           like: str = None, activate: bool = True):
        """Creates another project board, so a second project gets its own cards and its own
        columns. Nothing is shared between boards except the person looking at them.

        Args:
            name: what the project is called, e.g. "Website redesign"
            description: what this board is for, so you still know later
            columns: column names for the new board. Defaults to the layout from the settings
            like: name or id of an existing board whose column layout to copy instead, which is
                handy when every project runs through the same stages
            activate: switch to the new board right away (default true). Set false to keep
                working on the current board
        """
        self._reload()

        name = str(name or "").strip()
        if not name:
            return self.result("a board needs a name", success=False)

        if any(_slug(existing["name"]) == _slug(name) for existing in self.boards):
            return self.result(f"there is already a board called {name}", success=False)

        # an explicit layout wins over copying one
        layout = [str(entry) for entry in columns] if columns else None

        if layout is None and like:
            source, problem = self._board_ref(like)
            if source is None:
                return self.result(self._not_found("board", like, problem), success=False)

            layout = [column["name"] for column in self._columns_of(source)] or None

        previous = self.board
        board = self._new_board(name, description or "", columns=layout, activate=bool(activate))

        self._save()
        self.broadcast_board("board_created")

        result = f"created board {board['id']} ({board['name']}) with {len(self._columns_of(board))} columns"
        if board.get("active"):
            return self.result(f"{result} - it is the active board now: " + self._board_summary(board))

        return self.result(f"{result} - still on {previous['name']}, "
                           f"switch later with activate_board('{board['id']}')")

    @core.module.tool
    async def edit_board(self, board: str, name: str = None, description: str = None):
        """Renames a project board or changes what its description says about it.

        Args:
            board: the board's id, or its name (an unambiguous part of the name works too)
            name: new name for the board
            description: what the board is for, empty string clears it
        """
        self._reload()

        entry, problem = self._board_ref(board)
        if entry is None:
            return self.result(self._not_found("board", board, problem), success=False)

        changed = []

        if name is not None and str(name).strip():
            new_name = str(name).strip()
            if any(other["id"] != entry["id"] and _slug(other["name"]) == _slug(new_name)
                   for other in self.boards):
                return self.result(f"there is already a board called {new_name}", success=False)

            entry["name"] = new_name
            changed.append(f"name -> {new_name}")

        if description is not None:
            entry["description"] = str(description).strip()
            changed.append("description")

        if not changed:
            return self.result("nothing to change", success=False)

        entry["updated"] = _now()
        self._save()
        self.broadcast_board("board_updated")

        return self.result(f"updated board {entry['name']}: " + ", ".join(changed))

    @core.module.tool
    async def activate_board(self, board: str):
        """Switches to another project board. From then on the tools, the panel the user is
        looking at and every card you add are on that board.

        Args:
            board: the board's id, or its name (an unambiguous part of the name works too)
        """
        self._reload()

        entry, problem = self._board_ref(board)
        if entry is None:
            return self.result(self._not_found("board", board, problem), success=False)

        if entry is self.board:
            return self.result(f"{entry['name']} is already the active board: {self._board_summary(entry)}")

        self.set_active(entry)
        self._save()
        self.broadcast_board("board_switched")

        return self.result(f"active board is now {entry['name']}: {self._board_summary(entry)}")

    @core.module.tool
    async def delete_board(self, board: str, force: bool = False):
        """Deletes a project board together with its columns and every card on it.
        DANGEROUS: the cards are gone, not moved somewhere else.

        Args:
            board: the board's id, or its name (an unambiguous part of the name works too)
            force: set to true when the board still has cards and the user meant it
        """
        self._reload()

        entry, problem = self._board_ref(board)
        if entry is None:
            return self.result(self._not_found("board", board, problem), success=False)

        if len(self.boards) <= 1:
            return self.result("that is the only board there is, so it cannot be deleted - clear "
                               "its columns instead or create another board first", success=False)

        cards = self._cards_of(entry)
        columns = self._columns_of(entry)

        if cards and not force:
            return self.result(f"refusing to delete {entry['name']}: {len(cards)} cards would be lost. "
                               f"Pass force=True once the user really wants the project gone.", success=False)

        was_active = bool(entry.get("active"))

        self._drop_cards(cards)
        self._drop_actions_of(entry["id"])
        for column in columns:
            self.column_store.remove(column)
        self.boards.remove(entry)

        if was_active:
            self._select_active()
        elif self.board is None:
            self._select_active()

        self._save()
        self.broadcast_board("board_deleted")

        return self.result(f"deleted board {entry['name']} with {len(cards)} card(s) and "
                           f"{len(columns)} column(s). active board is now {self.board['name']}: "
                           f"{self._board_summary(self.board)}")

    # ------------------------------------------------------------------
    # tools: reading
    # ------------------------------------------------------------------

    @core.module.tool
    async def read_board(self, column: str = None, query: str = None, assignee: str = None,
                         priority: str = None, label: str = None, card_type: str = None,
                         include_done: bool = True, include_descriptions: bool = False,
                         max_cards: int = 80, board: str = None):
        """Reads the project board as a compact listing, one line per card, with the short
        card id first (that id is what the other tools take). Call this before moving or
        editing cards so you work with real ids and titles.

        Args:
            column: only show this column (name or id)
            query: only cards whose title, description, labels or comments contain this text
            assignee: only cards assigned to this person
            priority: only cards with this priority (critical, high, medium or low)
            label: only cards carrying this label
            card_type: only cards of this type (epic, story, task, bug or chore)
            include_done: set to false to leave out columns marked as done
            include_descriptions: include each card's description under its line
            max_cards: stop after this many cards across the whole board
            board: read another board by name or id without switching to it. Defaults to the
                active board, and writing tools never touch a board you merely looked at
        """
        self._reload()

        if board:
            other, problem = self._board_ref(board)
            if other is None:
                return self.result(self._not_found("board", board, problem), success=False)
            self.board = other

        if not len(self.columns):
            return self.result(f"{self.board['name']} has no columns yet", success=False)

        only_column = None
        if column:
            index, problem = self._column(column)
            if index < 0:
                return self.result(self._not_found("column", column, problem), success=False)
            only_column = self.columns[index]

        filters = dict(query=query or "", assignee=assignee or "", priority=priority or "",
                       label=label or "", card_type=card_type or "")
        filtering = any(filters.values())

        output = []
        shown = 0
        hidden = 0

        for entry in self.columns:
            if only_column is not None and entry["id"] != only_column["id"]:
                continue
            if not include_done and self._column_is_done(entry):
                continue

            cards = [card for card in self._column_cards(entry["id"]) if self._matches(card, **filters)]

            header = f"{entry['name']}"
            if entry.get("done"):
                header += " (done column)"
            if int(entry.get("wip_limit") or 0):
                header += f" - {len(cards)}/{entry['wip_limit']} wip"
                if len(cards) > int(entry["wip_limit"]):
                    header += " OVER LIMIT"
            if len(cards):
                header += f" [{len(cards)} cards, {sum(int(c.get('points') or 0) for c in cards)} pts]"

            lines = [header]
            for card in cards:
                if max_cards and shown >= int(max_cards):
                    hidden += 1
                    continue
                shown += 1
                lines.append(self._card_line(card, include_descriptions))

            if len(lines) == 1:
                lines.append("  (empty)")

            output.append("\n".join(lines))

        # an empty board is not "no matches": show its columns so the listing still says
        # something useful about the project
        if not shown and not hidden and filtering:
            return self.result("no cards match those filters", success=False)

        if not shown and not hidden:
            output.append("nothing on this board yet - add a card, or break a project down into stories")

        stats = self._stats()
        footer = f"\nboard: {self.board['name']}" + ("" if self.board.get("active") else " (looked at, not active)") + \
                 f" - {stats['total']} cards, {stats['done']} done ({stats['progress']}%), " \
                 f"{stats['blocked']} blocked, {stats['overdue']} overdue."

        if hidden:
            footer += f" {hidden} cards were cut off by max_cards."

        return self.result("\n\n".join(output) + footer)

    @core.module.tool
    async def board_stats(self, board: str = None):
        """Summarizes the project board: progress, per-column counts, work in progress limit
        breaches, blocked and overdue cards, and a per-person workload. Great for standups.

        Args:
            board: summarize another board by name or id without switching to it
        """
        self._reload()

        if board:
            other, problem = self._board_ref(board)
            if other is None:
                return self.result(self._not_found("board", board, problem), success=False)
            self.board = other

        stats = self._stats()
        if not stats["total"]:
            return self.result(f"{self.board['name']} is empty")

        lines = [
            f"{self.board['name']}: {stats['total']} cards, {stats['done']} done ({stats['progress']}%), "
            f"{stats['total'] - stats['done']} open",
            f"points: {stats['points_done']}/{stats['points_total']} done",
            f"watch out: {stats['blocked']} blocked, {stats['overdue']} overdue, {stats['unassigned']} unassigned",
            "",
            "columns:",
        ]

        for column in stats["columns"]:
            line = f"  {column['name']}: {column['cards']} cards, {column['points']} pts"
            if column["wip_limit"]:
                line += f" (wip limit {column['wip_limit']}" + (", OVER LIMIT)" if column["over_wip"] else ")")
            lines.append(line)

        lines.append("")
        lines.append("priorities: " + ", ".join(f"{count} {name}" for name, count in stats["priorities"].items()))

        if stats["types"]:
            lines.append("types: " + ", ".join(f"{count} {name}" for name, count in sorted(stats["types"].items())))

        if stats["assignees"]:
            lines.append("workload: " + ", ".join(
                f"{name} ({count} cards)" for name, count in
                sorted(stats["assignees"].items(), key=lambda item: -item[1])
            ))
        if stats["unassigned"]:
            lines.append(f"{stats['unassigned']} cards have no assignee")

        if stats["labels"]:
            lines.append("labels: " + ", ".join(f"#{name} ({count})" for name, count in sorted(stats["labels"].items())))

        return self.result("\n".join(lines))

    # ------------------------------------------------------------------
    # tools: cards
    # ------------------------------------------------------------------

    @core.module.tool
    async def add_card(self, title: str, column: str = None, description: str = None,
                       card_type: str = "task", priority: str = "medium", assignee: str = None,
                       labels: list = None, points: int = 0, due: str = None,
                       blocked: bool = False, to_top: bool = False):
        """Creates a card (user story, task, bug, ..) on the project board.

        Args:
            title: one line saying what the card is about
            column: name or id of the column to put it in. Defaults to the first column that isn't done
            description: longer description, acceptance criteria, notes
            card_type: epic, story, task, bug or chore
            priority: critical, high, medium or low
            assignee: who is doing this
            labels: array of short label strings, e.g. ["backend", "ux"]
            points: scrum story points (0 means not estimated yet)
            due: due date as YYYY-MM-DD
            blocked: create the card in a blocked state (it is waiting on something)
            to_top: insert at the top of the column instead of the bottom
        """
        self._reload()

        title = str(title or "").strip()
        if not title:
            return self.result("a card needs a title", success=False)

        column_index = -1
        if column:
            column_index, problem = self._column(column)
            if column_index < 0:
                return self.result(self._not_found("column", column, problem), success=False)
        else:
            column_index = self._default_column_index()

        if column_index < 0:
            return self.result("the board has no columns, create one with add_column first", success=False)

        target = self.columns[column_index]

        card_type = _slug(card_type) or "task"
        if card_type not in CARD_TYPES:
            return self.result(f"unknown card type '{card_type}', use one of: {', '.join(CARD_TYPES)}", success=False)

        priority = _slug(priority) or "medium"
        if priority not in PRIORITIES:
            return self.result(f"unknown priority '{priority}', use one of: {', '.join(PRIORITIES)}", success=False)

        due = str(due or "").strip()
        if due:
            try:
                due = datetime.date.fromisoformat(due).isoformat()
            except ValueError:
                return self.result("the due date must look like 2026-12-31", success=False)

        card = self._new_card(
            title=title,
            column_id=target["id"],
            description=description or "",
            card_type=card_type,
            priority=priority,
            assignee=assignee or "",
            labels=labels,
            points=points or 0,
            due=due,
        )

        card["blocked"] = bool(blocked)

        self._place(card, target["id"], index=0 if to_top else None)
        self.card_store.append(card)
        self._save()
        self.broadcast_board("card_added")

        result = f"added card {card['id']} to {target['name']}: {card['title']}"
        note = self._wip_note(target)
        return self.result(f"{result}\n{note}" if note else result)

    @core.module.tool
    async def add_cards(self, cards: list, column: str = None, card_type: str = None,
                        priority: str = None, assignee: str = None, labels: list = None,
                        points: int = 0, due: str = None, to_top: bool = False):
        """Adds a whole batch of cards in one call, which is what you want when you break a spec or
        a project down: one write, one push to the panel, and a per-item report of what landed. For
        an OpenSpec change prefer import_openspec, which reads the stories out of the files instead
        of out of your memory of them.

        Args:
            cards: array of card objects. each one takes the same fields as add_card: "title"
                (required) plus any of "description", "type", "priority", "assignee", "labels",
                "points", "due" (YYYY-MM-DD), "blocked" and "column" (name or id, which overrides
                where the batch lands). They are appended in the order you list them
            column: where the batch lands when an item does not say. Defaults to the first column
                that is not done
            card_type: type for the items that do not name one (epic, story, task, bug, chore)
            priority: priority for the items that do not name one (critical, high, medium, low)
            assignee: assignee for the items that do not name one
            labels: labels for every card in the batch, on top of the ones an item carries
            points: points for the items that do not name one
            due: due date for the items that do not name one (YYYY-MM-DD)
            to_top: put the batch at the top of its column instead of at the bottom, keeping the
                order you listed it in
        """
        self._reload()

        if not len(self.columns):
            return self.result("the board has no columns, create one with add_column first", success=False)

        if not isinstance(cards, (list, tuple)) or not len(cards):
            return self.result("give me a list of card objects to add", success=False)

        if column:
            column_index, problem = self._column(column)
            if column_index < 0:
                return self.result(self._not_found("column", column, problem), success=False)
            default_column = self.columns[column_index]
        else:
            index = self._default_column_index()
            if index < 0:
                return self.result("the board has no columns, create one with add_column first", success=False)
            default_column = self.columns[index]

        default_type = _slug(card_type) or "task"
        default_priority = _slug(priority) or "medium"
        if default_type not in CARD_TYPES:
            return self.result(f"unknown card type '{default_type}', use one of: {', '.join(CARD_TYPES)}", success=False)
        if default_priority not in PRIORITIES:
            return self.result(f"unknown priority '{default_priority}', use one of: {', '.join(PRIORITIES)}", success=False)

        batch_labels = self._clean_labels(labels)
        added = []
        problems = []

        for position, item in enumerate(cards):
            if not isinstance(item, dict):
                problems.append(f"item {position + 1}: expected an object with a title, got {item}")
                continue

            title = str(item.get("title") or "").strip()
            if not title:
                problems.append(f"item {position + 1}: no title")
                continue

            target = default_column
            if item.get("column"):
                column_index, problem = self._column(item["column"])
                if column_index < 0:
                    problems.append(f"{title}: {self._not_found('column', item['column'], problem)}")
                    continue
                target = self.columns[column_index]

            item_type = _slug(item.get("type")) or default_type
            if item_type not in CARD_TYPES:
                problems.append(f"{title}: unknown card type '{item_type}'")
                continue

            item_priority = _slug(item.get("priority")) or default_priority
            if item_priority not in PRIORITIES:
                problems.append(f"{title}: unknown priority '{item_priority}'")
                continue

            due = str(item.get("due") or due or "").strip()
            if due:
                try:
                    due = datetime.date.fromisoformat(due).isoformat()
                except ValueError:
                    problems.append(f"{title}: the due date must look like 2026-12-31, got '{due}'")
                    continue

            card = self._new_card(
                title=title,
                column_id=target["id"],
                description=str(item.get("description") or ""),
                card_type=item_type,
                priority=item_priority,
                assignee=str(item.get("assignee") or assignee or ""),
                labels=batch_labels + (item.get("labels") or []),
                points=int(item.get("points") or points or 0),
                due=due,
            )
            card["blocked"] = bool(item.get("blocked"))

            # to_top keeps the order the batch was listed in: each card lands below the ones
            # already placed rather than always at position 0
            self._place(card, target["id"], index=position if to_top else None)
            self.card_store.append(card)
            added.append((card, target))

        if not added:
            return self.result("none of those cards could be added:\n" + "\n".join(problems), success=False)

        # one write and one push for the whole batch, so the panel does not flicker per card
        self._save()
        self.broadcast_board("cards_added")

        lines = [f"added {len(added)} card(s):"]
        for card, target in added:
            lines.append(f"  [{card['id']}] {target['name']} - {card['title']}")

        if problems:
            lines.append(f"{len(problems)} item(s) were skipped:")
            lines.extend(f"  - {problem}" for problem in problems)

        # one wip note per column the batch touched, not one per card
        touched = {}
        for _card, target in added:
            touched[target["id"]] = target

        for target in touched.values():
            note = self._wip_note(target)
            if note:
                lines.append(note)

        return self.result("\n".join(lines))

    @core.module.tool
    async def edit_card(self, card: str, title: str = None, description: str = None,
                        card_type: str = None, priority: str = None, assignee: str = None,
                        labels: list = None, points: int = None, due: str = None, blocked: bool = None):
        """Edits a card. Only the fields you pass are changed. Pass an empty string to clear
        description, assignee, labels or due.

        Args:
            card: the card's short id, or its title (an unambiguous part of the title works too)
            title: new title
            description: new description
            card_type: epic, story, task, bug or chore
            priority: critical, high, medium or low
            assignee: who is doing this (empty string to unassign)
            labels: replacement array of labels (empty array to clear them all)
            points: scrum story points, 0 to clear the estimate
            due: due date as YYYY-MM-DD, empty string to remove the deadline
            blocked: mark the card blocked (true) or unblocked (false)
        """
        self._reload()

        index, problem = self._card(card)
        if index < 0:
            return self.result(self._not_found("card", card, problem), success=False)

        entry = self.cards[index]
        changed = []

        if title is not None and str(title).strip():
            entry["title"] = str(title).strip()
            changed.append("title")
        if description is not None:
            entry["description"] = str(description)
            changed.append("description")
        if card_type is not None:
            value = _slug(card_type)
            if value not in CARD_TYPES:
                return self.result(f"unknown card type '{value}', use one of: {', '.join(CARD_TYPES)}", success=False)
            entry["type"] = value
            changed.append("type")
        if priority is not None:
            value = _slug(priority)
            if value not in PRIORITIES:
                return self.result(f"unknown priority '{value}', use one of: {', '.join(PRIORITIES)}", success=False)
            entry["priority"] = value
            changed.append("priority")
        if assignee is not None:
            entry["assignee"] = str(assignee).strip()
            changed.append("assignee")
        if labels is not None:
            entry["labels"] = self._clean_labels(labels)
            changed.append("labels")
        if points is not None:
            entry["points"] = max(0, int(points))
            changed.append("points")
        if due is not None:
            due = str(due).strip()
            if due:
                try:
                    due = datetime.date.fromisoformat(due).isoformat()
                except ValueError:
                    return self.result("the due date must look like 2026-12-31", success=False)
            entry["due"] = due
            changed.append("due")
        if blocked is not None:
            entry["blocked"] = bool(blocked)
            changed.append("blocked")

        if not changed:
            return self.result("nothing to change", success=False)

        entry["updated"] = _now()
        self._save()
        self.broadcast_board("card_updated")

        return self.result(f"updated {', '.join(changed)} on {entry['id']}: {entry['title']}")

    @core.module.tool
    async def move_card(self, card: str, column: str, before_card: str = None, to_top: bool = False):
        """Moves a card to another column (and therefore to another stage of the project), or
        repositions it inside its own column. Use this whenever work progresses on a card.

        Args:
            card: the card's short id, or its title (an unambiguous part of the title works too)
            column: name or id of the target column
            before_card: sit this card directly above another card (id or title) in that column
            to_top: put the card at the very top of the column
        """
        self._reload()

        index, problem = self._card(card)
        if index < 0:
            return self.result(self._not_found("card", card, problem), success=False)

        entry = self.cards[index]

        column_index, problem = self._column(column)
        if column_index < 0:
            return self.result(self._not_found("column", column, problem), success=False)
        target = self.columns[column_index]

        before_id = None
        if before_card:
            before_index, problem = self._card(before_card)
            if problem == "ambiguous":
                return self.result(self._not_found("card", before_card, problem), success=False)
            if before_index >= 0:
                before_id = self.cards[before_index]["id"]

        position = self._place(entry, target["id"], index=0 if to_top else None, before_id=before_id)
        self._save()
        self.broadcast_board("card_moved")

        result = f"moved {entry['id']} ({entry['title']}) to {target['name']}, position {position + 1}"
        note = self._wip_note(target)
        return self.result(f"{result}\n{note}" if note else result)

    @core.module.tool
    async def reorder_column(self, column: str, card_ids: list):
        """Sets the top-to-bottom order of cards inside a column, which is how you prioritize
        the work. Cards you leave out keep their relative order and stay below the ones you listed.

        Args:
            column: name or id of the column
            card_ids: array of card short ids in the order you want them, top first
        """
        self._reload()

        column_index, problem = self._column(column)
        if column_index < 0:
            return self.result(self._not_found("column", column, problem), success=False)
        target = self.columns[column_index]

        ordered = []
        for ref in card_ids or []:
            index, prob = self._card(ref)
            if index < 0:
                return self.result(self._not_found("card", ref, prob), success=False)

            entry = self.cards[index]
            if entry["column"] != target["id"]:
                return self.result(f"{entry['id']} is not in {target['name']}, move it first", success=False)
            if entry not in ordered:
                ordered.append(entry)

        if not ordered:
            return self.result("give me at least one card id to order", success=False)

        rest = [entry for entry in self._column_cards(target["id"]) if entry not in ordered]

        for position, entry in enumerate(ordered + rest):
            entry["order"] = position
            entry["updated"] = _now()

        self._save()
        self.broadcast_board("column_reordered")

        return self.result(
            f"order in {target['name']} is now: " + " > ".join(entry["title"] for entry in ordered)
        )

    @core.module.tool
    async def duplicate_card(self, card: str, column: str = None):
        """Copies a card (its title, description, type, priority, labels and points - not its
        comments), which is handy for repeating work.

        Args:
            card: the card's short id, or its title (an unambiguous part of the title works too)
            column: column for the copy. Defaults to the original card's column
        """
        self._reload()

        index, problem = self._card(card)
        if index < 0:
            return self.result(self._not_found("card", card, problem), success=False)
        source = self.cards[index]

        if column:
            target_index, problem = self._column(column)
            if target_index < 0:
                return self.result(self._not_found("column", column, problem), success=False)
            target = self.columns[target_index]
        else:
            # stay where the original is
            target = next((other for other in self.columns if other["id"] == source.get("column")), None)
            if target is None:
                target = self.columns[self._default_column_index()]
        copy = self._new_card(
            title=f"{source['title']} (copy)",
            column_id=target["id"],
            description=source.get("description", ""),
            card_type=source.get("type", "task"),
            priority=source.get("priority", "medium"),
            assignee=source.get("assignee", ""),
            labels=source.get("labels") or [],
            points=source.get("points", 0),
            due=source.get("due", ""),
        )

        # right below the original, so the pair stays together
        below = len([entry for entry in self._column_cards(target["id"])
                     if entry["order"] <= source.get("order", 0)])

        self._place(copy, target["id"], index=below)
        self.card_store.append(copy)
        self._save()
        self.broadcast_board("card_duplicated")

        return self.result(f"copied to {copy['id']} in {target['name']}")

    @core.module.tool
    async def delete_card(self, card: str):
        """Deletes a card for good, comments included. Only use this when the user asked for it.

        Args:
            card: the card's short id, or its title (an unambiguous part of the title works too)
        """
        self._reload()

        index, problem = self._card(card)
        if index < 0:
            return self.result(self._not_found("card", card, problem), success=False)

        entry = self._drop_card(index)
        self._save()
        self.broadcast_board("card_deleted")

        return self.result(f"deleted card {entry['title']}")

    @core.module.tool
    async def add_comment(self, card: str, text: str, author: str = "ai"):
        """Adds a comment to a card. Use this to leave progress notes, findings or open
        questions on a card instead of just answering in chat.

        Args:
            card: the card's short id, or its title (an unambiguous part of the title works too)
            text: the comment
            author: who the comment is from, defaults to "ai"
        """
        self._reload()

        index, problem = self._card(card)
        if index < 0:
            return self.result(self._not_found("card", card, problem), success=False)

        text = str(text or "").strip()
        if not text:
            return self.result("a comment cannot be empty", success=False)

        entry = self.cards[index]
        entry.setdefault("comments", []).append({
            "id": str(ulid.ULID()),
            "author": str(author or "ai").strip() or "ai",
            "text": text,
            "created": _now(),
        })
        entry["updated"] = _now()
        self._save()
        self.broadcast_board("comment_added")

        return self.result(f"commented on {entry['title']}")

    @core.module.tool
    async def delete_comment(self, card: str, comment: str):
        """Removes a comment from a card.

        Args:
            card: the card's short id, or its title (an unambiguous part of the title works too)
            comment: the comment's id, or the comment's text
        """
        self._reload()

        index, problem = self._card(card)
        if index < 0:
            return self.result(self._not_found("card", card, problem), success=False)

        entry = self.cards[index]
        comments = entry.get("comments") or []

        needle = str(comment or "").strip().lower()

        found_index = next((position for position, item in enumerate(comments)
                            if str(item.get("id", "")).lower() == needle or _slug(item.get("text")) == needle), -1)
        if found_index < 0:
            found_index = next((position for position, item in enumerate(comments)
                                if needle and needle in _slug(item.get("text"))), -1)

        if found_index < 0:
            return self.result("no such comment on that card", success=False)

        comments.pop(found_index)
        entry["updated"] = _now()
        self._save()
        self.broadcast_board("comment_deleted")

        return self.result("comment removed")

    # ------------------------------------------------------------------
    # tools: columns
    # ------------------------------------------------------------------

    @core.module.tool
    async def add_column(self, name: str, after: str = None, wip_limit: int = 0, done: bool = False):
        """Adds a column (a stage of your workflow, such as "In Review") to the project board.

        Args:
            name: the column's name
            after: put it after this column (name or id). Defaults to the end of the board
            wip_limit: max work in progress cards allowed in it (0 = no limit)
            done: whether cards here count as finished work, which is what progress is counted from
        """
        self._reload()

        name = str(name or "").strip()
        if not name:
            return self.result("a column needs a name", success=False)

        if any(_slug(existing["name"]) == _slug(name) for existing in self.columns):
            return self.result(f"there is already a column called {name}", success=False)

        position = len(self.columns)
        if after:
            index, problem = self._column(after)
            if index < 0:
                return self.result(self._not_found("column", after, problem), success=False)
            position = index + 1

        column = self._new_column(name, self.board["id"], 0, done=done, wip_limit=wip_limit)
        self.column_store.append(column)

        layout = [entry for entry in self.columns if entry["id"] != column["id"]]
        layout.insert(position, column)
        self._set_column_layout(layout)

        self._save()
        self.broadcast_board("column_added")

        return self.result(f"added column {name} at position {position + 1}")

    @core.module.tool
    async def update_column(self, column: str, name: str = None, wip_limit: int = None,
                            done: bool = None, position: int = None):
        """Renames a column, changes its work in progress limit or done flag, or moves it
        somewhere else on the board.

        Args:
            column: name or id of the column
            name: new name
            wip_limit: new work in progress limit (0 removes the limit)
            done: whether cards here count as finished work
            position: new zero-based position of the column on the board
        """
        self._reload()

        index, problem = self._column(column)
        if index < 0:
            return self.result(self._not_found("column", column, problem), success=False)

        entry = self.columns[index]
        changed = []

        if name is not None and str(name).strip():
            new_name = str(name).strip()
            taken = any(other["id"] != entry["id"] and _slug(other["name"]) == _slug(new_name)
                        for other in self.columns)
            if taken:
                return self.result(f"there is already a column called {new_name}", success=False)

            entry["name"] = new_name
            changed.append(f"name -> {entry['name']}")
        if wip_limit is not None:
            entry["wip_limit"] = max(0, int(wip_limit))
            changed.append(f"wip limit -> {entry['wip_limit'] or 'none'}")
        if done is not None:
            entry["done"] = bool(done)
            changed.append(f"counts as done -> {entry['done']}")

        if position is not None:
            target = max(0, min(int(position), len(self.columns) - 1))

            layout = [other for other in self.columns if other["id"] != entry["id"]]
            layout.insert(target, entry)
            self._set_column_layout(layout)

            changed.append(f"position -> {target + 1}")

        if not changed:
            return self.result("nothing to change", success=False)

        self._save()
        self.broadcast_board("column_updated")

        return self.result(f"updated column {entry['name']}: " + ", ".join(changed))

    @core.module.tool
    async def delete_column(self, column: str, cards: str = "move", target_column: str = None):
        """Deletes a column from the project board.

        Args:
            column: name or id of the column
            cards: what to do with the cards inside it: "move" them elsewhere, or "delete" them
            target_column: where to move the cards. Defaults to the first remaining column
        """
        self._reload()

        index, problem = self._column(column)
        if index < 0:
            return self.result(self._not_found("column", column, problem), success=False)

        if len(self.columns) <= 1:
            return self.result("you cannot delete the only column on the board", success=False)

        entry = self.columns[index]
        inside = self._column_cards(entry["id"])
        mode = _slug(cards) or "move"

        if inside and mode not in ("move", "delete"):
            return self.result("cards must be either 'move' or 'delete'", success=False)

        target = None
        if inside and mode == "move":
            if target_column:
                target_index, problem = self._column(target_column)
                if target_index < 0:
                    return self.result(self._not_found("column", target_column, problem), success=False)
                if target_index == index:
                    return self.result("the target column is the column being deleted", success=False)
                target = self.columns[target_index]
            else:
                target = next((other for other in self.columns
                               if other["id"] != entry["id"] and not other.get("done")), None)
                if target is None:
                    target = next((other for other in self.columns if other["id"] != entry["id"]), None)

            for card in inside:
                self._place(card, target["id"])

        if mode == "delete":
            self._drop_cards(inside)

        self.column_store.remove(entry)
        self._set_column_layout(self.columns)

        # prompt actions scoped to a column that is gone would otherwise keep promising a
        # button that never appears, so they go back to working board-wide
        for action in self._actions_of(self.board):
            if action.get("column") == entry["id"]:
                action["column"] = ""
            if action.get("move_to") == entry["id"]:
                action["move_to"] = ""

        self._save()
        self.broadcast_board("column_deleted")

        if not inside:
            return self.result(f"deleted the empty column {entry['name']}")
        if mode == "delete":
            return self.result(f"deleted column {entry['name']} and its {len(inside)} cards")

        return self.result(f"deleted column {entry['name']}, moved {len(inside)} cards to {target['name']}")

    # ------------------------------------------------------------------
    # tools: prompt actions (templates you wrote, buttons you press)
    # ------------------------------------------------------------------

    @core.module.tool
    async def list_prompt_action_examples(self):
        """Lists the prompt templates the module ships as starting points for the board's play
        buttons. They are only examples: nothing is created by looking at them, and the user can
        pick one in the panel's action editor and edit it into whatever they want.

        Returns:
            one entry per example: name, the column it suits, a one line blurb
        """
        lines = [f"{len(ACTION_EXAMPLES)} prompt action templates the module ships as a starting point:"]

        for example in ACTION_EXAMPLES:
            lines.append(f"  {example['name']} - suits: "
                         f"{example['column'] or 'any card on the board'} - {example['blurb']}")

        lines.append("")
        lines.append("ask the user to pick one in the panel's action editor (board settings -> prompt"
                      " actions), or offer to write one from scratch with add_prompt_action.")
        lines.append("placeholders a template can use: " + " ".join(f"{{{key}}}" for key in CARD_PLACEHOLDERS))

        return self.result("\n".join(lines))

    @core.module.tool
    async def list_prompt_actions(self):
        """Lists the play buttons the active board has: the prompt templates the user wrote, which
        cards they show up on, and what they do besides filling the chat input. Useful to know what
        a "I pressed play on that card" from the user is actually about to ask you to do.

        Returns:
            one line per action: id, name, scope, side effects, and the template itself
        """
        self._reload()

        actions = self._actions_of(self.board)
        board_name = self.board["name"] if self.board else "?"

        if not actions:
            return self.result(f"the '{board_name}' board has no prompt actions yet, so nothing has a "
                               "play button on it. list_prompt_action_examples shows the templates the "
                               "module ships as a starting point, and the user can also set them up in "
                               "the panel's action editor")

        names = {column["id"]: column["name"] for column in self.columns}
        lines = [f"prompt actions on the '{board_name}' board "
                 "(the panel shows one play button per action that applies to a card):"]

        for action in actions:
            notes = ["every card" if not action.get("column") else names.get(action["column"], "a vanished column")]
            if action.get("move_to"):
                notes.append(f"moves the card to {names.get(action['move_to'], '?')}")
            if action.get("log_as_comment"):
                notes.append("logs the prompt on the card")

            lines.append(f"  [{action['id']}] {action['name']} - {'; '.join(notes)}")
            lines.append("        " + str(action.get("template", "")).replace("\n", "\n        "))

        lines.append("")
        lines.append("pressing play only fills the chat input - the user still sends it.")

        return self.result("\n".join(lines))

    @core.module.tool
    async def add_prompt_action(self, name: str, template: str, column: str = None,
                                move_to: str = None, log_as_comment: bool = False):
        """Adds one play button to the active board: a prompt template you write, which the panel
        fills with the card's fields and drops into the chat input when the user presses it. Do not
        invent what a button should say - ask the user, or start from list_prompt_action_examples.

        Args:
            name: what the button says, e.g. "Implement this task"
            template: the prompt, written for you to act on, with {placeholders} for the card's
                fields in it: {id} {title} {description} {column} {board} {type} {priority}
                {assignee} {labels} {points} {due} {comments} {change} {date}. Braces around
                anything else are left exactly as written, so json and code survive
            column: only offer this button on cards in this column (name or id). Leave it out to
                offer it on every card of the board. list_prompt_action_examples suggests one per
                example, but only the user's own columns exist, so treat it as a suggestion
            move_to: move the card to this column (name or id) when the button is pressed. Only
                worth it for a button that means "this stage is done"
            log_as_comment: also leave the rendered prompt on the card as a comment, so there is a
                trail of what each press did
        """

        problem = self._prompt_actions_off()
        if problem:
            return self.result(problem, success=False)
        self._reload()

        if not self.board:
            return self.result("there is no active board to add an action to", success=False)

        name = str(name or "").strip()
        template = str(template or "")

        if not name:
            return self.result("a prompt action needs a name - it is what the button says", success=False)
        if not template.strip():
            return self.result("a prompt action needs a template - what the button fills into the chat",
                               success=False)

        if any(_slug(existing["name"]) == _slug(name) for existing in self._actions_of(self.board)):
            return self.result(f"the board already has a prompt action called {name}", success=False)

        column_id, problem = self._scoped_column(column)
        if problem:
            return self.result(problem, success=False)

        move_id, problem = self._scoped_column(move_to, "move_to")
        if problem:
            return self.result(problem, success=False)

        action = self._new_action(name, template, self.board["id"], column=column_id,
                                  move_to=move_id, log_as_comment=bool(log_as_comment),
                                  order=len(self._actions_of(self.board)))
        self.actions.append(action)
        self._save()
        self.broadcast_board("actions_changed")

        names = {column["id"]: column["name"] for column in self.columns}
        scope = "every card" if not column_id else f"cards in {names.get(column_id, '?')}"
        result = f"added prompt action {action['id']} ({action['name']}) for {scope}"

        preview = self._action_preview(action)
        if preview:
            result += f"\n\nit renders to:\n{preview}"

        return self.result(result)

    @core.module.tool
    async def edit_prompt_action(self, action: str, name: str = None, template: str = None,
                                 column: str = None, move_to: str = None, log_as_comment: bool = None,
                                 order: int = None):
        """Edits one of the board's play buttons. Only what you pass is changed.

        Args:
            action: the action's id, or its name (an unambiguous part of the name works too)
            name: what the button says
            template: the prompt, with {placeholders} for the card's fields in it
            column: restrict the button to this column (name or id), "" for the whole board
            move_to: move the card here when pressed (name or id), "" for no move
            log_as_comment: leave the rendered prompt on the card as a comment
            order: swap places with the action sitting at this zero-based position, which is how
                you put the button the user presses most in front
        """

        problem = self._prompt_actions_off()
        if problem:
            return self.result(problem, success=False)
        self._reload()

        index, problem = self._action(action)
        if index < 0:
            return self.result(self._not_found("prompt action", action, problem), success=False)

        actions = self._actions_of(self.board)
        entry = actions[index]
        changed = []

        if name is not None and str(name).strip():
            new_name = str(name).strip()
            if any(other["id"] != entry["id"] and _slug(other["name"]) == _slug(new_name) for other in actions):
                return self.result(f"the board already has a prompt action called {new_name}", success=False)
            entry["name"] = new_name
            changed.append(f"name -> {new_name}")

        if template is not None:
            if not str(template).strip():
                return self.result("a prompt action cannot have an empty template", success=False)
            entry["template"] = str(template)
            changed.append("template")

        if column is not None:
            column_id, problem = self._scoped_column(column)
            if problem:
                return self.result(problem, success=False)
            entry["column"] = column_id
            changed.append(f"scope -> {column_id or 'whole board'}")

        if move_to is not None:
            move_id, problem = self._scoped_column(move_to, "move_to")
            if problem:
                return self.result(problem, success=False)
            entry["move_to"] = move_id
            changed.append(f"moves to -> {move_id or 'nowhere'}")

        if log_as_comment is not None:
            entry["log_as_comment"] = bool(log_as_comment)
            changed.append(f"logs the prompt -> {entry['log_as_comment']}")

        if order is not None:
            target = max(0, min(int(order), len(actions) - 1))
            other = actions[target]

            entry["order"], other["order"] = other["order"], entry["order"]
            changed.append(f"position -> {target + 1}")

        if not changed:
            return self.result("nothing to change", success=False)

        entry["updated"] = _now()
        self._save()
        self.broadcast_board("actions_changed")

        return self.result(f"updated prompt action {entry['name']}: " + ", ".join(changed))

    @core.module.tool
    async def delete_prompt_action(self, action: str):
        """Removes one of the board's play buttons. The cards are untouched.

        Args:
            action: the action's id, or its name (an unambiguous part of the name works too)
        """

        problem = self._prompt_actions_off()
        if problem:
            return self.result(problem, success=False)
        self._reload()

        index, problem = self._action(action)
        if index < 0:
            return self.result(self._not_found("prompt action", action, problem), success=False)

        entry = self._actions_of(self.board)[index]
        self.actions[:] = [other for other in self.actions if other["id"] != entry["id"]]

        self._save()
        self.broadcast_board("actions_changed")

        return self.result(f"deleted prompt action {entry['name']}")

    def _scoped_column(self, ref, argument="column"):
        """a prompt action's column reference -> (column id, problem). "" and None mean "the
        whole board", which is a real answer here rather than a missing argument"""
        if ref is None or not str(ref).strip():
            return "", ""

        index, problem = self._column(ref)
        if index < 0:
            return "", self._not_found("column", ref, problem)

        return self.columns[index]["id"], ""

    def _action_preview(self, action):
        """what an action's template turns into on the first card it would apply to, so a
        template can be judged by what it actually says rather than by its placeholders"""
        cards = self._column_cards(action["column"]) if action.get("column") else self.cards

        for card in cards:
            return _render(action.get("template", ""), self._card_values(card))

        return ""

    def _prompt_actions_off(self):
        """prompt actions are the user's to switch off, and then nothing should be writing them:
        not the panel, which hides the editor, and not the AI, which still has the tools"""
        if not self.config.get("enable_prompt_actions", True):
            return ("prompt actions are switched off in the project-board settings, so there are "
                    "no play buttons to configure - the user can turn them back on in the settings")

        return ""

    async def _play_action(self, action_ref, card_ref):
        """what the panel's play button does: render the template for the card, then apply the
        side effects the action was configured with. filling the chat input is the browser's job -
        a tool call never starts a turn, and neither does a button here"""

        problem = self._prompt_actions_off()
        if problem:
            return self.result(problem, success=False)
        self._reload()

        index, problem = self._card(card_ref)
        if index < 0:
            return self.result(self._not_found("card", card_ref, problem), success=False)
        card = self.cards[index]

        action_index, problem = self._action(action_ref)
        if action_index < 0:
            return self.result(self._not_found("prompt action", action_ref, problem), success=False)
        action = self._actions_of(self.board)[action_index]

        prompt = _render(action.get("template", ""), self._card_values(card))

        return self.result({
            "action": action["id"],
            "name": action["name"],
            "prompt": prompt,
            "card": card["id"],
            # the panel tells the user whether the prompt landed in the input or nowhere
            "column": action.get("column") or "",
            "move_to": action.get("move_to") or "",
            "log_as_comment": bool(action.get("log_as_comment")),
        })

    async def _action_launched(self, action_ref, card_ref, prompt=None):
        """the second half of a press: the side effects the action configures, recorded at the
        moment the button was pressed rather than when the message eventually gets sent"""

        problem = self._prompt_actions_off()
        if problem:
            return self.result(problem, success=False)
        self._reload()

        index, problem = self._card(card_ref)
        if index < 0:
            return self.result(self._not_found("card", card_ref, problem), success=False)
        card = self.cards[index]

        action_index, problem = self._action(action_ref)
        if action_index < 0:
            return self.result(self._not_found("prompt action", action_ref, problem), success=False)
        action = self._actions_of(self.board)[action_index]

        done = []

        if action.get("log_as_comment"):
            text = str(prompt or _render(action.get("template", ""), self._card_values(card))).strip()
            if text:
                card.setdefault("comments", []).append({
                    "id": str(ulid.ULID()),
                    "author": f"action:{action['name']}",
                    "text": text,
                    "created": _now(),
                })
                card["updated"] = _now()
                done.append("logged the prompt on the card")

        if action.get("move_to"):
            target = next((column for column in self.columns if column["id"] == action["move_to"]), None)
            if target is not None and card.get("column") != target["id"]:
                self._place(card, target["id"])
                done.append(f"moved it to {target['name']}")
            elif target is None:
                done.append("its column is gone, so it did not move")

        if done:
            self._save()
            self.broadcast_board("card_updated")

        return self.result(f"{action['name']} on {card['id']}: " + ", ".join(done) if done
                           else f"{action['name']} on {card['id']}: nothing else to do")

    # ------------------------------------------------------------------
    # tools: openspec (read a change folder, land its stories)
    # ------------------------------------------------------------------
    #
    # the integration is with OpenSpec's files rather than with its CLI: openspec writes plain
    # markdown (### Requirement:, #### Scenario: with - WHEN / - THEN, tasks.md checkboxes), so
    # the board can read a change whether or not the CLI is installed. it never runs it, and it
    # never writes to your project - ticking a box in tasks.md stays the job of whatever module
    # you edit code with. only folders named in openspec_roots can be read at all.

    def _openspec_ready(self):
        """single gate for everything openspec, so a disabled module says so once, plainly"""
        if not self.config.get("enable_openspec", True):
            return "openspec support is turned off in the project-board settings"

        return ""

    def _openspec_roots(self):
        """the folders the user allowed openspec reading from, as [(as configured, absolute)]"""
        roots = []

        for raw in self.config.get("openspec_roots") or []:
            text = str(raw or "").strip()
            if not text:
                continue

            absolute = os.path.abspath(os.path.expanduser(text))
            if not any(absolute == known for _shown, known in roots):
                roots.append((text, absolute))

        return roots

    def _openspec_root(self, ref=None):
        """root reference -> (as configured, absolute, problem). resolving against the settings
        list instead of accepting a path is the point: the user decides once, in the settings,
        which folders this module may read from, and nothing outside that list can be reached"""
        roots = self._openspec_roots()

        if not roots:
            return "", "", ("no openspec folder is configured. set openspec_roots to the repository "
                            "that contains openspec/ (or straight to an openspec folder) and try again")

        if not ref:
            for shown, absolute in roots:
                if self._openspec_base(absolute):
                    return shown, absolute, ""

            return "", "", ("none of the configured openspec_roots hold an openspec/changes folder yet: "
                            + ", ".join(shown for shown, _known in roots))

        needle = _slug(ref)
        for shown, absolute in roots:
            if _slug(shown) == needle or _slug(absolute) == needle \
                    or _slug(os.path.basename(absolute)) == needle \
                    or _slug(os.path.basename(os.path.dirname(absolute))) == needle:
                return shown, absolute, ""

        return "", "", ("openspec_roots does not include anything matching "
                             f"'{ref}'. it has: " + ", ".join(shown for shown, _known in roots))

    def _openspec_base(self, absolute):
        """the openspec folder of a configured root, or "" when the root is not an initialized
        project - the `changes/` folder is what actually says an openspec project lives here"""
        if not os.path.isdir(absolute):
            return ""
        if os.path.isdir(os.path.join(absolute, "openspec", "changes")):
            return os.path.join(absolute, "openspec")
        if os.path.isdir(os.path.join(absolute, "changes")):
            return absolute

        return ""

    def _openspec_projects(self):
        """every configured root that turns out to hold an openspec project, as
        [(as configured, absolute, openspec folder)].

        more than one is the whole reason the setting is a list - a frontend repo and a backend
        one, say - so nothing in here may treat the first root as 'the project'.
        """
        projects = []

        for shown, absolute in self._openspec_roots():
            base = self._openspec_base(absolute)
            if base:
                projects.append((shown, absolute, base))

        return projects

    def _openspec_targets(self, root=None):
        """(projects, problem) for one call. with no root named it is every project that is
        configured; naming one narrows the list to that entry, which is how a second repo stops
        being invisible just because another one is listed first"""
        projects = self._openspec_projects()

        if root:
            _shown, absolute, problem = self._openspec_root(root)
            if problem:
                return [], problem

            projects = [entry for entry in projects if entry[1] == absolute]
            if not projects:
                return [], (f"'{root}' is configured in openspec_roots, but there is no "
                            "openspec/changes folder inside it")

        if not projects:
            return [], (self._openspec_ui_state()["problem"]
                        or "none of the configured openspec_roots holds an openspec project")

        return projects, ""

    def _openspec_label(self, project, projects):
        """the project's name for messages and rows: the folder it lives in, which is what a
        person recognises, falling back to the path they configured when two roots share a name"""
        name = os.path.basename(os.path.dirname(project[2])) or os.path.basename(project[2])
        names = [os.path.basename(os.path.dirname(entry[2])) for entry in projects]

        return name if names.count(name) == 1 else project[0]

    def _openspec_find(self, projects, change):
        """every project that has a change matching this name, as [(project, change_id)].

        answered across all of them so a change in the second repo can be imported by name alone,
        and so two repos with a change of the same name are reported instead of guessed about.
        """
        matches = []

        for project in projects:
            ids = self._openspec_change_ids(project[2])
            index, _problem = self._lookup([{"id": entry} for entry in ids], change, "id")
            if index >= 0:
                matches.append((project, ids[index]))

        return matches

    def _openspec_read(self, base, relative):
        """one file inside a root, through the same sandboxed open the skills module uses.
        None covers "not there", which keeps a missing optional artifact out of the way"""
        try:
            descriptor = core.sandbox_open(base, relative, os.O_RDONLY)
        except (OSError, ValueError):
            return None

        try:
            with os.fdopen(descriptor, "r", encoding="utf-8", errors="replace") as handle:
                return handle.read()
        except OSError:
            return None

    def _openspec_entries(self, base, relative=""):
        """names of the entries of a folder inside a root, "" for the root itself"""
        try:
            return sorted(core.sandbox_listdir(base, relative))
        except (OSError, ValueError):
            return []

    def _openspec_is_dir(self, base, relative):
        """whether an entry of a folder inside a root is itself a folder.

        asking the sandbox to list it is the check: a file raises, a folder does not. done this
        way instead of with os.path so the one rule of this feature keeps holding - every path
        into your project goes through the sandboxed helpers.
        """
        try:
            core.sandbox_listdir(base, relative)
        except (OSError, ValueError):
            return False

        return True

    def _openspec_change_ids(self, base):
        """the changes in flight. an archived change is finished work, not backlog, so the
        archive folder is never read - and a plain file sitting in changes/ (a README, an
        IMPLEMENTATION_ORDER.md someone left there) is not a change either.
        """
        return [entry for entry in self._openspec_entries(base, "changes")
                if entry != OPENSPEC_ARCHIVE and not entry.startswith(".")
                and self._openspec_is_dir(base, f"changes/{entry}")]

    def _openspec_change(self, base, change_id):
        """one change folder, parsed: the proposal's intent, its requirements with their
        scenarios, and the tasks.md checklist. design.md is left out on purpose - that is
        implementation detail, and the board tracks what is to be done, not how"""
        folder = f"changes/{change_id}"

        proposal = self._openspec_read(base, f"{folder}/proposal.md")
        tasks = self._openspec_read(base, f"{folder}/tasks.md")
        metadata = self._openspec_read(base, f"{folder}/.openspec.yaml")

        requirements = []
        capabilities = []

        for capability in self._openspec_entries(base, f"{folder}/specs"):
            if not self._openspec_is_dir(base, f"{folder}/specs/{capability}"):
                continue

            spec = self._openspec_read(base, f"{folder}/specs/{capability}/spec.md")
            if spec is None:
                continue

            capabilities.append(capability)
            requirements.extend(_parse_openspec_spec(spec, capability))

        return {
            "id": change_id,
            "folder": f"openspec/{folder}",
            "proposal": _parse_openspec_proposal(proposal) if proposal else "",
            "tasks": _parse_openspec_tasks(tasks) if tasks else [],
            "requirements": requirements,
            "capabilities": capabilities,
            "has_design": self._openspec_read(base, f"{folder}/design.md") is not None,
            # a change with no spec deltas is legitimate for a pure refactor (skip_specs: true)
            "skip_specs": bool(re.search(r"^\s*skip_specs:\s*true", metadata or "", re.MULTILINE)),
        }

    def _openspec_cards(self, change, unit, column_id, as_epic=True):
        """the cards a change describes, before any of them is written.

        'requirements' makes one story per requirement - the testable unit, because its scenarios
        are the acceptance criteria. 'tasks' mirrors the checklist instead, so the board and
        tasks.md say the same thing. every card carries the source it came from, which is what
        makes a second import an update rather than a pile of duplicates.
        """
        label = f"{OPENSPEC_LABEL}/{change['id']}"
        plan = []

        # an epic for a change that has nothing but a .openspec.yaml would be a blank card, so it
        # is filed when there is something on it to say: the proposal's intent, or work
        if as_epic and (change["proposal"] or change["requirements"] or change["tasks"]):
            checked = len([task for task in change["tasks"] if task["done"]])
            summary = [f"Imported from {change['folder']}."]
            if change["capabilities"]:
                summary.append(f"Capabilities: {', '.join(change['capabilities'])}.")
            summary.append(f"{len(change['requirements'])} requirement(s), "
                           f"{checked}/{len(change['tasks'])} tasks checked off.")
            if change["proposal"]:
                summary.append("")
                summary.append(change["proposal"])

            plan.append({
                "source": f"openspec:{change['id']}#change",
                "title": f"OpenSpec change: {change['id']}",
                "description": "\n".join(summary),
                "type": "epic",
                "labels": [label],
                "column": column_id,
                "done": False,
            })

        if unit in ("requirements", "both"):
            for requirement in change["requirements"]:
                capability = _labelify(requirement.get("capability"), 20)
                title, shortened = _shorten(requirement["name"])

                plan.append({
                    "source": (f"openspec:{change['id']}#req:{requirement.get('capability') or 'spec'}"
                               f":{_labelify(requirement['name'], 40)}"),
                    "title": title,
                    "description": (_requirement_markdown(change, requirement)
                                    + (f"\n\nThe requirement is titled '{requirement['name']}' in full."
                                       if shortened else "")),
                    "type": "story",
                    "labels": [label] + ([capability] if capability else [])
                              + [f"os-{requirement.get('kind', 'added')}"],
                    "column": column_id,
                    "done": False,
                    "note": "" if requirement.get("scenarios") else
                            f"'{requirement['name']}' has no scenario, so nothing about it is testable yet",
                })

        if unit in ("tasks", "both"):
            for task in change["tasks"]:
                group = _labelify(task.get("group"), 20)
                number = f"{task['number']} " if task.get("number") else ""
                title, shortened = _shorten(f"{number}{task['title']}")

                plan.append({
                    "source": (f"openspec:{change['id']}#task:"
                               f"{task.get('number') or _labelify(task['title'], 40)}"),
                    "title": title,
                    "description": (f"From {change['folder']}/tasks.md"
                                    + (f", under '{task['group']}'" if task.get("group") else "")
                                    + (f" - already checked off in the file" if task["done"] else "")
                                    # a long task line is cut short in the title, so the card has to
                                    # carry the sentence the board could not show
                                    + (f"\n\n{task['number']} {task['title']}".rstrip()
                                       if shortened else "")),
                    "type": "task",
                    "labels": [label] + ([group] if group else []),
                    "column": column_id,
                    "done": bool(task["done"]),
                })

        # two requirements can share a name across capabilities and two untitled tasks can share
        # a title. sources have to be one per card, or updating them becomes a coin toss
        seen = {}
        for entry in plan:
            count = seen.get(entry["source"], 0)
            seen[entry["source"]] = count + 1
            if count:
                entry["source"] = f"{entry['source']}#{count + 1}"

        return plan

    def _openspec_apply(self, plan, update_done=True):
        """write a plan onto the board. a card whose source is already here gets its text
        refreshed rather than duplicated: the files are the truth about the requirement, while
        the column, priority, points, assignee and title of a card are yours and stay yours. a
        task checked off in tasks.md is moved to a done column, and nothing is ever dragged
        backwards out of one."""
        known = {column["id"]: column for column in self.columns}
        done_column = next((column for column in self.columns if column.get("done")), None)

        added, updated, notes = [], [], []

        for entry in plan:
            existing = next((card for card in self.cards if card.get("source") == entry["source"]), None)

            if existing is not None:
                existing["description"] = entry["description"]
                existing["type"] = entry["type"]
                # labels are merged: the ones the import owns come back, your own triage stays
                existing["labels"] = self._clean_labels(list(dict.fromkeys(
                    (existing.get("labels") or []) + entry["labels"])))
                existing["updated"] = _now()
                updated.append(existing)

                if entry["done"] and update_done and done_column is not None \
                        and not self._column_is_done(known.get(existing.get("column"))):
                    self._place(existing, done_column["id"])

                continue

            column_id = entry["column"]
            if entry["done"] and done_column is not None:
                column_id = done_column["id"]
            elif known.get(entry["column"]) is None and len(self.columns):
                column_id = self.columns[self._default_column_index()]["id"]

            card = self._new_card(
                title=entry["title"],
                column_id=column_id,
                description=entry["description"],
                card_type=entry["type"],
                labels=entry["labels"],
                source=entry["source"],
            )

            self._place(card, column_id)
            self.card_store.append(card)
            added.append(card)

            if entry.get("note"):
                notes.append(entry["note"])

        return added, updated, notes

    @core.module.tool
    async def import_openspec(self, change: str = None, root: str = None, unit: str = None,
                             column: str = None, as_epic: bool = True, update_done: bool = True,
                             dry_run: bool = False, max_cards: int = None):
        """Turns an OpenSpec change into board cards by reading openspec/changes/<change>/: each
        requirement becomes a story with its #### Scenario: lines as acceptance criteria, or each
        tasks.md checkbox when unit is 'tasks'. Reading the files instead of your memory of them is
        what makes the cards reviewable, and re-running it updates the cards it made rather than
        adding duplicates. Nothing is written outside the board, and your project is never touched.

        Args:
            change: the change id (a folder under openspec/changes). Leave it out when only one
                change is in flight; read_openspec lists them
            root: which configured openspec_roots entry to read, when there is more than one
            unit: 'requirements' (one testable story per requirement, the default), 'tasks' (one
                card per tasks.md checkbox) or 'both'
            column: where the cards land (name or id). Defaults to the first column that is not done
            as_epic: also file one epic card holding the change itself, with the proposal's intent
                on it, so a whole batch is recognisable on the board
            update_done: move cards whose task is checked off in tasks.md into a done column
            dry_run: report what would happen and write nothing, so the user can agree first
            max_cards: cap on cards created by this call, defaulting to openspec_max_cards
        """
        self._reload()

        problem = self._openspec_ready()
        if problem:
            return self.result(problem, success=False)

        projects, problem = self._openspec_targets(root)
        if problem:
            return self.result(problem, success=False)

        # no root named means "the project I am working on", which is the first one. the others are
        # reachable by name as well, and a name that matches two of them is refused below
        _shown, _absolute, base = projects[0]

        ids = self._openspec_change_ids(base)
        if not ids:
            return self.result(f"{base} has no changes in flight - openspec/changes is empty, so "
                               "there is nothing to import yet"
                               + (f". your other roots: "
                                  + ", ".join(f"{self._openspec_label(entry, projects)} "
                                              f"({len(self._openspec_change_ids(entry[2]))} change(s))"
                                              for entry in projects[1:])
                                  if len(projects) > 1 else ""), success=False)

        if change:
            matches = self._openspec_find(projects, change)
            if not matches:
                return self.result(f"no openspec change matching '{change}' "
                                   f"(in flight: {', '.join(ids)}"
                                   + (f" in {base}; other roots: "
                                      + ", ".join(f"{self._openspec_label(entry, projects)} has "
                                                  f"{', '.join(self._openspec_change_ids(entry[2])) or 'none'}"
                                                  for entry in projects[1:])
                                      if len(projects) > 1 else "") + ")", success=False)
            if len(matches) > 1:
                return self.result(f"'{change}' is in flight in more than one of your "
                                   f"openspec_roots ({', '.join(self._openspec_label(entry, projects)
                                                                 for entry, _id in matches)}) "
                                   "- say which one with root=", success=False)

            project, change_id = matches[0]
            base = project[2]
            # name the repo the cards came from whenever more than one is configured, including
            # when the caller narrowed it themselves - "which one did I just land?" is answered
            # by the message rather than by scrolling back through the settings
            root_note = (f" (from {self._openspec_label(project, self._openspec_projects())})"
                         if len(self._openspec_projects()) > 1 else "")
        elif len(ids) == 1:
            change_id = ids[0]
            root_note = ""
        else:
            return self.result(f"several changes are in flight in {base}, which one? "
                               f"({', '.join(ids)})"
                               + (f" - there are {sum(len(self._openspec_change_ids(entry[2])) for entry in projects[1:])} "
                                  "more in your other roots, name one with root="
                                  if len(projects) > 1 else ""), success=False)

        unit = _slug(unit) or _slug(self.config.get("openspec_default_unit")) or "requirements"
        if unit not in OPENSPEC_UNITS:
            return self.result(f"unknown unit '{unit}', use one of: {', '.join(OPENSPEC_UNITS)}", success=False)

        if column:
            column_index, problem = self._column(column)
            if column_index < 0:
                return self.result(self._not_found("column", column, problem), success=False)
            target = self.columns[column_index]
        else:
            index = self._default_column_index()
            if index < 0:
                return self.result("the board has no columns, create one with add_column first", success=False)
            target = self.columns[index]

        parsed = self._openspec_change(base, change_id)
        plan = self._openspec_cards(parsed, unit, target["id"], as_epic=bool(as_epic))

        if not plan:
            hint = (" it declares skip_specs, so its work is only in tasks.md - which looks empty "
                    "too, so either the change is still being drafted or it is not an openspec change"
                    if parsed["skip_specs"] else
                    " there is not even a proposal to put on an epic card, so there is nothing here "
                    "a board could hold")
            return self.result(f"openspec/changes/{change_id} has no requirements, no tasks and no "
                               f"proposal -{hint}", success=False)
        limit = int(max_cards if max_cards is not None else (self.config.get("openspec_max_cards") or 0))

        truncated = 0
        if limit and len(plan) > limit:
            truncated = len(plan) - limit
            plan = plan[:limit]

        sources = {card.get("source") for card in self.cards if card.get("source")}
        fresh = len([entry for entry in plan if entry["source"] not in sources])

        if dry_run:
            lines = [f"openspec/changes/{change_id} as {unit} into {target['name']}"
                     f"{root_note} (nothing written yet):", f"  {fresh} new card(s), "
                     f"{len(plan) - fresh} already on the board would be refreshed"]
            for entry in plan[:20]:
                mark = "=" if entry["source"] in sources else "+"
                lines.append(f"  {mark} {entry['type']}: {entry['title']}")
            if len(plan) > 20:
                lines.append(f"  .. and {len(plan) - 20} more")
            if truncated:
                lines.append(f"  {truncated} card(s) were cut off by the max_cards limit")

            return self.result("\n".join(lines))

        added, updated, notes = self._openspec_apply(plan, update_done=bool(update_done))

        if added or updated:
            self._save()
            self.broadcast_board("cards_imported")

        lines = [f"imported openspec/changes/{change_id} ({unit}) into {target['name']}"
                 f"{root_note}: {len(added)} card(s) added, {len(updated)} refreshed"]
        for card in added[:20]:
            lines.append(f"  [{card['id']}] {card['title']}")
        if len(added) > 20:
            lines.append(f"  .. and {len(added) - 20} more")
        if truncated:
            lines.append(f"  {truncated} card(s) were left out by the max_cards limit")
        if not added and updated:
            lines.append("  nothing new: the board already had this change, its text is now current")
        if not parsed["requirements"] and not parsed["tasks"]:
            # a change with only a proposal is a real thing in a real project: somebody created it
            # and has not written its artifacts yet. the epic is worth having, the story is that
            # the stories are not there yet
            lines.append("  note: this change only has a proposal so far, so the epic is all the "
                         "board can hold - its stories appear once it has requirements or tasks")
        lines.extend(f"  note: {note}" for note in notes)
        lines.append(f"  the cards carry the '{OPENSPEC_LABEL}/{change_id}' label, and ticked tasks "
                     "follow tasks.md - never the other way round")

        return self.result("\n".join(lines))

    @core.module.tool
    async def read_openspec(self, change: str = None, root: str = None, show_tasks: bool = False):
        """Reads the OpenSpec changes that are in flight and how they relate to the board: what is
        specified, how much of it is already on the board, and which requirements are not testable
        yet because they have no scenario. Read-only - it answers 'what is still unplanned?'

        Args:
            change: one change id to look at closely (its requirements, which of them are on the
                board, which have no scenario). Leave it out for the list of everything in flight
            root: which configured openspec_roots entry to read, when there is more than one
            show_tasks: also list the tasks.md checklist under that change. Off by default because
                a big change's checklist would bury the requirements; it comes on by itself when
                the change has no requirements at all
        """
        self._reload()

        problem = self._openspec_ready()
        if problem:
            return self.result(problem, success=False)

        projects, problem = self._openspec_targets(root)
        if problem:
            return self.result(problem, success=False)

        _shown, _absolute, base = projects[0]
        ids = self._openspec_change_ids(base)

        on_board = {}
        for card in self.cards:
            change_of = _openspec_change_of(card)
            if change_of:
                on_board[change_of] = on_board.get(change_of, 0) + 1

        if change:
            matches = self._openspec_find(projects, change)
            if not matches:
                return self.result(f"no openspec change matching '{change}' "
                                   f"(in flight: {', '.join(ids)})", success=False)
            if len(matches) > 1:
                return self.result(f"'{change}' is in flight in more than one of your "
                                   f"openspec_roots ({', '.join(self._openspec_label(entry, projects)
                                                                 for entry, _id in matches)}) "
                                   "- say which one with root=", success=False)

            project, _change_id = matches[0]
            base = project[2]
            several = len(self._openspec_projects()) > 1

            parsed = self._openspec_change(base, _change_id)
            sources = {card.get("source"): card["id"] for card in self.cards if card.get("source")}

            lines = [f"openspec/changes/{parsed['id']}"
                     + (f" (in {self._openspec_label(project, self._openspec_projects())})"
                        if several else "")
                     + (" (skip_specs)" if parsed["skip_specs"] else "")
                     + f" - capabilities: {', '.join(parsed['capabilities']) or 'none'}"
                     + (", design.md present" if parsed["has_design"] else "")]

            for requirement in parsed["requirements"]:
                source = (f"openspec:{parsed['id']}#req:{requirement.get('capability') or 'spec'}"
                          f":{_labelify(requirement['name'], 40)}")
                scenarios = len(requirement["scenarios"])
                lines.append(f"  [{sources.get(source, 'not on the board')}] "
                             f"{requirement.get('capability', '?')}/{requirement['name']} "
                             f"({requirement['kind']}, {scenarios} scenario(s)"
                             + (", NOT TESTABLE YET" if not scenarios else "") + ")")

            listed_tasks = show_tasks or not parsed["requirements"]
            if listed_tasks:
                for task in parsed["tasks"]:
                    source = (f"openspec:{parsed['id']}#task:"
                              f"{task.get('number') or _labelify(task['title'], 40)}")
                    lines.append(f"  [{'x' if task['done'] else ' '}] "
                                 f"{task.get('number') or '-'} {task['title']} "
                                 f"-> {sources.get(source, 'not on the board')}")

            if not parsed["requirements"] and not parsed["tasks"]:
                lines.append("  nothing here yet: no requirements, no tasks and no proposal, so "
                             "there is no card to be had from this change")

            # the question this tool gets asked is 'what is still unplanned', so answer it instead
            # of making the model count lines
            planned = len([r for r in parsed["requirements"]
                           if sources.get(f"openspec:{parsed['id']}#req:"
                                          f"{r.get('capability') or 'spec'}:{_labelify(r['name'], 40)}")])
            no_scenario = len([r for r in parsed["requirements"] if not r["scenarios"]])
            lines.append(f"  on this board: {planned}/{len(parsed['requirements'])} requirement(s)"
                         + (f", {len([t for t in parsed['tasks'] if sources.get(
                                f"openspec:{parsed['id']}#task:"
                                f"{t.get('number') or _labelify(t['title'], 40)}")])}"
                               f"/{len(parsed['tasks'])} task(s)" if listed_tasks and parsed["tasks"] else "")
                         + (f", {no_scenario} without a scenario" if no_scenario else "")
                         + (f", {on_board.get(parsed['id'], 0)} card(s) carrying the "
                            f"'{OPENSPEC_LABEL}/{parsed['id']}' label" if on_board.get(parsed['id'])
                            else ", nothing on this board yet"))

            return self.result("\n".join(lines))

        lines = ["openspec changes in flight"
                 + (f" across {len(projects)} roots" if len(projects) > 1 else f" in {base}") + ":"]

        for project in projects:
            if len(projects) > 1:
                lines.append(f"  {self._openspec_label(project, projects)}:")

            for change_id in self._openspec_change_ids(project[2]):
                parsed = self._openspec_change(project[2], change_id)
                checked = len([task for task in parsed["tasks"] if task["done"]])
                untestable = len([requirement for requirement in parsed["requirements"]
                                  if not requirement["scenarios"]])

                lines.append(f"  {'  ' if len(projects) > 1 else ''}{change_id} - "
                             f"{len(parsed['requirements'])} requirement(s), "
                             f"{checked}/{len(parsed['tasks'])} tasks checked off, "
                             f"{on_board.get(change_id, 0)} card(s) on this board"
                             + (f", {untestable} requirement(s) without a scenario"
                                if untestable else ""))

        lines.append("")
        lines.append("import one with import_openspec - it reads these files rather than your "
                     "memory of them, and re-running it refreshes the cards instead of duplicating"
                     + (". with more than one root, name it with root=" if len(projects) > 1 else ""))

        return self.result("\n".join(lines))

    # ------------------------------------------------------------------
    # command
    # ------------------------------------------------------------------

    @core.module.command("board", send_to_ai=False)
    async def cmd_board(self, args: list):
        """Show the project board. Without arguments it shows the whole board, otherwise it
        filters by text. `/board switch <name>` switches to another board, `/board list`
        shows them all."""
        words = [str(arg) for arg in (args or [])]
        command = _slug(words[0]) if words else ""

        if command in ("list", "ls", "boards"):
            return (await self.list_boards())["content"]

        if command in ("switch", "use", "open", "go") and len(words) > 1:
            return (await self.activate_board(" ".join(words[1:])))["content"]

        return (await self.read_board(query=" ".join(words) or None))["content"]

    @core.module.command("boards", send_to_ai=False)
    async def cmd_boards(self, args: list):
        """List every project board with its card counts, and which one is active."""
        return (await self.list_boards())["content"]

    # ------------------------------------------------------------------
    # webui extension api (private methods are skipped by the tool loader)
    # ------------------------------------------------------------------

    def _ui_board(self):
        """everything the board panel needs in one shot, active board first"""
        self._reload()

        done_ids = {column["id"] for column in self.columns if column.get("done")}

        cards = []
        for card in self.cards:
            entry = dict(card)
            entry["overdue"] = card.get("column") not in done_ids and _is_overdue(card)
            cards.append(entry)

        return {
            "active": {
                "id": self.board["id"],
                "name": self.board["name"],
                "description": self.board.get("description", ""),
            } if self.board else None,
            "boards": self._boards_overview(),
            "columns": [dict(column) for column in self.columns],
            "cards": cards,
            "stats": self._stats(),
            # the play buttons of this board, so the panel can render them without a second
            # request. the examples the action editor offers are not here on purpose: they are
            # static text the editor fetches once, from actions/examples
            "actions": self._ui_actions(),
            "options": {
                "types": list(CARD_TYPES),
                "priorities": list(PRIORITIES),
                "placeholders": list(CARD_PLACEHOLDERS),
                "spec_placeholders": list(SPEC_PLACEHOLDERS),
                "openspec_units": list(OPENSPEC_UNITS),
            },
            "settings": {
                "keep_chat_input": bool(self.config.get("keep_chat_input", True)),
                "enable_prompt_actions": bool(self.config.get("enable_prompt_actions", True)),
                "openspec": self._openspec_ui_state(),
            },
        }

    def _openspec_ui_state(self):
        """what the panel may offer for openspec. deliberately no file reading here: opening the
        board should not touch your project, the strip asks for the changes when you open it"""
        roots = self._openspec_roots()
        problem = self._openspec_ready()

        if not problem and not roots:
            # the one state a newcomer hits first, so say what to do about it instead of just
            # saying "not configured" - there is nowhere else in the UI that explains this
            problem = ("no openspec folder is configured yet. set openspec_roots to the repository "
                       "that contains openspec/, or straight to an openspec folder, and reload this "
                       "strip - until then the board has nowhere it is allowed to read from")
        elif not problem and not any(self._openspec_base(absolute) for _shown, absolute in roots):
            problem = ("none of the configured openspec_roots hold an openspec/changes folder yet: "
                       + ", ".join(shown for shown, _absolute in roots))

        return {
            "enabled": bool(self.config.get("enable_openspec", True)),
            "ready": not problem and bool(roots),
            "problem": problem,
            "roots": [shown for shown, _absolute in roots],
            "default_unit": _slug(self.config.get("openspec_default_unit")) or "requirements",
        }

    @webui.route("board")
    async def _route_board(self, body=None, query=None):
        return self._ui_board()

    @webui.route("board/activate", method="POST")
    async def _route_board_activate(self, body=None, query=None):
        """the switcher in the board header. takes {id} and makes that board the one the
        panel and the tools work on"""
        body = body or {}
        return await self.activate_board(body.get("id") or body.get("name"))

    @webui.route("board/create", method="POST")
    async def _route_board_create(self, body=None, query=None):
        body = body or {}
        return await self.create_board(
            name=body.get("name"),
            description=body.get("description") or None,
            columns=body.get("columns") or None,
            like=body.get("like") or None,
            activate=bool(body.get("activate", True)),
        )

    @webui.route("board/update", method="POST")
    async def _route_board_update(self, body=None, query=None):
        body = body or {}
        return await self.edit_board(
            board=body.get("id"),
            name=body.get("name"),
            description=body.get("description"),
        )

    @webui.route("board/delete", method="POST")
    async def _route_board_delete(self, body=None, query=None):
        body = body or {}
        return await self.delete_board(body.get("id"), force=bool(body.get("force")))

    @webui.route("card/create", method="POST")
    async def _route_card_create(self, body=None, query=None):
        body = body or {}
        return await self.add_card(
            title=body.get("title"),
            column=body.get("column") or None,
            description=body.get("description") or None,
            card_type=body.get("type") or "task",
            priority=body.get("priority") or "medium",
            assignee=body.get("assignee") or None,
            labels=body.get("labels") or None,
            points=body.get("points") or 0,
            due=body.get("due") or None,
            blocked=bool(body.get("blocked")),
            to_top=bool(body.get("to_top")),
        )

    @webui.route("card/update", method="POST")
    async def _route_card_update(self, body=None, query=None):
        body = body or {}
        # the modal always sends the whole form, so empty strings mean "cleared" here
        return await self.edit_card(
            card=body.get("id"),
            title=body.get("title"),
            description=body.get("description", ""),
            card_type=body.get("type"),
            priority=body.get("priority"),
            assignee=body.get("assignee", ""),
            labels=body.get("labels", []),
            points=body.get("points", 0),
            due=body.get("due", ""),
            blocked=bool(body.get("blocked")),
        )

    @webui.route("card/move", method="POST")
    async def _route_card_move(self, body=None, query=None):
        """drag & drop lands here. takes {id, column} plus either an `index` (position inside
        the column) or `before_card` (sit above another card, which survives filtering)."""
        body = body or {}

        self._reload()
        index, problem = self._card(body.get("id"))
        if index < 0:
            return self.result(self._not_found("card", body.get("id"), problem), success=False)

        column_index, problem = self._column(body.get("column"))
        if column_index < 0:
            return self.result(self._not_found("column", body.get("column"), problem), success=False)

        entry = self.cards[index]
        target = self.columns[column_index]

        before = body.get("before_card")
        before_id = None
        if before:
            before_index, _problem = self._card(before)
            if before_index >= 0:
                before_id = self.cards[before_index]["id"]

        position = body.get("index")
        if before_id:
            position = self._place(entry, target["id"], before_id=before_id)
        else:
            position = self._place(entry, target["id"], index=None if position is None else int(position))

        self._save()
        self.broadcast_board("card_moved")

        return self.result({"id": entry["id"], "column": target["name"], "position": position,
                            "wip_warning": self._wip_note(target)})

    @webui.route("card/reorder", method="POST")
    async def _route_card_reorder(self, body=None, query=None):
        body = body or {}
        return await self.reorder_column(body.get("column"), body.get("card_ids") or [])

    @webui.route("card/duplicate", method="POST")
    async def _route_card_duplicate(self, body=None, query=None):
        body = body or {}
        return await self.duplicate_card(body.get("id"), body.get("column") or None)

    @webui.route("card/delete", method="POST")
    async def _route_card_delete(self, body=None, query=None):
        body = body or {}

        self._reload()
        return await self.delete_card(body.get("id"))

    @webui.route("comment/add", method="POST")
    async def _route_comment_add(self, body=None, query=None):
        body = body or {}
        return await self.add_comment(body.get("id"), body.get("text"), body.get("author") or "you")

    @webui.route("comment/delete", method="POST")
    async def _route_comment_delete(self, body=None, query=None):
        body = body or {}
        return await self.delete_comment(body.get("id"), body.get("comment"))

    @webui.route("column/create", method="POST")
    async def _route_column_create(self, body=None, query=None):
        body = body or {}
        return await self.add_column(
            name=body.get("name"),
            after=body.get("after") or None,
            wip_limit=body.get("wip_limit") or 0,
            done=bool(body.get("done")),
        )

    @webui.route("column/update", method="POST")
    async def _route_column_update(self, body=None, query=None):
        body = body or {}
        return await self.update_column(
            column=body.get("id"),
            name=body.get("name"),
            wip_limit=body.get("wip_limit"),
            done=body.get("done"),
            position=body.get("position"),
        )

    @webui.route("column/delete", method="POST")
    async def _route_column_delete(self, body=None, query=None):
        body = body or {}
        return await self.delete_column(
            column=body.get("id"),
            cards=body.get("cards") or "move",
            target_column=body.get("target_column") or None,
        )

    # ------------------------------------------------------------------
    # routes: prompt actions (the panel's play buttons)
    # ------------------------------------------------------------------

    @webui.route("actions/list")
    async def _route_actions_list(self, body=None, query=None):
        """the board's prompt actions plus the placeholder cheat-sheet the editor shows"""
        self._reload()

        return {
            "actions": self._ui_actions(),
            "placeholders": list(CARD_PLACEHOLDERS),
            "examples": len(ACTION_EXAMPLES),
            "enabled": bool(self.config.get("enable_prompt_actions", True)),
        }

    @webui.route("actions/examples")
    async def _route_actions_examples(self, body=None, query=None):
        """the templates the action editor offers as a starting point. served from the same
        constant the AI's list_prompt_action_examples reads, so the panel and your AI always
        describe the same set of examples"""
        return {"examples": [dict(example) for example in ACTION_EXAMPLES],
                "placeholders": list(CARD_PLACEHOLDERS)}

    @webui.route("action/save", method="POST")
    async def _route_action_save(self, body=None, query=None):
        """create one, or edit the one whose id came in. the editor posts the whole form"""
        body = body or {}

        if body.get("id"):
            return await self.edit_prompt_action(
                action=body.get("id"),
                name=body.get("name"),
                template=body.get("template"),
                column=body.get("column", ""),
                move_to=body.get("move_to", ""),
                log_as_comment=bool(body.get("log_as_comment")),
                order=body.get("order"),
            )

        return await self.add_prompt_action(
            name=body.get("name"),
            template=body.get("template"),
            column=body.get("column") or None,
            move_to=body.get("move_to") or None,
            log_as_comment=bool(body.get("log_as_comment")),
        )

    @webui.route("action/delete", method="POST")
    async def _route_action_delete(self, body=None, query=None):
        body = body or {}
        return await self.delete_prompt_action(body.get("id"))

    @webui.route("action/render", method="POST")
    async def _route_action_render(self, body=None, query=None):
        """what a play button asks for first: the template with this card's fields in it. the
        panel puts that text into the chat input, which is as far as this goes - a button press
        never sends a message by itself"""
        body = body or {}
        return await self._play_action(body.get("action"), body.get("card") or body.get("id"))

    @webui.route("action/launched", method="POST")
    async def _route_action_launched(self, body=None, query=None):
        """and then the side effects the action was configured with (move the card, log the
        prompt on it), recorded when the button was pressed"""
        body = body or {}
        return await self._action_launched(body.get("action"), body.get("card") or body.get("id"),
                                           prompt=body.get("prompt"))

    # ------------------------------------------------------------------
    # routes: process spec
    # ------------------------------------------------------------------

    async def _render_spec_prompt(self, title=None, spec=None):
        """the spec prompt, with the pasted spec and this board's names in it. rendered here
        rather than in the panel so that what you see is what the module settings say"""
        self._reload()

        spec = str(spec or "").strip()
        if not spec:
            return None, "there is no spec in there yet - paste or type it first"

        return _render(self.config.get("spec_action_prompt") or DEFAULT_SPEC_PROMPT, {
            "title": str(title or "").strip() or "Untitled spec",
            "spec": spec,
            "board": self.board["name"] if self.board else "",
            "backlog": self._backlog_column(),
            "date": _today().isoformat(),
        }), ""

    @webui.route("spec/render", method="POST")
    async def _route_spec_render(self, body=None, query=None):
        """renders the process-spec prompt. the panel calls it both for its preview and to fill
        the chat input, so there is one place that decides what the button actually says"""
        body = body or {}

        prompt, problem = await self._render_spec_prompt(body.get("title"), body.get("spec"))
        if problem:
            return self.result(problem, success=False)

        return {
            "prompt": prompt,
            "board": self.board["name"] if self.board else "",
            "backlog": self._backlog_column(),
            "chars": len(str(body.get("spec") or "").strip()),
        }

    # ------------------------------------------------------------------
    # routes: openspec
    # ------------------------------------------------------------------

    @webui.route("openspec/changes")
    async def _route_openspec_changes(self, body=None, query=None):
        """the changes in flight, for the board's openspec strip. the files are only read when
        the strip is actually opened, and never written"""
        self._reload()

        state = self._openspec_ui_state()
        payload = dict(state)
        payload["changes"] = []
        payload["unit"] = state["default_unit"]

        if not state["ready"]:
            payload["problem"] = state["problem"] or "no openspec folder is configured for this module"
            return payload

        projects, problem = self._openspec_targets()
        if problem:
            return payload | {"problem": problem}

        on_board = {}
        for card in self.cards:
            change_of = _openspec_change_of(card)
            if change_of:
                on_board[change_of] = on_board.get(change_of, 0) + 1

        for shown, absolute, base in projects:
            for change_id in self._openspec_change_ids(base):
                parsed = self._openspec_change(base, change_id)
                checked = len([task for task in parsed["tasks"] if task["done"]])

                payload["changes"].append({
                    "id": change_id,
                    "root": shown,
                    # which repo the row came from, which only matters once more than one is
                    # being read - a single project should not litter its own rows with its name
                    "root_name": self._openspec_label((shown, absolute, base), projects),
                    "capabilities": parsed["capabilities"],
                    "requirements": len(parsed["requirements"]),
                    "untestable": len([requirement for requirement in parsed["requirements"]
                                       if not requirement["scenarios"]]),
                    "tasks": len(parsed["tasks"]),
                    "tasks_done": checked,
                    "on_board": on_board.get(change_id, 0),
                    "skip_specs": parsed["skip_specs"],
                })

        payload["bases"] = [base for _shown, _absolute, base in projects]
        payload["base"] = payload["bases"][0]

        if not payload["changes"]:
            payload["problem"] = ("no changes in flight in "
                                  + ", ".join(payload["bases"]) + " - openspec/changes is empty, "
                                  "so there is nothing to land yet")

        return payload

    @webui.route("openspec/import", method="POST")
    async def _route_openspec_import(self, body=None, query=None):
        """the strip's "land these stories" button, which goes through the same tool your AI
        uses so both paths mean exactly the same thing"""
        body = body or {}
        return await self.import_openspec(
            change=body.get("change") or None,
            root=body.get("root") or None,
            unit=body.get("unit") or None,
            column=body.get("column") or None,
            as_epic=bool(body.get("as_epic", True)),
            update_done=bool(body.get("update_done", True)),
            dry_run=bool(body.get("dry_run")),
        )
