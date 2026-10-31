# -- AI-GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-26) status:reviewed harness:openlumara --
# project-board tests for OpenLumara — a kanban / scrum board you drive from the WebUI while your AI drives it with tools
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
"""
user_modules/project-board - the board's whole tool surface, its webui routes and
the prompts derived from it.

integration level: the real module on a FakeManager, real tmp-dir StorageLists.
Webui broadcasts are exercised by the absence of a channel on the fake manager,
which is the path taken when OpenLumara runs on another channel than the webui.

intent under test:
- a fresh board is seeded from the default_columns setting, and a column named
  after a finished state becomes a done column (progress is counted from those).
- cards take short, board-unique ids; tools accept that id, an exact title, or an
  unambiguous piece of it, and refuse to guess when a reference is ambiguous.
- ordering inside a column is dense (0..n-1) after every move, and moving above a
  card keeps the intent of "directly above it".
- done columns, wip limits, due dates and blocked flags are what the listings, the
  stats and the system prompt report; validation errors come back as error envelopes.
- deleting a column moves its cards somewhere sane, or deletes them when asked, and
  the last column on the board cannot be deleted.
"""

import datetime
import json
import pathlib
import re

import pytest

from conftest import FakeManager  # noqa: F401  (kept for debugging in isolation)


def column(board, name):
    return next(c for c in board.columns if c["name"] == name)


def titles(board, name):
    return [card["title"] for card in board._column_cards(column(board, name)["id"])]


async def add(board, title, **kwargs):
    result = await board.add_card(title, **kwargs)
    assert result["status"] == "success", result["content"]
    return board.cards[-1]["id"]


# ---------------------------------------------------------------------------
# board setup
# ---------------------------------------------------------------------------

async def test_fresh_board_uses_the_default_columns(board):
    assert [c["name"] for c in board.columns] == ["Backlog", "To Do", "In Progress", "Done"]
    assert not column(board, "Backlog")["done"]
    assert column(board, "Done")["done"], "a column called Done counts as finished work"


async def test_a_board_without_default_columns_starts_without_any(board, monkeypatch, tmp_path):
    """the webui still works: adding the first column is up to the user or the AI"""
    import core
    import importlib

    empty_data = tmp_path / "empty-data"
    empty_data.mkdir()
    core.config.config["core"]["data_folder"] = str(empty_data)
    core.config.config.save()

    monkeypatch.setattr(board.config, "get", lambda *args, **kwargs: [])

    fresh = importlib.import_module("user_modules.project-board").ProjectBoard(FakeManager())
    fresh.config = board.config
    await fresh.on_ready()

    assert list(fresh.columns) == []
    assert (await fresh.read_board())["status"] == "error"
    assert (await fresh.add_card("nowhere to go"))["status"] == "error"
    assert await fresh.on_system_prompt() is None


async def test_orphaned_cards_are_adopted_by_the_first_column(board):
    card_id = await add(board, "homeless card")

    board.cards[0]["column"] = "01NOTACOLUMN"
    board.card_store.save()
    board._reload()

    assert board._column_cards(board.columns[0]["id"])[0]["id"] == card_id


# ---------------------------------------------------------------------------
# cards: creating and validating
# ---------------------------------------------------------------------------

async def test_add_card_fills_defaults_and_appends_below(board):
    card_id = await add(board, "write the docs")
    card = board.cards[0]

    assert card["id"] == card_id
    assert len(card_id) == 6 and card_id == card_id.upper(), "ids are short and speakable"
    assert card["column"] == column(board, "Backlog")["id"], "default column is the first open one"
    assert card["type"] == "task" and card["priority"] == "medium"
    assert card["order"] == 0 and card["comments"] == [] and card["points"] == 0


async def test_add_card_to_top_inserts_above_the_rest(board):
    await add(board, "second")
    await add(board, "first", to_top=True)

    assert titles(board, "Backlog") == ["first", "second"]


async def test_add_card_resolves_columns_case_insensitively(board):
    await board.add_column("In Review")

    await add(board, "picked", column="IN REVIEW")
    assert titles(board, "In Review") == ["picked"]


async def test_add_card_validates_its_input(board):
    assert (await board.add_card("   "))["status"] == "error"
    assert (await board.add_card("x", column="Nope"))["status"] == "error"
    assert (await board.add_card("x", card_type="feature"))["status"] == "error"
    assert (await board.add_card("x", priority="urgent"))["status"] == "error"
    assert (await board.add_card("x", due="next tuesday"))["status"] == "error"
    assert len(board.cards) == 0


async def test_add_card_normalizes_labels_and_points_and_due(board):
    await add(board, "labeled", labels=["#auth", " auth ", "", "ui"], points=7,
              due="2026-12-01")

    card = board.cards[0]
    assert card["labels"] == ["auth", "ui"]
    assert card["points"] == 7
    assert card["due"] == "2026-12-01"


async def test_card_ids_stay_unique(board):
    ids = set()
    for index in range(40):
        ids.add(await add(board, f"card {index}"))

    assert len(ids) == 40


# ---------------------------------------------------------------------------
# references
# ---------------------------------------------------------------------------

async def test_cards_are_found_by_id_title_or_a_piece_of_the_title(board):
    card_id = await add(board, "Fix the login screen")

    for reference in (card_id, "fix the login screen", "login screen", "FIX"):
        index, problem = board._card(reference)
        assert index == 0, f"{reference!r} should resolve ({problem})"


async def test_ambiguous_references_are_refused_instead_of_guessed(board):
    await add(board, "Fix the login screen")
    await add(board, "Fix the login screen again")

    index, problem = board._card("login screen")
    assert index == -1 and problem == "ambiguous", "a piece of a title shared by two cards is not a guess"

    result = await board.delete_card("login screen")
    assert result["status"] == "error" and "exact id" in result["content"]

    # an exact title always wins, even when another card shares the phrase
    assert (await board.delete_card("Fix the login screen"))["status"] == "success"
    assert [c["title"] for c in board.cards] == ["Fix the login screen again"]


# ---------------------------------------------------------------------------
# cards: editing
# ---------------------------------------------------------------------------

async def test_edit_card_only_touches_what_it_is_given(board):
    card_id = await add(board, "original", priority="low", points=2, assignee="steven")

    result = await board.edit_card(card_id, title="renamed", blocked=True)
    assert result["status"] == "success" and "title" in result["content"] and "blocked" in result["content"]

    card = board.cards[0]
    assert card["title"] == "renamed" and card["blocked"] is True
    assert card["priority"] == "low" and card["points"] == 2 and card["assignee"] == "steven"


async def test_edit_card_clears_fields_with_empty_values(board):
    card_id = await add(board, "busy", description="notes", assignee="steven",
                        labels=["auth"], due="2026-11-01", points=5)

    await board.edit_card(card_id, description="", assignee="", labels=[], due="", points=0)

    card = board.cards[0]
    assert card["description"] == "" and card["assignee"] == "" and card["labels"] == []
    assert card["due"] == "" and card["points"] == 0


async def test_edit_card_needs_something_to_do(board):
    card_id = await add(board, "nothing changed")

    assert (await board.edit_card(card_id))["status"] == "error"
    assert (await board.edit_card("does not exist", title="x"))["status"] == "error"
    assert (await board.edit_card(card_id, priority="nope"))["status"] == "error"


# ---------------------------------------------------------------------------
# moving and ordering
# ---------------------------------------------------------------------------

async def test_move_card_between_columns(board):
    card_id = await add(board, "moving on")

    result = await board.move_card(card_id, "In Progress")
    assert result["status"] == "success" and "position 1" in result["content"]

    assert titles(board, "Backlog") == []
    assert titles(board, "In Progress") == ["moving on"]


async def test_move_card_above_another_card(board):
    await add(board, "one")
    second = await add(board, "two")
    third = await add(board, "three")

    await board.move_card(third, "Backlog", before_card=second)
    assert titles(board, "Backlog") == ["one", "three", "two"]


async def test_moving_keeps_orders_dense(board):
    for name in ("one", "two", "three", "four"):
        await add(board, name)

    await board.move_card(board.cards[1]["id"], "To Do")
    await board.move_card(board.cards[1]["id"], "To Do")

    assert [c["order"] for c in board._column_cards(column(board, "Backlog")["id"])] == [0, 1, 2]
    assert [c["order"] for c in board._column_cards(column(board, "To Do")["id"])] == [0]


async def test_move_card_warns_about_work_in_progress_limits(board):
    await board.add_column("Focus", wip_limit=1)
    first = await add(board, "first")
    second = await add(board, "second")

    await board.move_card(first, "Focus")
    result = await board.move_card(second, "Focus")

    assert "over its wip limit (2/1)" in result["content"]


async def test_reorder_column_orders_the_given_cards_first(board):
    for name in ("one", "two", "three"):
        await add(board, name)

    ids = [card["id"] for card in board._column_cards(column(board, "Backlog")["id"])]
    result = await board.reorder_column("Backlog", [ids[2], ids[0]])

    assert result["status"] == "success"
    assert titles(board, "Backlog") == ["three", "one", "two"], "untouched cards keep their order below"

    foreign = await board.reorder_column("To Do", [ids[0]])
    assert foreign["status"] == "error" and "not in To Do" in foreign["content"]


async def test_duplicate_card_copies_next_to_the_original(board):
    card_id = await add(board, "repeatable", points=3, labels=["ux"], description="why")

    result = await board.duplicate_card(card_id)
    assert result["status"] == "success"

    copies = board._column_cards(column(board, "Backlog")["id"])
    assert [c["title"] for c in copies] == ["repeatable", "repeatable (copy)"]
    assert copies[1]["points"] == 3 and copies[1]["labels"] == ["ux"]
    assert copies[1]["description"] == "why"


async def test_duplicate_card_can_land_in_another_column(board):
    card_id = await add(board, "carry on")

    await board.duplicate_card(card_id, column="In Progress")
    assert titles(board, "In Progress") == ["carry on (copy)"]


# ---------------------------------------------------------------------------
# comments
# ---------------------------------------------------------------------------

