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


class ProjectBoard(core.module.Module):
    """Gives you a kanban / scrum project board: you drag the cards around in the WebUI, your AI runs the board with tools."""

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
            "description": "Columns to create on a fresh board. A column named Done, Closed, Complete or Completed is treated as a done column, which is what progress percentages are counted from. Changing this later does not touch an existing board - rename or delete columns in the WebUI instead, or ask your AI to.",
            "default": ["Backlog", "To Do", "In Progress", "Done"]
        },
        "keep_chat_input": {
            "description": "Keep the chat input bar at the bottom while the board is open, so you can tell your AI to change the board without leaving it. Turn this off for a full-screen board.",
            "default": True,
            "depends": "enable_webui_extension"
        },
        "refresh_interval": {
            "description": "Seconds between automatic board refreshes while the board is open, so changes from your AI or from another browser tab show up. 0 disables polling. Board changes are pushed to the WebUI instantly over the websocket either way, so a high value (or 0) is perfectly fine.",
            "default": 15,
            "depends": "enable_webui_extension"
        }
    }

    async def on_ready(self):
        self._broadcast_tasks = set()
        self.cards = core.storage.StorageList("project_board_cards", "json")
        self.columns = core.storage.StorageList("project_board_columns", "json")

        # a fresh board gets its columns from the settings
        if not self.columns:
            names = self.config.get("default_columns") or []
            for name in names:
                name = str(name).strip()
                if not name:
                    continue
                self.columns.append(self._new_column(name, done=_slug(name) in DONE_COLUMN_NAMES))
            self.columns.save()

    # ------------------------------------------------------------------
    # storage helpers
    # ------------------------------------------------------------------

    def _reload(self):
        """pick up edits made by other processes / a previous session"""
        self.cards.load()
        self.columns.load()
        self._adopt_orphans()

    def _adopt_orphans(self):
        """heal cards pointing at a column that no longer exists (hand-edited storage, etc)"""
        orphans = self._orphan_cards()
        if not orphans or not len(self.columns):
            return

        target = self.columns[0]
        for card in orphans:
            self._place(card, target["id"])

        self.cards.save()
        self.log(self.name, f"moved {len(orphans)} orphan card(s) to {target['name']}")

    def _new_column(self, name, done=False, wip_limit=0):
        return {
            "id": str(ulid.ULID()),
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
                  assignee="", labels=None, points=0, due="", order=0):
        return {
            "id": self._new_id(self.cards),
            "title": str(title).strip(),
            "description": str(description or ""),
            "type": str(card_type or "task").strip().lower(),
            "priority": str(priority or "medium").strip().lower(),
            "column": column_id,
            "order": int(order or 0),
            "assignee": str(assignee or "").strip(),
            "labels": self._clean_labels(labels),
            "points": max(0, int(points or 0)),
            "due": str(due or "").strip(),
            "blocked": False,
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
        return f"no {kind} matching '{ref}' was found (use read_board to list them)"

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
        intro = "You manage a project board with your project-board tools."
        if "webui" in self.manager.channels:
            intro += " The user can see the board in the webui, so your changes show up for them right away."

        header = (
            f"{intro} "
            f"{stats['total']} cards, {stats['done']} done, {stats['blocked']} blocked, {stats['overdue']} overdue, "
            f"{points_open} points still open. Columns: "
            + " -> ".join(column["name"] for column in self.columns) + "."
        )

        if not len(self.cards):
            return header + "\nThe board is empty."

        output = [header, "Open cards (id | column | priority/type | title):", *listed]

        if skipped:
            output.append(f".. and {skipped} more open cards, use read_board to see them all.")

        return "\n".join(output)

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
    # tools: reading
    # ------------------------------------------------------------------

    @core.module.tool
    async def read_board(self, column: str = None, query: str = None, assignee: str = None,
                         priority: str = None, label: str = None, card_type: str = None,
                         include_done: bool = True, include_descriptions: bool = False,
                         max_cards: int = 80):
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
        """
        self._reload()

        if not len(self.columns):
            return self.result("the board has no columns yet", success=False)

        only_column = None
        if column:
            index, problem = self._column(column)
            if index < 0:
                return self.result(self._not_found("column", column, problem), success=False)
            only_column = self.columns[index]

        filters = dict(query=query or "", assignee=assignee or "", priority=priority or "",
                       label=label or "", card_type=card_type or "")

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

        if shown == 0 and hidden == 0:
            return self.result("no cards match those filters", success=False)

        stats = self._stats()
        footer = f"\nboard: {stats['total']} cards, {stats['done']} done ({stats['progress']}%), " \
                 f"{stats['blocked']} blocked, {stats['overdue']} overdue."

        if hidden:
            footer += f" {hidden} cards were cut off by max_cards."

        return self.result("\n\n".join(output) + footer)

    @core.module.tool
    async def board_stats(self):
        """Summarizes the project board: progress, per-column counts, work in progress limit
        breaches, blocked and overdue cards, and a per-person workload. Great for standups."""
        self._reload()

        stats = self._stats()
        if not stats["total"]:
            return self.result("the board is empty")

        lines = [
            f"{stats['total']} cards: {stats['done']} done ({stats['progress']}%), "
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
        self.cards.append(card)
        self.cards.save()
        self.broadcast_board("card_added")

        result = f"added card {card['id']} to {target['name']}: {card['title']}"
        note = self._wip_note(target)
        return self.result(f"{result}\n{note}" if note else result)

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
        self.cards.save()
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
        self.cards.save()
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

        self.cards.save()
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
        self.cards.append(copy)
        self.cards.save()
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

        entry = self.cards.pop(index)
        self.cards.save()
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
        self.cards.save()
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
        self.cards.save()
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

        self.columns.insert(position, self._new_column(name, done=done, wip_limit=wip_limit))
        self.columns.save()
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
            if target != index:
                self.columns.pop(index)
                self.columns.insert(target, entry)
            changed.append(f"position -> {target + 1}")

        if not changed:
            return self.result("nothing to change", success=False)

        self.columns.save()
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
            self.cards[:] = [card for card in self.cards if card.get("column") != entry["id"]]

        self.columns.pop(index)

        self.columns.save()
        self.cards.save()
        self.broadcast_board("column_deleted")

        if not inside:
            return self.result(f"deleted the empty column {entry['name']}")
        if mode == "delete":
            return self.result(f"deleted column {entry['name']} and its {len(inside)} cards")

        return self.result(f"deleted column {entry['name']}, moved {len(inside)} cards to {target['name']}")

    # ------------------------------------------------------------------
    # command
    # ------------------------------------------------------------------

    @core.module.command("board", send_to_ai=False)
    async def cmd_board(self, args: list):
        """Show the project board. Without arguments it shows the whole board, otherwise it filters by text."""
        query = " ".join(str(arg) for arg in (args or [])) or None
        return (await self.read_board(query=query))["content"]

    # ------------------------------------------------------------------
    # webui extension api (private methods are skipped by the tool loader)
    # ------------------------------------------------------------------

    def _ui_board(self):
        """everything the board panel needs in one shot"""
        self._reload()

        done_ids = {column["id"] for column in self.columns if column.get("done")}

        cards = []
        for card in self.cards:
            entry = dict(card)
            entry["overdue"] = card.get("column") not in done_ids and _is_overdue(card)
            cards.append(entry)

        return {
            "columns": [dict(column) for column in self.columns],
            "cards": cards,
            "stats": self._stats(),
            "options": {
                "types": list(CARD_TYPES),
                "priorities": list(PRIORITIES),
            },
            "settings": {
                "keep_chat_input": bool(self.config.get("keep_chat_input", True)),
                "refresh_interval": int(self.config.get("refresh_interval", 15) or 0),
            },
        }

    @webui.route("board")
    async def _route_board(self, body=None, query=None):
        return self._ui_board()

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

        self.cards.save()
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
