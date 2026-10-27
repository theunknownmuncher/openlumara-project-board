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
    assert set(payload["settings"]) == {"keep_chat_input", "refresh_interval"}

    overdue = {card["id"]: card["overdue"] for card in payload["cards"]}
    assert overdue[board.cards[0]["id"]] is True, "the panel gets overdue precomputed"


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