async def test_comments_are_attributed_and_removable(board):
    card_id = await add(board, "talk to me")

    assert (await board.add_comment(card_id, "  "))["status"] == "error"

    await board.add_comment(card_id, "blocked on the api", author="ai")
    comment = board.cards[0]["comments"][0]
    assert comment["author"] == "ai" and comment["text"] == "blocked on the api"

    assert (await board.delete_comment(card_id, "blocked on the API"))["status"] == "success"
    assert board.cards[0]["comments"] == []

    await board.add_comment(card_id, "second note")
    assert (await board.delete_comment(card_id, "nothing like it"))["status"] == "error"


async def test_comments_and_description_are_shown_by_the_read_tool(board):
    card_id = await add(board, "documented", description="acceptance criteria")
    await board.add_comment(card_id, "a note")

    listing = (await board.read_board())["content"]
    assert "1 comments" in listing

    detailed = (await board.read_board(include_descriptions=True))["content"]
    assert "acceptance criteria" in detailed


# ---------------------------------------------------------------------------
# columns
# ---------------------------------------------------------------------------

async def test_add_column_places_it_after_another_one(board):
    assert (await board.add_column("In Review", after="In Progress", wip_limit=2))["status"] == "success"
    assert [c["name"] for c in board.columns] == ["Backlog", "To Do", "In Progress", "In Review", "Done"]

    assert (await board.add_column("In Review"))["status"] == "error"
    assert (await board.add_column("Somewhere", after="Nope"))["status"] == "error"
    assert (await board.add_column("   "))["status"] == "error"


async def test_update_column_renames_moves_and_sets_flags(board):
    await add(board, "waiting")

    assert (await board.update_column("To Do", name="Ready"))["status"] == "success"
    assert (await board.update_column("Ready", name="Backlog"))["status"] == "error", "names stay unique"
    assert (await board.update_column("Ready", position=0))["status"] == "success"
    assert [c["name"] for c in board.columns][:2] == ["Ready", "Backlog"]
    assert (await board.update_column("Ready"))["status"] == "error", "nothing to change"

    await board.update_column("Ready", wip_limit=1, done=True)
    assert column(board, "Ready")["wip_limit"] == 1 and column(board, "Ready")["done"] is True


async def test_delete_column_moves_or_deletes_its_cards(board):
    await add(board, "doomed", column="To Do")
    await add(board, "survivor", column="To Do")

    await board.delete_column("To Do", cards="move")
    assert titles(board, "Backlog") == ["doomed", "survivor"], "cards go to the first remaining open column"

    await add(board, "gone", column="Backlog")
    await board.delete_column("Backlog", cards="delete")
    assert [c["title"] for c in board.cards] == []


async def test_delete_column_target_can_be_chosen(board):
    await add(board, "traveller")

    await board.delete_column("Backlog", target_column="In Progress")
    assert titles(board, "In Progress") == ["traveller"]


async def test_the_last_column_cannot_be_deleted(board):
    for _ in range(len(board.columns) - 1):
        await board.delete_column(board.columns[-1]["name"])

    assert len(board.columns) == 1
    assert (await board.delete_column(board.columns[0]["name"]))["status"] == "error"


# ---------------------------------------------------------------------------
# listings, stats and prompts
# ---------------------------------------------------------------------------

async def seed(board):
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()

    await add(board, "urgent thing", priority="critical", due=yesterday, assignee="steven",
              labels=["api"], points=3)
    await add(board, "blocked thing", card_type="bug", blocked=True, column="To Do")
    await add(board, "quiet thing", priority="low", due=tomorrow, column="In Progress")
    await add(board, "finished thing", column="Done", points=5)

    return yesterday, tomorrow


async def test_read_board_groups_by_column_and_can_leave_done_out(board):
    await seed(board)

    listing = (await board.read_board())["content"]
    for name in ("Backlog", "To Do", "In Progress", "Done"):
        assert name in listing

    open_only = (await board.read_board(include_done=False))["content"]
    assert "finished thing" not in open_only
    assert "urgent thing" in open_only


async def test_read_board_filters(board):
    await seed(board)

    assert "blocked thing" in (await board.read_board(card_type="bug"))["content"]
    assert "urgent thing" in (await board.read_board(assignee="steven"))["content"]
    assert "urgent thing" in (await board.read_board(label="api"))["content"]
    assert "urgent thing" in (await board.read_board(priority="critical"))["content"]
    assert "quiet thing" in (await board.read_board(query="quiet"))["content"]

    assert (await board.read_board(column="To Do", query="urgent"))["status"] == "error"
    assert (await board.read_board(column="Nope"))["status"] == "error"


async def test_read_board_cuts_off_long_boards_and_says_so(board):
    for index in range(6):
        await add(board, f"card {index}")

    listing = (await board.read_board(max_cards=2))["content"]
    shown = [line for line in listing.splitlines() if line.startswith("  ") and "[medium/task]" in line]

    assert len(shown) == 2
    assert "cards were cut off by max_cards" in listing


async def test_board_stats_reports_progress_and_workload(board):
    await seed(board)

    stats = board._stats()
    assert stats["total"] == 4 and stats["done"] == 1 and stats["progress"] == 25
    assert stats["blocked"] == 1 and stats["overdue"] == 1
    assert stats["unassigned"] == 2, "cards in done columns are not counted as waiting work"
    assert stats["points_total"] == 8 and stats["points_done"] == 5

    summary = (await board.board_stats())["content"]
    assert "steven (1 cards)" in summary
    assert "#api (1)" in summary
    assert "OVER LIMIT" not in summary


async def test_board_stats_on_an_empty_board(board):
    assert (await board.board_stats())["content"] == "General is empty"


async def test_overdue_only_counts_unfinished_work(board):
    yesterday = (datetime.date.today() - datetime.timedelta(days=2)).isoformat()

    await add(board, "late and done", column="Done", due=yesterday)
    assert board._stats()["overdue"] == 0

    await add(board, "late", due=yesterday)
    assert board._stats()["overdue"] == 1


async def test_system_prompt_lists_open_cards_and_respects_the_cap(board, monkeypatch):
    await seed(board)

    prompt = await board.on_system_prompt()
    assert "urgent thing" in prompt and "quiet thing" in prompt
    assert "finished thing" not in prompt, "done work is left out of the prompt"
    assert "OVERDUE" in prompt
    assert "Backlog -> To Do -> In Progress -> Done" in prompt

    real_get = board.config.get
    monkeypatch.setattr(board.config, "get",
                        lambda *args, **kwargs: 1 if args and args[0] == "max_cards_in_prompt"
                        else real_get(*args, **kwargs))

    capped = await board.on_system_prompt()
    assert capped.count("\n[") == 1, "one card listed"
    assert "more open cards" in capped


async def test_system_prompt_can_be_switched_off(board, monkeypatch):
    await seed(board)

    monkeypatch.setattr(board.config, "get", lambda *args, **kwargs: False)
    assert await board.on_system_prompt() is None


async def test_system_prompt_mentions_the_webui_only_when_it_runs(board):
    await seed(board)

    assert "webui" not in await board.on_system_prompt()

    board.manager.channels["webui"] = object()
    assert "webui" in await board.on_system_prompt()


# ---------------------------------------------------------------------------
# command
# ---------------------------------------------------------------------------

async def test_board_command_renders_the_board_or_a_clear_message(board):
    empty = await board.cmd_board([])
    assert "Backlog" in empty, "an empty board still shows the columns it has"
    assert "nothing on this board yet" in empty

    await add(board, "findable card")

    rendered = await board.cmd_board(["findable"])
    assert "findable card" in rendered

    assert "no cards match" in await board.cmd_board(["nothing matches this"])


# ---------------------------------------------------------------------------
# webui routes
# ---------------------------------------------------------------------------

async def test_board_route_returns_everything_the_panel_needs(board):
    await seed(board)

    payload = board._ui_board()
    assert [c["name"] for c in payload["columns"]] == ["Backlog", "To Do", "In Progress", "Done"]
    assert len(payload["cards"]) == 4
    assert payload["stats"]["total"] == 4
    assert payload["options"]["priorities"][0] == "critical"
    assert set(payload["settings"]) == {"keep_chat_input", "enable_prompt_actions", "openspec"}
    assert payload["actions"] == [], "a board without play buttons says so rather than guessing"

    overdue = {card["id"]: card["overdue"] for card in payload["cards"]}
    assert overdue[board.cards[0]["id"]] is True, "the panel gets overdue precomputed"


def test_the_panel_asset_keeps_itself_current():
    """the refresh behaviour lives in the shipped assets rather than in the module, so it is
    locked in here: reload on open, an optional timer you can switch off and retime from the
    status bar, that switch remembered per browser, and no polling once the panel is closed"""
    module_dir = pathlib.Path(__file__).resolve().parent.parent
    script = (module_dir / "webui" / "assets" / "js" / "project_board.js").read_text()
    panel = (module_dir / "webui" / "templates" / "chat" / "index.html").read_text()
    styles = (module_dir / "webui" / "assets" / "css" / "project_board.css").read_text()

    assert "await this.refresh(true);" in script, "opening the board reloads it"
    assert "if (!this.open || !this.autoRefresh) return;" in script, "the timer honours the switch"
    assert "const PB_REFRESH_SECONDS = 5;" in script, "five seconds is where it starts out"
    assert 'localStorage.setItem("pb.autorefresh"' in script, "the switch is remembered"
    assert 'localStorage.setItem("pb.refresh-seconds"' in script, "and so is the interval"

    # the switch and its seconds field sit in the status bar at the bottom, and the field
    # is disabled while auto-refresh is unticked
    assert 'class="pb-statusbar"' in panel
    assert 'class="pb-auto"' in panel and 'x-model="autoRefresh"' in panel
    assert 'x-model="refreshSecondsText"' in panel and ':disabled="!autoRefresh"' in panel
    assert panel.index('class="pb-statusbar"') < panel.index('class="pb-auto"'), \
        "the switch belongs in the status bar, not in the header"
    assert ".pb-seconds:disabled" in styles, "and disabled is visible as such"

    # left to right: the switch, its interval, and only then when the board was last updated
    order = [panel.index(marker) for marker in ('class="pb-auto"', 'class="pb-seconds"',
                                                'class="pb-auto-unit"', 'class="pb-refreshed"')]
    assert order == sorted(order), "checkbox, seconds, then the last-updated note"


def test_the_panel_hands_the_chat_scroll_position_back():
    """opening the board takes #messages out of the layout, and a container that is out of
    the layout has no scroll position left to come back to, so the panel remembers where the
    chat was scrolled to and puts it back when the board is closed"""
    module_dir = pathlib.Path(__file__).resolve().parent.parent
    script = (module_dir / "webui" / "assets" / "js" / "project_board.js").read_text()

    show = script[script.index("async show() {"):script.index("hide() {")]
    hide = script[script.index("    hide() {"):script.index("applyBodyClass() {")]

    assert "this.captureChatScroll();" in show, "opening remembers where the chat was"
    assert show.index("captureChatScroll()") < show.index("applyBodyClass()"), \
        "and it reads the position while the chat is still laid out, not after"
    assert "this.restoreChatScroll();" in hide, "closing gives it back"

    # anchored on the turn at the top of the view rather than on a bare pixel offset, since
    # turns are lazily mounted and the offsets drift as they come back in
    assert '[data-turn-index]' in script
    assert "ui.updateMounts()" in script, "the lazy mounts are nudged along while it settles"
    assert "selectedChat" in script, "a chat switched underneath the board is left alone"
    assert "{ bottom: true }" in script, "a chat with nothing to hand back goes to its newest"


async def test_card_routes_roundtrip(board):
    created = await board._route_card_create(body={"title": "ui card", "labels": "a, b", "points": 3})
    assert created["status"] == "success"
    card_id = board.cards[0]["id"]

    updated = await board._route_card_update(body={
        "id": card_id, "title": "ui card renamed", "description": "", "type": "bug",
        "priority": "high", "assignee": "rose", "labels": [], "points": 0, "due": "",
        "blocked": True,
    })
    assert updated["status"] == "success"
    assert board.cards[0]["title"] == "ui card renamed" and board.cards[0]["type"] == "bug"
    assert board.cards[0]["assignee"] == "rose" and board.cards[0]["blocked"] is True
    assert board.cards[0]["labels"] == []

    moved = await board._route_card_move(body={"id": card_id, "column": "In Progress", "index": 0})
    assert moved["status"] == "success" and moved["content"]["column"] == "In Progress"

    await board._route_card_create(body={"title": "second", "column": "In Progress"})
    second = next(card for card in board.cards if card["title"] == "second")

    moved = await board._route_card_move(body={"id": card_id, "column": "In Progress",
                                               "before_card": second["id"]})
    assert [c["title"] for c in board._column_cards(column(board, "In Progress")["id"])] == [
        "ui card renamed", "second"]

    commented = await board._route_comment_add(body={"id": card_id, "text": "ui note"})
    assert commented["status"] == "success" and board.cards[0]["comments"][0]["author"] == "you"

    removed = await board._route_comment_delete(body={"id": card_id, "comment": "ui note"})
    assert removed["status"] == "success"

    deleted = await board._route_card_delete(body={"id": card_id})
    assert deleted["status"] == "success" and len(board.cards) == 1


async def test_moves_through_the_route_keep_the_column_ordered(board):
    for name in ("one", "two", "three"):
        await add(board, name, column="In Progress")

    third = next(card for card in board.cards if card["title"] == "three")
    await board._route_card_move(body={"id": third["id"], "column": "In Progress", "index": 0})

    inside = board._column_cards(column(board, "In Progress")["id"])
    assert [card["title"] for card in inside] == ["three", "one", "two"]
    assert [card["order"] for card in inside] == [0, 1, 2]



async def test_routes_report_problems_as_errors(board):
    assert (await board._route_card_move(body={"id": "NOPE", "column": "Backlog"}))["status"] == "error"
    assert (await board._route_card_move(body={"id": None, "column": "Nope"}))["status"] == "error"
    assert (await board._route_card_create(body={}))["status"] == "error"
    assert (await board._route_column_update(body={"id": "Nope"}))["status"] == "error"


async def test_column_routes(board):
    await board._route_column_create(body={"name": "In Review", "after": "In Progress", "wip_limit": 3})
    assert [c["name"] for c in board.columns][-2:] == ["In Review", "Done"]

    review = column(board, "In Review")
    assert review["wip_limit"] == 3

    await board._route_column_update(body={"id": review["id"], "done": True, "wip_limit": 0})
    assert column(board, "In Review")["done"] is True and column(board, "In Review")["wip_limit"] == 0

    await board._route_column_update(body={"id": review["id"], "position": 0})
    assert board.columns[0]["name"] == "In Review"

    await add(board, "in the way", column="In Review")
    await board._route_column_delete(body={"id": review["id"], "cards": "move"})
    assert "In Review" not in [c["name"] for c in board.columns]
    assert titles(board, "Backlog") == ["in the way"]


# ---------------------------------------------------------------------------
# boards: one per project, one of them active
# ---------------------------------------------------------------------------

def test_a_fresh_install_starts_with_one_active_board(board):
    assert len(board.boards) == 1
    assert board.board is board.boards[0]
    assert board.board["name"] == "General" and board.board["active"] is True
    assert [column_entry["name"] for column_entry in board.columns] == \
        ["Backlog", "To Do", "In Progress", "Done"]


def test_the_default_board_name_setting_names_the_first_board(make_board):
    assert make_board(default_board_name="Kitchen reno").board["name"] == "Kitchen reno"


def test_board_less_storage_from_an_older_install_becomes_the_first_board(make_board, isolated_paths):
    (isolated_paths / "project_board_columns.json").write_text(json.dumps([
        {"id": "01OLDCOL1", "name": "Up first", "done": False, "wip_limit": 0, "created": "2026-01-01T10:00:00"},
        {"id": "01OLDCOL2", "name": "Done", "done": True, "wip_limit": 0, "created": "2026-01-01T10:00:01"},
    ]))
    (isolated_paths / "project_board_cards.json").write_text(json.dumps([
        {"id": "OLDARD", "title": "carried over", "column": "01OLDCOL2", "order": 0,
         "type": "task", "priority": "medium", "points": 3},
    ]))

    board = make_board()

    assert len(board.boards) == 1 and board.board["name"] == "General"
    assert [column_entry["name"] for column_entry in board.columns] == ["Up first", "Done"], \
        "the migrated board keeps its own layout instead of being handed the default one"
    assert board.cards[0]["title"] == "carried over"
    assert board.cards[0]["board"] == board.board["id"]
    assert board._stats()["done"] == 1 and board._stats()["progress"] == 100


async def test_new_boards_are_their_own_room(board):
    await add(board, "on general")

    await board.create_board("Website redesign")
    assert board.board["name"] == "Website redesign", "creating a board switches to it"
    assert [c["title"] for c in board.cards] == []

    await add(board, "on the other one")
    assert titles(board, "Backlog") == ["on the other one"]

    await board.activate_board("General")
    assert titles(board, "Backlog") == ["on general"]


async def test_columns_and_wip_limits_belong_to_a_board(board):
    await board.add_column("In Review", after="In Progress", wip_limit=2)
    await board.create_board("Second project")

    assert [column_entry["name"] for column_entry in board.columns] == ["Backlog", "To Do", "In Progress", "Done"]

    # the same column name again, on another board, which is perfectly fine
    await board.add_column("In Review", wip_limit=5)
    assert column(board, "In Review")["wip_limit"] == 5

    await board.activate_board("Second project")
    assert column(board, "In Review")["wip_limit"] == 5

    await board.activate_board("General")
    assert column(board, "In Review")["wip_limit"] == 2
    assert [column_entry["name"] for column_entry in board.columns] == \
        ["Backlog", "To Do", "In Progress", "In Review", "Done"]


async def test_create_board_can_stay_quiet_or_copy_another_layout(board):
    await board.add_column("In Review", after="In Progress")

    await board.create_board("Not yet", activate=False)
    assert board.board["name"] == "General"

    await board.create_board("Same stages", like="General")
    assert [column_entry["name"] for column_entry in board.columns] == \
        ["Backlog", "To Do", "In Progress", "In Review", "Done"]

    await board.create_board("Minimal", columns=["Now", "Later"])
    assert [column_entry["name"] for column_entry in board.columns] == ["Now", "Later"]


async def test_board_names_are_yours_to_keep(board):
    await board.create_board("Website redesign")

    duplicate = await board.create_board("website Redesign")
    assert duplicate["status"] == "error" and "already a board" in duplicate["content"]

    renamed = await board.edit_board("Website redesign", name="Marketing site",
                                     description="the thing with the funnel")
    assert renamed["status"] == "success"
    assert board.board["name"] == "Marketing site"
    assert board.board["description"] == "the thing with the funnel"

    clash = await board.edit_board("Marketing site", name="General")
    assert clash["status"] == "error"

    assert (await board.edit_board("General"))["status"] == "error", "nothing to change"


async def test_activating_a_board_accepts_id_name_or_a_piece_of_it(board):
    await board.create_board("Website redesign")
    target = board.board["id"]

    await board.activate_board("General")
    for reference in (target, "Website redesign", "redesign"):
        await board.activate_board("General")
        result = await board.activate_board(reference)
        assert result["status"] == "success", result["content"]
        assert board.board["id"] == target

    already = await board.activate_board("Website redesign")
    assert "already the active board" in already["content"]

    assert (await board.activate_board("nope"))["status"] == "error"
    assert (await board.activate_board("nope"))["content"].endswith("use list_boards to list them)")


async def test_two_boards_with_the_same_word_switch_without_guessing(board):
    await board.create_board("Website redesign")
    await board.activate_board("General")
    await board.create_board("Website migration")

    ambiguous = await board.activate_board("Website")
    assert ambiguous["status"] == "error" and "several boards match" in ambiguous["content"]

    assert (await board.activate_board("Website redesign"))["status"] == "success"


async def test_you_can_look_at_another_board_without_moving_the_pen(board):
    await add(board, "on general")
    await board.create_board("Other project")
    await add(board, "on the other one")

    await board.activate_board("General")

    listing = await board.read_board(board="Other project")
    assert "on the other one" in listing["content"]
    assert "looked at, not active" in listing["content"]

    stats = await board.board_stats(board="Other project")
    assert stats["content"].startswith("Other project:")

    # writing after a look still writes to the board you are actually on
    await board.add_card("still on general")
    assert titles(board, "Backlog") == ["on general", "still on general"]

    assert (await board.read_board(board="nope"))["status"] == "error"


async def test_list_boards_shows_the_boards_with_their_counts(board):
    await add(board, "one", points=3)
    await add(board, "two", column="Done")
    await board.create_board("Second")
    await add(board, "three", column="In Progress", points=5)
    await board.activate_board("General")

    listing = (await board.list_boards())["content"]
    assert "[ACTIVE]" in listing
    assert "General - 2 cards (1 done), 3 points open, 4 columns [ACTIVE]" in listing
    assert "Second - 1 cards (0 done), 5 points open, 4 columns" in listing
    assert listing.count("\n  ") == 2


async def test_deleting_a_board_takes_its_columns_and_cards_with_it(board):
    await add(board, "keep me")
    await board.create_board("Doomed")
    doomed_id = board.board["id"]
    await add(board, "bye")

    refused = await board.delete_board("Doomed")
    assert refused["status"] == "error" and "cards would be lost" in refused["content"]
    assert len(board.boards) == 2

    deleted = await board.delete_board(doomed_id, force=True)
    assert deleted["status"] == "success"

    assert [b["name"] for b in board.boards] == ["General"]
    assert board.board["name"] == "General" and board.board["active"] is True
    assert titles(board, "Backlog") == ["keep me"]
    assert not [column_entry for column_entry in board.column_store if column_entry["board"] == doomed_id]
    assert not [card for card in board.card_store if card["board"] == doomed_id]


async def test_the_only_board_left_cannot_be_deleted(board):
    result = await board.delete_board("General", force=True)
    assert result["status"] == "error" and "only board" in result["content"]


async def test_items_pointing_at_a_board_that_is_gone_get_adopted(board):
    await add(board, "orphan")

    entry = next(card for card in board.card_store if card["id"] == board.cards[-1]["id"])
    entry["board"] = "0GONE"
    board.card_store.save()

    board._reload()

    assert board.cards[-1]["title"] == "orphan"
    assert board.cards[-1]["board"] == board.boards[0]["id"]


async def test_the_prompt_names_the_active_board_and_points_at_the_others(board):
    await add(board, "on general")
    await board.create_board("Website redesign")
    await add(board, "on the other one")
    await board.activate_board("General")

    prompt = await board.on_system_prompt()

    assert "'General' project board" in prompt
    assert "Website redesign" in prompt and "activate_board" in prompt
    assert "on general" in prompt
    assert "on the other one" not in prompt, "another board's cards never leak into the prompt"


async def test_the_board_command_can_list_and_switch_boards(board):
    await board.create_board("Website redesign")
    await board.activate_board("General")

    assert "Website redesign" in (await board.cmd_board(["list"]))
    assert "General is already the active board" in (await board.cmd_board(["switch", "General"]))

    switched = await board.cmd_board(["switch", "Website", "redesign"])
    assert "active board is now Website redesign" in switched
    assert board.board["name"] == "Website redesign"

    assert "Website redesign" in (await board.cmd_boards([]))
    assert "Backlog" in (await board.cmd_board([]))


async def test_the_ui_payload_offers_the_board_switcher(board):
    await add(board, "on general")
    await board.create_board("Second")
    await add(board, "one", column="In Progress")
    await board.activate_board("General")

    payload = board._ui_board()

    assert payload["active"]["name"] == "General"
    assert [entry["name"] for entry in payload["boards"]] == ["General", "Second"]
    assert payload["boards"][0]["active"] is True and payload["boards"][0]["cards"] == 1
    assert payload["boards"][1]["active"] is False and payload["boards"][1]["cards"] == 1
    assert payload["boards"][1]["points"] == 0
    assert [card["title"] for card in payload["cards"]] == ["on general"], "only the active board's cards"


async def test_the_board_routes_roundtrip(board):
    created = await board._route_board_create(body={"name": "Second", "columns": ["Now", "Later"]})
    assert created["status"] == "success"
    assert [column_entry["name"] for column_entry in board.columns] == ["Now", "Later"]

    second = board.board["id"]

    await board.activate_board("General")
    activated = await board._route_board_activate(body={"id": second})
    assert activated["status"] == "success" and board.board["id"] == second

    updated = await board._route_board_update(body={"id": second, "description": "temporary"})
    assert updated["status"] == "success"
    assert next(b for b in board.boards if b["id"] == second)["description"] == "temporary"

    await board._route_card_create(body={"title": "on the second board", "column": "Now"})

    refused = await board._route_board_delete(body={"id": second})
    assert refused["status"] == "error", "a board with cards needs force"

    # the last board standing is protected, too
    await board._route_board_delete(body={"id": second, "force": True})
    assert (await board._route_board_delete(body={"id": board.boards[0]["id"], "force": True}))["status"] == "error"

    assert (await board._route_board_activate(body={"id": "NOPE"}))["status"] == "error"
    assert (await board._route_board_create(body={}))["status"] == "error"


# ---------------------------------------------------------------------------
# prompt actions: the user's own templates, behind a play button
# ---------------------------------------------------------------------------

async def action(board, name="Implement this task", template="Work on {id}: {title}", **kwargs):
    result = await board.add_prompt_action(name, template, **kwargs)
    assert result["status"] == "success", result["content"]

    return board.actions[-1]["id"]


async def test_a_new_board_has_no_play_buttons(board):
    assert board._ui_board()["actions"] == []

    result = await board.list_prompt_actions()
    assert "no prompt actions yet" in result["content"]


async def test_a_prompt_action_is_named_listed_and_deletable(board):
    await add(board, "Add the toggle")
    identifier = await action(board, name="Implement this task",
                              template="Work on {title} ({id}) in {column}.")

    listed = await board.list_prompt_actions()
    assert "Implement this task" in listed["content"]
    assert "Work on {title}" in listed["content"], "the listing shows what the button will say"

    deleted = await board.delete_prompt_action(identifier)
    assert deleted["status"] == "success", deleted["content"]
    assert board.actions == []


async def test_prompt_action_names_are_unique_per_board(board):
    first = await action(board, name="Fix it")

    again = await board.add_prompt_action("fix it", "template")
    assert again["status"] == "error"
    assert "already has a prompt action" in again["content"]

    assert (await board.edit_prompt_action(first, name="Fix it properly"))["status"] == "success"


async def test_a_prompt_action_needs_both_halves(board):
    assert (await board.add_prompt_action("", "text"))["status"] == "error"
    assert (await board.add_prompt_action("Name", "  "))["status"] == "error"


async def test_an_action_can_be_limited_to_one_column(board):
    identifier = await action(board, name="Review this", column="In Progress")

    entry = next(item for item in board.actions if item["id"] == identifier)
    assert entry["column"] == column(board, "In Progress")["id"]

    payload = board._ui_board()
    assert payload["actions"][0]["column_name"] == "In Progress", "the panel gets names, not ids"


async def test_a_column_that_is_not_there_is_refused_rather_than_guessed(board):
    assert "no column matching" in (await board.add_prompt_action("x", "y", column="Icebox"))["content"]
    identifier = await action(board)
    assert (await board.edit_prompt_action(identifier, move_to="Icebox"))["status"] == "error"


async def test_actions_belong_to_their_board(board):
    await action(board, name="Only here")

    other = await board.create_board("Second project")
    assert other["status"] == "success", other["content"]

    assert board._actions_of(board.board) == [], "a second project starts with its own buttons"

    await board.activate_board("General")
    assert [item["name"] for item in board._actions_of(board.board)] == ["Only here"]


async def test_deleting_a_board_takes_its_actions_with_it(board):
    await action(board)
    await board.create_board("Keeper")
    await board.delete_board("General", force=True)

    assert board.actions == []


async def test_deleting_a_column_unscopes_the_actions_that_used_it(board):
    identifier = await action(board, name="Review this", column="In Progress",
                              move_to="In Progress")

    await board.delete_column("In Progress")

    entry = next(item for item in board.actions if item["id"] == identifier)
    assert entry["column"] == "", "an action whose column is gone works board-wide again"
    assert entry["move_to"] == ""


async def test_actions_pointing_at_things_that_are_gone_are_repaired(board, monkeypatch):
    identifier = await action(board, name="Ghost")

    for entry in board.actions:
        entry["board"] = "nope"
        entry["column"] = "no-such-column"
    board.actions.save()

    board._reload()

    entry = next(item for item in board.actions if item["id"] == identifier)
    assert entry["board"] == board.boards[0]["id"]
    assert entry["column"] == ""


async def test_the_order_argument_swaps_two_buttons(board):
    first = await action(board, name="First")
    second = await action(board, name="Second")
    third = await action(board, name="Third")

    assert [item["id"] for item in board._actions_of(board.board)] == [first, second, third]

    await board.edit_prompt_action(third, order=0)

    assert [item["name"] for item in board._actions_of(board.board)] == ["Third", "Second", "First"]


# ---------------------------------------------------------------------------
# rendering a prompt template
# ---------------------------------------------------------------------------

def card_values(board, title="Add the toggle", **kwargs):
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(board.add_card(title, **kwargs))
    finally:
        loop.close()

    return board._card_values(board.cards[-1])


async def test_a_template_gets_the_card_in_front_of_it(board):
    await board.add_card("Add the toggle", column="In Progress", description="with icons",
                         card_type="story", priority="high", assignee="steven",
                         labels=["ui", "settings"], points=3, due="2026-12-31")
    await board.add_comment(board.cards[0]["id"], "start with the css")

    rendered = module_render(board, "{id}|{title}|{column}|{board}|{type}|{priority}|{assignee}|"
                                    "{labels}|{points}|{due}|{comments}|{date}")
    card_id = board.cards[0]["id"]

    assert rendered.startswith(f"{card_id}|Add the toggle|In Progress|General|story|high|steven")
    assert "#ui #settings" in rendered
    assert "3|2026-12-31" in rendered
    assert "- ai: start with the css" in rendered
    assert datetime.date.today().isoformat() in rendered


def pb():
    """the module object, for the tests that lock its shipped constants and pure parsers"""
    import importlib

    return importlib.import_module("user_modules.project-board")


def module_render(board, template):
    """renders a template against a card through the same helper the routes use"""
    return pb()._render(template, board._card_values(board.cards[-1]))


async def test_cards_without_the_optional_bits_render_cleanly(board):
    await board.add_card("Bare card")

    rendered = module_render(board, "[{description}] [{assignee}] [{points}] [{due}] [{change}]")
    assert rendered == "[] [] [] [] []"


async def test_braces_that_are_not_placeholders_survive(board):
    """templates are prose: someone pasting json or a f-string into one must get it back"""
    await board.add_card("Bare card")

    rendered = module_render(board, 'config = { "keep": {nested} }\n{{python}} {id}')

    assert '{ "keep": {nested} }' in rendered
    assert "{{python}}" in rendered
    assert board.cards[0]["id"] in rendered


async def test_every_shipped_example_renders_against_a_real_card(board):
    module = pb()
    await board.add_card("Estimate the scoring rewrite", description="one line", column="Backlog")

    assert len(module.ACTION_EXAMPLES) >= 12, "the editor should never start you from a blank page"

    names = [example["name"] for example in module.ACTION_EXAMPLES]
    assert len(names) == len(set(names)), "example names have to be pickable one by one"

    for example in module.ACTION_EXAMPLES:
        assert example["blurb"] and example["template"].strip(), example["name"]

        rendered = module._render(example["template"], board._card_values(board.cards[-1]))

        for placeholder in module.CARD_PLACEHOLDERS:
            assert "{" + placeholder + "}" not in rendered, \
                f"{example['name']} promises {placeholder} but the module does not offer it"


async def test_the_examples_the_panel_offers_are_the_ones_the_ai_sees(board):
    module = pb()

    served = await board._route_actions_examples()
    assert [entry["name"] for entry in served["examples"]] == [e["name"] for e in module.ACTION_EXAMPLES]

    listed = await board.list_prompt_action_examples()
    assert "Implement this task" in listed["content"]
    assert "{title}" in listed["content"], "the tool tells you what you can put in a template"


# ---------------------------------------------------------------------------
# pressing play
# ---------------------------------------------------------------------------

async def test_a_press_renders_the_prompt_and_sends_nothing(board):
    await add(board, "Add the toggle")
    identifier = await action(board, name="Implement this task",
                              template="Work on {title} ({id}) in {column}.")

    result = await board._play_action(identifier, board.cards[0]["id"])

    assert result["status"] == "success", result["content"]
    assert result["content"]["prompt"] == "Work on Add the toggle (%s) in Backlog." % board.cards[0]["id"]
    assert result["content"]["name"] == "Implement this task"
    assert board.cards[0]["comments"] == [], "rendering alone changes nothing on the card"


async def test_a_press_applies_only_the_side_effects_that_were_asked_for(board):
    await add(board, "Fix the toggle", column="In Progress")
    card_id = board.cards[0]["id"]

    plain = await action(board, name="Just ask", template="do {title}")
    first = await board._action_launched(plain, card_id, prompt="do Fix the toggle")
    assert "nothing else to do" in first["content"]
    assert board.cards[0]["column"] == column(board, "In Progress")["id"]
    assert board.cards[0]["comments"] == []

    busy = await action(board, name="Finish this", template="finish {id}",
                        column="In Progress", move_to="Done", log_as_comment=True)
    second = await board._action_launched(busy, card_id, prompt="finish %s" % card_id)

    assert "moved it to Done" in second["content"]
    assert board.cards[0]["column"] == column(board, "Done")["id"]
    assert board.cards[0]["comments"][0]["author"] == "action:Finish this"
    assert board.cards[0]["comments"][0]["text"] == f"finish {card_id}"


# ---------------------------------------------------------------------------
# the spec prompt
# ---------------------------------------------------------------------------

async def test_the_shipped_spec_prompt_sends_the_ai_to_openspec(board):
    await board.add_card("Placeholder")

    prompt, problem = await board._render_spec_prompt("scoring rewrite", "The scorer shall rank.")
    assert not problem

    assert "openspec" in prompt, "the default template is the OpenSpec shaped one"
    assert "project-board_import_openspec" in prompt
    assert "scoring rewrite" in prompt
    assert "The scorer shall rank." in prompt
    assert "'General'" in prompt, "the board it belongs to is named in the prompt"
    assert "'Backlog'" in prompt, "so is where the stories are supposed to land"


async def test_the_spec_prompt_is_yours_to_rewrite():
    board = await build(spec_action_prompt="Board {board}: turn this into cards in {backlog}.\n{spec}")

    prompt, problem = await board._render_spec_prompt(None, "some spec text")
    assert not problem
    assert prompt == "Board General: turn this into cards in Backlog.\nsome spec text", \
        "placeholders only, and nothing else appended"


async def test_an_empty_spec_is_refused_before_it_reaches_the_chat(board):
    prompt, problem = await board._render_spec_prompt("x", "   ")
    assert prompt is None and "no spec" in problem

    result = await board._route_spec_render(body={"title": "", "spec": ""})
    assert result["status"] == "error"


# ---------------------------------------------------------------------------
# batch intake
# ---------------------------------------------------------------------------

async def test_add_cards_lands_a_batch_in_the_order_it_was_listed(board):
    result = await board.add_cards([
        {"title": "First", "points": 2},
        {"title": "Second", "type": "story", "labels": ["backend"]},
        {"title": "Third", "blocked": True},
    ], column="To Do")

    assert result["status"] == "success", result["content"]
    assert titles(board, "To Do") == ["First", "Second", "Third"]
    assert board.cards[1]["type"] == "story" and board.cards[1]["labels"] == ["backend"]
    assert board.cards[2]["blocked"] is True
    assert board.cards[0]["column"] == column(board, "To Do")["id"]


async def test_add_cards_keeps_the_order_even_at_the_top_of_a_column(board):
    await board.add_cards([{"title": "One"}, {"title": "Two"}, {"title": "Three"}], to_top=True)

    assert titles(board, "Backlog") == ["One", "Two", "Three"]


async def test_add_cards_shares_what_the_items_do_not_say(board):
    await board.add_cards([{"title": "Alpha"}, {"title": "Beta", "assignee": "steven"}],
                          card_type="story", priority="high", assignee="ai", labels=["spec"],
                          points=3, due="2026-11-01")

    assert [card["type"] for card in board.cards] == ["story", "story"]
    assert [card["assignee"] for card in board.cards] == ["ai", "steven"]
    assert [card["points"] for card in board.cards] == [3, 3]
    assert [card["due"] for card in board.cards] == ["2026-11-01", "2026-11-01"]


async def test_add_cards_reports_the_items_it_skipped_instead_of_stopping(board):
    result = await board.add_cards([
        {"title": "Fine"},
        {"points": 2},
        {"title": "Wrong stage", "column": "Icebox"},
        "not even an object",
        {"title": "Bad date", "due": "next tuesday"},
    ])

    assert result["status"] == "success", "one good card is enough to write"
    assert titles(board, "Backlog") == ["Fine"]
    assert "no title" in result["content"]
    assert "Icebox" in result["content"]
    assert "2026-12-31" in result["content"], "the date complaint explains what it wants"

    assert (await board.add_cards([{"points": 1}]))["status"] == "error", "all bad is an error"


async def test_add_cards_validates_what_it_inherits(board):
    assert (await board.add_cards([{"title": "x"}], card_type="feature"))["status"] == "error"
    assert (await board.add_cards([{"title": "x"}], priority="urgent"))["status"] == "error"
    assert (await board.add_cards([]))["status"] == "error"


# ---------------------------------------------------------------------------
# openspec: reading a change folder
# ---------------------------------------------------------------------------

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
OPENSPEC_FOLDER = FIXTURES / "openspec"


async def build(**settings):
    """conftest's make_board for async tests: on_ready() is awaited on the loop the test is
    already running on, and each board gets a data folder of its own"""
    import core
    import importlib
    import tempfile

    core.config.config.load({
        "core": {"data_folder": tempfile.mkdtemp(prefix="pb-settings-")},
        "modules": {"settings": {"project-board": dict(settings)}},
    })

    instance = importlib.import_module("user_modules.project-board").ProjectBoard(FakeManager())
    await instance.on_ready()

    return instance


@pytest.fixture
async def openspec_board():
    """a board whose openspec_roots points at the fixture project. the fixture is a real
    openspec-shaped tree (requirements with scenarios, a tasks.md checklist, an archived
    change, main specs and a skip_specs refactor) rather than a string in a test"""
    return await build(openspec_roots=[str(OPENSPEC_FOLDER)])


def test_the_task_checklist_is_read_as_a_checklist():
    module = pb()
    tasks = module._parse_openspec_tasks((OPENSPEC_FOLDER / "changes/add-dark-mode/tasks.md").read_text())

    assert len(tasks) == 7, "prose under a heading is not a task"
    assert tasks[0] == {"number": "1.1", "group": "1. Theme Infrastructure",
                        "title": "Create ThemeContext with light/dark state", "done": False}
    assert [task["done"] for task in tasks].count(True) == 1, "[x] is the only mark that means done"
    assert tasks[-1]["number"] == "", "an unnumbered checkbox still counts"


def test_a_delta_spec_becomes_requirements_with_scenarios():
    module = pb()
    requirements = module._parse_openspec_spec(
        (OPENSPEC_FOLDER / "changes/add-dark-mode/specs/ui/spec.md").read_text(), "ui")

    assert {requirement["name"] for requirement in requirements} == {
        "Theme selection", "Contrast", "Remember me banner"}

    by_name = {requirement["name"]: requirement for requirement in requirements}
    assert by_name["Theme selection"]["scenarios"][0]["name"] == "User toggles dark mode"
    assert by_name["Theme selection"]["scenarios"][0]["lines"] == [
        "**WHEN** the user clicks the theme toggle",
        "**THEN** the app switches to dark mode and persists the choice"]
    assert by_name["Theme selection"]["kind"] == "added"
    assert by_name["Contrast"]["kind"] == "modified"
    assert "Previously" in by_name["Contrast"]["text"], "what changed from before is worth keeping"
    assert by_name["Remember me banner"]["scenarios"] == []
    assert by_name["Theme selection"]["capability"] == "ui"


def test_the_proposal_summary_keeps_the_parts_worth_reading():
    module = pb()
    summary = module._parse_openspec_proposal(
        (OPENSPEC_FOLDER / "changes/add-dark-mode/proposal.md").read_text())

    assert "Intent" in summary and "eye strain" in summary
    assert "Out of scope" in summary
    assert "CSS custom properties" in summary


async def test_a_change_without_a_configured_folder_is_reported_not_guessed(board):
    result = await board.import_openspec(change="add-dark-mode")
    assert result["status"] == "error"
    assert "no openspec folder is configured" in result["content"]

    assert "no openspec folder is configured" in (await board.read_openspec())["content"]


async def test_a_root_that_holds_no_openspec_project_says_so():
    board = await build(openspec_roots=[str(FIXTURES / "some-project-i-forgotten-to-clone")])
    assert "none of the configured openspec_roots" in (await board.import_openspec())["content"]


async def test_import_lands_one_testable_story_per_requirement(openspec_board):
    result = await openspec_board.import_openspec(change="add-dark-mode")
    assert result["status"] == "success", result["content"]

    stories = [card for card in openspec_board.cards if card["type"] == "story"]
    assert {card["title"] for card in stories} == {
        "Theme selection", "Contrast", "Remember me banner", "Theme persistence"}

    selection = next(card for card in stories if card["title"] == "Theme selection")
    assert "Scenario: User toggles dark mode" in selection["description"]
    assert "**WHEN** the user clicks the theme toggle" in selection["description"], \
        "the scenarios come along as acceptance criteria - that is what makes the story testable"
    assert "Requirement: Theme selection" in selection["description"]

    untestable = next(card for card in stories if card["title"] == "Remember me banner")
    assert "no scenario" in untestable["description"]
    assert "no scenario" in result["content"], "and the AI is told about it"

    assert [card["column"] for card in stories] == [column(openspec_board, "Backlog")["id"]] * 4

    epic = next(card for card in openspec_board.cards if card["type"] == "epic")
    assert epic["title"] == "OpenSpec change: add-dark-mode"
    assert "eye strain" in epic["description"], "the proposal's intent rides along"

    for card in openspec_board.cards:
        assert "openspec/add-dark-mode" in card["labels"], "a whole batch is filterable"
        assert card["source"].startswith("openspec:add-dark-mode#")


async def test_tasks_mode_mirrors_the_checklist_and_follows_the_boxes(openspec_board):
    result = await openspec_board.import_openspec(change="add-dark-mode", unit="tasks")
    assert result["status"] == "success", result["content"]

    tasks = [card for card in openspec_board.cards if card["type"] == "task"]
    assert len(tasks) == 7
    assert "1.1 Create ThemeContext with light/dark state" in [card["title"] for card in tasks]

    checked = next(card for card in tasks if card["title"].startswith("1.2"))
    assert checked["column"] == column(openspec_board, "Done")["id"], \
        "a task already ticked in the file lands in a done column"

    assert not [card for card in openspec_board.cards if card["type"] == "story"], \
        "tasks mode does not invent stories on the side"


async def test_importing_a_second_time_refreshes_rather_than_duplicates(openspec_board):
    await openspec_board.import_openspec(change="add-dark-mode")
    before = len(openspec_board.cards)

    story = next(card for card in openspec_board.cards if card["title"] == "Contrast")
    story["column"] = column(openspec_board, "In Progress")["id"]
    story["priority"] = "critical"
    story["points"] = 5
    story["assignee"] = "steven"
    story["labels"] = story["labels"] + ["urgent"]

    result = await openspec_board.import_openspec(change="add-dark-mode")
    assert len(openspec_board.cards) == before, "nothing new came in"
    assert "0 card(s) added" in result["content"]

    story = next(card for card in openspec_board.cards if card["title"] == "Contrast")
    assert story["column"] == column(openspec_board, "In Progress")["id"], \
        "the files decide what a requirement says, not what stage it reached"
    assert (story["priority"], story["points"], story["assignee"]) == ("critical", 5, "steven")
    assert "urgent" in story["labels"], "your own labels survive a refresh"

    assert story["description"].startswith("Requirement: Contrast")


async def test_a_ticked_task_moves_its_card_forwards_but_nothing_backwards(tmp_path):
    """tasks.md gets edited here, so this one works on a copy of the fixture tree rather than
    on the shipped fixture - and it also covers a root that is the repository folder"""
    import shutil

    project = tmp_path / "project"
    shutil.copytree(OPENSPEC_FOLDER, project / "openspec")

    openspec_board = await build(openspec_roots=[str(project)])
    await openspec_board.import_openspec(change="add-dark-mode", unit="tasks")

    todo = next(card for card in openspec_board.cards if card["title"].startswith("1.1"))
    todo["column"] = column(openspec_board, "In Progress")["id"]

    # the file is edited the way a session edits it: the work gets ticked off
    path = project / "openspec/changes/add-dark-mode/tasks.md"
    original = path.read_text()
    try:
        path.write_text(original.replace("- [ ] 1.1 Create", "- [x] 1.1 Create"))
        await openspec_board.import_openspec(change="add-dark-mode", unit="tasks")

        todo = next(card for card in openspec_board.cards if card["title"].startswith("1.1"))
        assert todo["column"] == column(openspec_board, "Done")["id"]

        untouched = next(card for card in openspec_board.cards if card["title"].startswith("1.3"))
        assert untouched["column"] != column(openspec_board, "Done")["id"]
    finally:
        path.write_text(original)

    await openspec_board.import_openspec(change="add-dark-mode", unit="tasks", update_done=False)
    todo = next(card for card in openspec_board.cards if card["title"].startswith("1.1"))
    assert todo["column"] == column(openspec_board, "Done")["id"], "and it is never dragged back"


async def test_a_dry_run_says_the_numbers_and_writes_nothing(openspec_board):
    result = await openspec_board.import_openspec(change="add-dark-mode", dry_run=True)

    assert result["status"] == "success", result["content"]
    assert "new card(s)" in result["content"]
    assert "nothing written yet" in result["content"]
    assert openspec_board.cards == []


async def test_the_archive_is_finished_work_and_never_backlog(openspec_board):
    listed = await openspec_board.read_openspec()

    assert "add-dark-mode" in listed["content"]
    assert "legacy-refactor" in listed["content"]
    assert "2025-01-23-old-theme" not in listed["content"]

    imported = await openspec_board.import_openspec(change="2025-01-23-old-theme")
    assert imported["status"] == "error"
    assert "in flight: add-dark-mode, half-drafted, legacy-refactor, unfinished, verbose-tasks" \
        in imported["content"]


async def test_a_plain_file_sitting_in_changes_is_not_a_change(openspec_board):
    """a real project has notes lying around in changes/ - RELEASE-NOTES.md, an
    IMPLEMENTATION_ORDER.md somebody dropped there. offering one as a change means a button in
    the panel that can only ever fail"""
    assert (OPENSPEC_FOLDER / "changes/RELEASE-NOTES.md").exists(), "the fixture has the stray file"

    state = await openspec_board._route_openspec_changes()
    assert "RELEASE-NOTES" not in str(state["changes"])

    listed = await openspec_board.read_openspec()
    assert "RELEASE-NOTES" not in listed["content"]

    imported = await openspec_board.import_openspec(change="RELEASE-NOTES.md")
    assert imported["status"] == "error", "and it cannot even be asked for by name"


async def test_a_change_that_is_only_a_proposal_still_gets_its_epic(openspec_board):
    """a change that was created and not yet written up is normal in a real project: it has a
    proposal and nothing else. refusing it loses the one card that is true about it"""
    result = await openspec_board.import_openspec(change="unfinished")

    assert result["status"] == "success", result["content"]
    assert [card["type"] for card in openspec_board.cards] == ["epic"]
    assert "only has a proposal" in result["content"], "and it says the stories are still missing"

    again = await openspec_board.import_openspec(change="unfinished")
    assert len(openspec_board.cards) == 1, "and it is idempotent like everything else"
    assert "0 card(s) added" in again["content"]


async def test_a_change_with_truly_nothing_in_it_says_so(openspec_board):
    result = await openspec_board.import_openspec(change="half-drafted")

    assert result["status"] == "error"
    assert "no proposal" in result["content"], "the refusal says what is missing"


async def test_a_task_line_too_long_for_a_card_is_cut_short_and_kept_in_full(openspec_board):
    """real tasks.md lines run to 700+ characters. a card titled with one of those is unreadable
    on a board, so the title is cut at a word and the card carries the whole line instead"""
    result = await openspec_board.import_openspec(change="verbose-tasks", unit="tasks")
    assert result["status"] == "success", result["content"]

    tasks = [card for card in openspec_board.cards if card["type"] == "task"]
    short = next(card for card in tasks if card["title"] == "1.1 Short one.")
    long = next(card for card in tasks if card["title"].startswith("1.2 "))

    assert len(long["title"]) <= 102, f"the title still has to fit on a card, got {len(long['title'])}"
    assert long["title"].endswith("\u2026") and not long["title"].endswith(" \u2026")
    assert " the golden tests" in long["description"], "nothing about the task is lost"
    assert short["description"].endswith("file") or "1.1" not in short["description"], \
        "a title that did not need cutting is not repeated in the description"

    # and cutting the title does not stop a re-import from finding the card again
    before = [card["id"] for card in openspec_board.cards]
    await openspec_board.import_openspec(change="verbose-tasks", unit="tasks")
    assert [card["id"] for card in openspec_board.cards] == before


async def test_read_sums_up_what_is_already_on_the_board(openspec_board):
    """the question this tool gets asked is 'what is still unplanned', so it answers it instead
    of leaving the model to count lines"""
    before = await openspec_board.read_openspec(change="add-dark-mode")
    assert "nothing on this board yet" in before["content"]

    await openspec_board.import_openspec(change="add-dark-mode", max_cards=3)

    after = await openspec_board.read_openspec(change="add-dark-mode")
    assert "on this board: 2/4 requirement(s)" in after["content"], after["content"]

    await openspec_board.import_openspec(change="add-dark-mode")
    full = await openspec_board.read_openspec(change="add-dark-mode")
    assert "on this board: 4/4 requirement(s)" in full["content"]
    assert "card(s) carrying the 'openspec/add-dark-mode' label" in full["content"]


async def test_a_skip_specs_change_still_has_a_task_list(openspec_board):
    result = await openspec_board.import_openspec(change="legacy-refactor", unit="tasks")
    assert result["status"] == "success", result["content"]

    assert [card["title"] for card in openspec_board.cards if card["type"] == "task"] == [
        "1.1 Split the scoring module into pure functions", "1.2 Delete the dead report writer"]

    read = await openspec_board.read_openspec(change="legacy-refactor")
    assert "skip_specs" in read["content"]


async def test_the_cap_keeps_a_monster_spec_off_the_board(openspec_board):
    result = await openspec_board.import_openspec(change="add-dark-mode", unit="both", max_cards=3)

    assert len(openspec_board.cards) == 3
    assert "left out by the max_cards limit" in result["content"]


async def test_the_repository_root_works_as_a_root():
    """point it at the project folder that *contains* openspec/, which is what someone
    copying coder's sandbox_paths would write"""
    board = await build(openspec_roots=[str(FIXTURES)])

    result = await board.import_openspec(change="add-dark-mode")
    assert result["status"] == "success", result["content"]


async def test_several_changes_in_flight_have_to_be_named(openspec_board):
    result = await openspec_board.import_openspec()

    assert result["status"] == "error"
    assert "several changes are in flight" in result["content"]


async def test_read_says_what_is_specified_and_what_is_on_the_board(openspec_board):
    before = await openspec_board.read_openspec()
    assert "0 card(s) on this board" in before["content"]
    assert "requirement(s) without a scenario" in before["content"]

    await openspec_board.import_openspec(change="add-dark-mode")

    after = await openspec_board.read_openspec(change="add-dark-mode")
    assert "NOT TESTABLE YET" in after["content"], "the one without a scenario stands out"
    assert "[not on the board]" not in after["content"], "imported stories are matched back up"
    assert after["content"].count("ui/") == 3


async def test_a_board_with_nothing_configured_says_what_to_set(isolated_paths):
    """an empty openspec_roots is the first thing every new install sees, and a hidden button or a
    bare 'not configured' leaves the feature undiscoverable, so the panel gets a sentence with the
    setting's name in it"""
    board = await build(enable_openspec=True)
    state = board._openspec_ui_state()

    assert state["enabled"] is True and state["ready"] is False
    assert "openspec_roots" in state["problem"], "it names the setting to change"

    assert board._ui_board()["settings"]["openspec"]["problem"], "the panel payload carries it"

    # a folder that is configured but is not an openspec project is its own answer
    board = await build(openspec_roots=[str(FIXTURES / "some-project-i-forgotten-to-clone")])
    state = board._openspec_ui_state()

    assert state["ready"] is False
    assert "some-project-i-forgotten-to-clone" in state["problem"], "it says which folder came up empty"


async def test_openspec_reading_can_be_switched_off():
    board = await build(enable_openspec=False, openspec_roots=[str(OPENSPEC_FOLDER)])

    assert "turned off" in (await board.import_openspec())["content"]
    assert board._openspec_ui_state()["ready"] is False


# ---------------------------------------------------------------------------
# what the panel and the system prompt get
# ---------------------------------------------------------------------------

async def test_the_panel_payload_carries_the_buttons_and_the_cheat_sheet(board):
    await action(board, name="Review this change", column="In Progress")
    payload = board._ui_board()

    assert [entry["name"] for entry in payload["actions"]] == ["Review this change"]
    assert payload["actions"][0]["column_name"] == "In Progress"

    assert "{id}" not in payload["options"]["placeholders"], "the panel gets names, braces and all"
    assert "id" in payload["options"]["placeholders"]
    assert "spec" in payload["options"]["spec_placeholders"]
    assert payload["options"]["openspec_units"] == ["requirements", "tasks", "both"]

    assert payload["settings"]["enable_prompt_actions"] is True
    assert payload["settings"]["openspec"]["ready"] is False, "no roots configured here"


async def test_the_openspec_routes_answer_the_strips_two_questions(openspec_board):
    state = await openspec_board._route_openspec_changes()
    assert state["ready"] is True
    assert {entry["id"] for entry in state["changes"]} == {
        "add-dark-mode", "half-drafted", "legacy-refactor", "unfinished", "verbose-tasks"}

    dark = next(entry for entry in state["changes"] if entry["id"] == "add-dark-mode")
    assert dark["requirements"] == 4 and dark["tasks"] == 7 and dark["tasks_done"] == 1
    assert dark["untestable"] == 1 and dark["on_board"] == 0

    imported = await openspec_board._route_openspec_import(
        {"change": "add-dark-mode", "unit": "requirements"})
    assert imported["status"] == "success", imported["content"]

    state = await openspec_board._route_openspec_changes()
    dark = next(entry for entry in state["changes"] if entry["id"] == "add-dark-mode")
    assert dark["on_board"] == 5, "the epic plus one card per requirement"


async def test_the_action_routes_round_trip(board):
    await add(board, "Add the toggle")
    card_id = board.cards[0]["id"]

    listing = await board._route_actions_list()
    assert listing["actions"] == [] and listing["placeholders"]

    created = await board._route_action_save({"name": "Implement this task",
                                              "template": "work on {id}", "column": ""})
    assert created["status"] == "success", created["content"]
    identifier = board.actions[0]["id"]

    assert [entry["id"] for entry in board._ui_board()["actions"]] == [identifier]

    rendered = await board._route_action_render({"action": identifier, "card": card_id})
    assert rendered["content"]["prompt"] == f"work on {card_id}"

    launched = await board._route_action_launched({"action": identifier, "card": card_id,
                                                   "prompt": "no side effects here"})
    assert "nothing else to do" in launched["content"]

    moved = await board._route_action_save({"id": identifier, "name": "Implement this task",
                                            "template": "work on {id}", "column": "",
                                            "move_to": "In Progress"})
    assert moved["status"] == "success", moved["content"]

    await board._route_action_launched({"action": identifier, "card": card_id})
    assert board.cards[0]["column"] == column(board, "In Progress")["id"]

    assert (await board._route_action_delete({"id": identifier}))["status"] == "success"
    assert board.actions == []


async def test_the_system_prompt_says_what_pressing_play_means(board):
    await action(board, name="Implement this task")
    await action(board, name="Review this change")

    prompt = await board.on_system_prompt()
    assert "2 prompt action(s)" in prompt
    assert "Implement this task" in prompt and "Review this change" in prompt
    assert "fills their chat input" in prompt


async def test_the_system_prompt_names_the_changes_the_cards_came_from(openspec_board):
    await openspec_board.import_openspec(change="legacy-refactor", unit="tasks")

    prompt = await openspec_board.on_system_prompt()
    assert "legacy-refactor" in prompt
    assert "import_openspec" in prompt


async def test_the_shipped_assets_carry_the_buttons_the_editors_and_the_reads():
    """none of this is reachable from python, so the shipped files are the thing under test"""
    module_dir = pathlib.Path(__file__).resolve().parent.parent
    script = (module_dir / "webui" / "assets" / "js" / "project_board.js").read_text()
    panel = (module_dir / "webui" / "templates" / "chat" / "index.html").read_text()
    actions = (module_dir / "webui" / "templates" / "modals" / "project_board_actions.html").read_text()
    spec = (module_dir / "webui" / "templates" / "modals" / "project_board_spec.html").read_text()
    styles = (module_dir / "webui" / "assets" / "css" / "project_board.css").read_text()

    # a press fills the chat input and focuses it, and does not send
    assert 'chat.user_input = text;' in script, "prefill, not send"
    assert "action/render" in script and "action/launched" in script
    assert "getElementById(\"user-input\")" in script
    assert "pb-input-peek" in script and "pb-hide-input.pb-input-peek" in styles, \
        "a press reveals the input bar even with the board full-screen"

    # one button when one action applies, a menu when several do
    assert "actionsFor(card)" in panel and "playAction(card, primaryAction(card))" in panel
    assert "pb-menu" in panel and "copyActionPrompt" in panel

    # the editors, and the examples that stop the blank page
    assert "actions/examples" in script and "applyExample" in script
    assert 'openModal("project_board_actions")' in script
    assert "pb-action-template" in actions and "{id}" not in actions.split("placeholder")[0]
    assert "spec/render" in script and 'openModal("project_board_spec")' in script
    assert "process spec" in spec.lower()

    # copying, and the openspec strip
    assert "briefText" in script and "navigator.clipboard" in script
    assert "execCommand" in script, "plain http has no clipboard api"
    assert "openspec/changes" in script and "land stories" in panel
    assert "dry_run: true" in script, "the strip quotes real numbers before it writes"

    # the keyboard knows about all of it
    for key in ('event.key === "p"', 'event.key === "a"', 'event.key === "s"', 'event.key === "c"'):
        assert key in script

    assert ".pb-play" in styles and ".pb-spec-preview" in styles and ".pb-openspec-row" in styles

    # a real project had thirty changes in flight when this strip was designed around three, and
    # an unbounded list pushed the entire board off the bottom of the panel
    assert 'class="pb-openspec-list"' in panel and ".pb-openspec-list" in styles
    list_rule = styles.split(".pb-openspec-list", 1)[1].split("}", 1)[0]
    assert "max-height" in list_rule and "overflow-y: auto" in list_rule
    assert "openspec.changes.length" in panel, "the strip says how many changes it is holding"

    # a fresh install has no openspec_roots, so the strip has to be offered anyway (it opens to
    # explain itself) and the spec dialog has to warn that its stories cannot be landed yet
    assert 'x-show="openspecOffered()"' in panel and "openspecOffered()" in script
    assert 'x-show="showOpenspec && openspecReady()"' in panel, "no pointless controls before setup"
    assert "specLandingNote()" in script and 'class="pb-spec-note"' in spec
    assert ".pb-spec-note" in styles

    # the play button only exists when an action applies, and its title reads the action - so
    # the binding has to sit inside an x-if rather than an x-show, or Alpine evaluates
    # primaryAction(card).name on a card that has none
    assert 'x-if="actionsEnabled() && actionsFor(card).length"' in panel

    # an HTML entity in a bound expression is decoded before Alpine compiles it, and a decoded
    # newline is a syntax error in the generated function - which fails the whole panel silently
    dialog = (module_dir / "webui" / "templates" / "modals" / "project_board_card.html").read_text()
    for markup in (panel, actions, spec, dialog):
        for expression in re.findall(r':[\w.-]+="([^"]*)"', markup):
            assert "&#" not in expression, f"entity in an alpine expression: {expression[:60]}"


async def test_every_tool_and_every_parameter_is_documented(board):
    """what the model is handed is built out of these docstrings, so a parameter without a
    description is a parameter it has to guess at - which is how a tool that takes a `root`
    ends up being pointed at the wrong project"""
    import core.tool_loader

    class Channel:
        def __init__(self, modules):
            self.manager = type("M", (), {"modules": modules})()

        def log(self, *args):
            pass

    loader = core.tool_loader.ToolLoader(Channel({"project-board": board}))
    loader.register_module(board)

    mine = {name: entry["tool"]["function"] for name, entry in loader.catalog.items()
            if name.startswith("project-board_")}
    assert len(mine) >= 24, f"the module offers {len(mine)} tools, which looks like a regression"

    undocumented = []
    for name, function in mine.items():
        if not function.get("description"):
            undocumented.append(f"{name} has no description")
        for parameter, schema in function["parameters"]["properties"].items():
            if not schema.get("description"):
                undocumented.append(f"{name}.{parameter} has no description")
            if schema["type"] not in ("string", "integer", "boolean", "array", "object", "number"):
                undocumented.append(f"{name}.{parameter} is typed {schema['type']!r}")

    assert not undocumented, "; ".join(undocumented)

    # the two tools whose arguments are worth getting wrong, because they write a lot or read
    # someone's project on the strength of a path
    batch = mine["project-board_add_cards"]["parameters"]["properties"]
    assert batch["cards"]["type"] == "array" and batch["labels"]["type"] == "array"
    assert "openspec" in mine["project-board_import_openspec"]["description"].lower()
    assert mine["project-board_import_openspec"]["parameters"]["properties"]["dry_run"]["type"] == "boolean"


async def test_an_action_cannot_point_at_a_column_that_is_not_there(board):
    """a play button that quietly moves nothing is worse than one that is not there, so a stage
    that does not exist on this board is refused instead of being remembered as a dead setting"""
    await add(board, "Add the toggle")
    identifier = await action(board, name="Finish this", template="finish {id}")

    refused = await board.edit_prompt_action(identifier, move_to="In Review")
    assert refused["status"] == "error" and "column" in refused["content"]

    entry = next(item for item in board.actions if item["id"] == identifier)
    assert entry["move_to"] == "", "the old configuration is kept, not half applied"
    assert entry["log_as_comment"] is False

    assert (await board.add_prompt_action("Review this", "review {id}",
                                          column="In Progress"))["status"] == "success"
    assert (await board.add_prompt_action("Nope", "review {id}", column="In Review"))["status"] == "error"

    assert (await board.add_column(name="In Review"))["status"] == "success"
    review = column(board, "In Review")["id"]
    assert (await board.edit_prompt_action(identifier, move_to="In Review",
                                           log_as_comment=True))["status"] == "success"

    entry = next(item for item in board.actions if item["id"] == identifier)
    assert entry["move_to"] == review and entry["log_as_comment"] is True


# --------------------------------------------------------------------------- more than one repo

def two_projects(root):
    """two separate openspec projects, which is the whole reason openspec_roots is a list.
    returns (root_path, [project_a, project_b]) with one shared change name on purpose, because
    that is the case a tool must not guess about"""
    import shutil

    first = root / "frontend"
    second = root / "backend"
    shutil.copytree(OPENSPEC_FOLDER, first / "openspec")

    (second / "openspec/changes/quiet-hours").mkdir(parents=True)
    (second / "openspec/changes/fix-login").mkdir(parents=True)
    (second / "openspec/specs").mkdir()

    (second / "openspec/changes/quiet-hours/proposal.md").write_text(
        "## Why\n\nNotifications at night are rude.\n")
    (second / "openspec/changes/quiet-hours/tasks.md").write_text(
        "## 1. Quiet hours\n\n- [ ] 1.1 Add the window to the settings model\n")
    (second / "openspec/changes/fix-login/proposal.md").write_text(
        "## Why\n\nThe backend one.\n")

    # the same change name in the first project, so ambiguity is on the table
    (first / "openspec/changes/fix-login").mkdir()
    (first / "openspec/changes/fix-login/proposal.md").write_text("## Why\n\nThe frontend one.\n")

    return first, second


async def test_a_second_root_is_not_invisible_just_because_another_came_first(isolated_paths):
    """the strip used to stop at the first project that had changes, which made the second repo
    unreachable from the panel even though the tools could read it"""
    first, second = two_projects(isolated_paths)
    board = await build(openspec_roots=[str(first), str(second)])

    state = await board._route_openspec_changes()
    listed = {entry["id"]: entry for entry in state["changes"]}

    assert len(state["bases"]) == 2, "both projects are read"
    assert "quiet-hours" in listed, "the second project's change is offered"
    assert listed["quiet-hours"]["root"] == str(second)
    assert listed["quiet-hours"]["root_name"] == "backend"
    assert listed["add-dark-mode"]["root_name"] == "frontend"
    assert listed["quiet-hours"]["requirements"] == 0 and listed["quiet-hours"]["tasks"] == 1


async def test_a_change_in_the_second_project_can_be_landed_by_name_alone(isolated_paths):
    first, second = two_projects(isolated_paths)
    board = await build(openspec_roots=[str(first), str(second)])

    result = await board.import_openspec(change="quiet-hours")

    assert result["status"] == "success", result["content"]
    assert "(from backend)" in result["content"], result["content"].splitlines()[0]
    assert str(second) not in result["content"], "a name the user recognises, not their path"

    cards = [card for card in board.cards if card["type"] == "epic"]
    assert any("quiet-hours" in card["title"] for card in cards)


async def test_a_change_name_two_projects_share_is_refused_not_guessed(isolated_paths):
    first, second = two_projects(isolated_paths)
    board = await build(openspec_roots=[str(first), str(second)])

    imported = await board.import_openspec(change="fix-login")
    assert imported["status"] == "error"
    assert "more than one" in imported["content"] and "root=" in imported["content"]
    assert "frontend, backend" in imported["content"], "the refusal names them the way you do"

    read = await board.read_openspec(change="fix-login")
    assert read["status"] == "error", "the same rule for reading as for writing"

    # naming the root settles it, and the two are clearly told apart
    picked = await board.import_openspec(change="fix-login", root=str(second))
    assert picked["status"] == "success", picked["content"]
    assert "backend" in picked["content"]

    report = await board.read_openspec(change="fix-login", root="backend")
    assert report["status"] == "success" and "backend" in report["content"]


async def test_the_listing_covers_every_project_and_says_so(isolated_paths):
    first, second = two_projects(isolated_paths)
    board = await build(openspec_roots=[str(first), str(second)])

    report = await board.read_openspec()

    assert "across 2 roots" in report["content"]
    assert "frontend:" in report["content"] and "backend:" in report["content"]
    assert "quiet-hours" in report["content"] and "add-dark-mode" in report["content"]
    assert "name it with root=" in report["content"]


async def test_naming_a_root_you_do_not_have_is_refused(isolated_paths):
    first, second = two_projects(isolated_paths)
    board = await build(openspec_roots=[str(first), str(second)])

    unknown = await board.import_openspec(change="quiet-hours", root="whatever")
    assert unknown["status"] == "error" and "openspec_roots does not include" in unknown["content"]

    # a configured root that is not a project says so, rather than reporting an empty listing
    board = await build(openspec_roots=[str(first), str(isolated_paths)])
    narrow = await board.import_openspec(change="add-dark-mode", root=str(isolated_paths))
    assert narrow["status"] == "error" and "no openspec/changes folder inside it" in narrow["content"]


async def test_two_roots_with_the_same_folder_name_fall_back_to_the_path(isolated_paths):
    """two clones of one repo in different folders - common with git worktrees - have the same
    folder name, and then the only thing that tells them apart is the path someone configured"""
    import shutil

    first, second = two_projects(isolated_paths)
    twin = isolated_paths / "other" / "backend"
    twin.parent.mkdir()
    shutil.copytree(second, twin)

    board = await build(openspec_roots=[str(first), str(second), str(twin)])
    report = await board.read_openspec(change="fix-login")

    assert report["status"] == "error"
    assert str(second) in report["content"] and str(twin) in report["content"], report["content"]


async def test_switching_the_feature_off_also_stops_the_writing(isolated_paths):
    """the setting promises to hide the play buttons, and a tool that kept writing them while the
    user had them hidden would leave invisible settings nobody knows are there"""
    board = await build(enable_prompt_actions=False)

    for call in [board.add_prompt_action("Ship it", "ship {id}"),
                 board.edit_prompt_action("whatever", name="x"),
                 board.delete_prompt_action("whatever")]:
        refused = await call
        assert refused["status"] == "error" and "switched off" in refused["content"]

    assert board.actions == [], "nothing half-configured is waiting for the switch to come back"

    # reading is still fine: the panel and the AI both need to know the buttons are off, not that
    # something is broken
    assert (await board.list_prompt_actions())["status"] == "success"
    assert board._ui_board()["settings"]["enable_prompt_actions"] is False
    assert (await board._route_actions_list())["actions"] == []

    # the panel's save route delegates to the tools, so it is covered by the same guard
    assert (await board._route_action_save({"name": "x", "template": "y"}))["status"] == "error"


async def test_a_press_cannot_be_made_while_the_feature_is_off(board):
    """a press is the user's gesture; with the buttons hidden there is no gesture to honour, so the
    side effects (moving the card, logging a comment) do not happen behind their back either"""
    import core

    await add(board, "Add the toggle")
    identifier = await action(board, name="Ship it", template="ship {id}",
                              move_to="Done", log_as_comment=True)

    core.config.config.load({
        "core": {"data_folder": str(board.card_store.path).rsplit("/", 1)[0]},
        "modules": {"settings": {"project-board": {"enable_prompt_actions": False}}},
    })

    refused = await board._play_action(identifier, board.cards[0]["id"])
    assert refused["status"] == "error" and "switched off" in refused["content"]

    launched = await board._action_launched(identifier, board.cards[0]["id"], prompt="ship it")
    assert launched["status"] == "error"
    assert board.cards[0]["column"] == column(board, "Backlog")["id"], "the card did not move"
    assert not board.cards[0].get("comments"), "and nothing was logged"
