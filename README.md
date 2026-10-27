# project-board — kanban / scrum boards for you and your AI

A user module for [OpenLumara](https://github.com/Rose22/openlumara) that gives you proper
**project boards**: user stories, tasks and bugs on a board with columns, drag & drop, story
points, priorities, labels, due dates, WIP limits and comments. One board per project, and you
switch between them.

What makes it different from a plain todo list is that **both of you can work the board**.
You drag cards around in the WebUI, and your AI runs the same board through tools — it can
break a project down into stories, prioritize the backlog, move your work along as you report
progress, write up standup summaries, and leave notes on cards. Every change is visible on both
sides within a moment, over the websocket.

The board **takes over the chat panel** in the WebUI while it is open: the message history makes
room for the columns, so you get a full-height board without leaving the chat. The chat input
stays at the bottom by default, so you can keep talking to your AI ("move the login story to
review and tell me what is at risk") while looking at the board. Turn that off for a
full-screen board.

## What you get

### Boards, one per project

- a **board switcher** in the panel header as soon as there is more than one board; the panel
  and your AI always work on the board that is active
- `shift + N` (or the `+` next to the switcher) creates a board, with a name, what it is for,
  and the option to copy the current column layout so every project runs through the same stages
- the gear opens **this board**: rename it, write what it is for, see its totals, delete it
  (with a confirmation that says how many cards go with it)
- boards are separate rooms: columns, labels, assignees, WIP limits and cards belong to one
  board, so two projects can both have a column called `To Do` and never see each other's cards
- switching boards clears the filters, because a label from another project only looks like an
  empty board

### The board panel (WebUI)

- a toggle button in the chat header (with a live card count), or `alt + b` from anywhere
- columns with card counts, story point totals and WIP limits (a column over its limit is
  flagged in red, both in the header and when the AI pushes past it)
- **drag & drop** cards between columns and **reorder** them inside a column (a drop line shows
  where the card lands), plus drag a column by its grip to reorder the board
- cards show type, priority, labels, points, due date (red when overdue), blocked state,
  assignee initials and comment count
- click a card to open it: all fields, plus its **comment thread**, duplicate and delete
- inline card composer per column (`+`), a full "new card" dialog, inline column settings
  (rename, WIP limit, done flag, reorder, delete)
- search plus filters by assignee, priority, type and label, sorting inside a column
  (board order / priority / points / due / newest / alphabetical), hide-done toggle
- a progress bar (cards in done columns), a board summary line (cards, percent done, open points,
  blocked, overdue) and a blocked / overdue pill in the header
- `n` new card, `shift + N` new board, `/` search, `r` reload, `Esc` back to the chat, and
  `alt + ←/→/↑/↓` to move the focused card between columns or reorder it — no mouse needed
- the board refreshes itself when your AI changes it or switches to another board (websocket
  push), when another tab changes it, and after each AI turn. Changes made by hand are picked up
  by the AI the same way: every tool reloads from disk first
- works on a phone: the switcher and both strips wrap, one column at a time, swipe sideways,
  card dialogs stack vertically

### For your AI

| Tool | What it does |
|---|---|
| `project-board_list_boards` | Every board with its card counts, marking the active one |
| `project-board_create_board` | Another project: name, purpose, its own column layout (or a copy of an existing board's), and it switches to it unless you say otherwise |
| `project-board_activate_board` | Switch to another board — from then on the tools and the panel are on that board |
| `project-board_edit_board` | Rename a board or change what its description says |
| `project-board_delete_board` | Delete a board with its columns and cards; refuses while it still has cards unless you pass `force` |
| `project-board_read_board` | The board as compact lines with short card ids, with column / text / assignee / priority / label / type filters, descriptions on request, and `board=` to look at another board without switching |
| `project-board_board_stats` | Progress, per-column counts, WIP limit breaches, blocked / overdue / unassigned counts, per-person workload and label usage (great for standups), `board=` to summarize another project |
| `project-board_add_card` | Create a card (column, type, priority, assignee, labels, points, due date, blocked, top-or-bottom) |
| `project-board_edit_card` | Change any field; empty values clear description / assignee / labels / due |
| `project-board_move_card` | Move to another column, optionally above a specific card (use it whenever work progresses) |
| `project-board_reorder_column` | Set the top-to-bottom order of a column, i.e. prioritize the work |
| `project-board_duplicate_card` | Copy a card, keeping its fields (never its comments) |
| `project-board_delete_card` | Remove a card and its comments |
| `project-board_add_comment` / `project-board_delete_comment` | Leave progress notes and questions on a card |
| `project-board_add_column` / `project-board_update_column` / `project-board_delete_column` | Shape a board's workflow: rename, WIP limits, done flags, reordering, and where the cards of a deleted column go |

**Writes only ever touch the active board.** `read_board` and `board_stats` can look at another
board with `board="…"`, which never moves the pen — so your AI can compare two projects and then
say "switch me to the site one" before it starts editing.

Cards are addressed by their **short id** (`7QK3MZ`, printed by `read_board` and unique across all
boards), by their exact title, or by an unambiguous piece of the title. When a phrase matches
several cards the tools refuse to guess and say so, so "the login one" can never quietly edit the
wrong card.

Card types are `epic`, `story`, `task`, `bug` and `chore`; priorities are `critical`, `high`,
`medium` and `low`. Column names are yours: the default `Backlog → To Do → In Progress → Done`
works for both kanban and scrum, and a column called `Done` / `Closed` / `Complete(d)` is
treated as finished work (that is what the progress bar and the point totals count from).

While `insert_system_prompt` is on, the AI always sees the active board's open cards, so you can
just say "what is blocked?" or "we shipped the login thing" without making it look first. The
prompt names the active board, lists the other board names so it knows what it can switch to, and
holds open cards only, capped by `max_cards_in_prompt`.

### Command

```
/board                     the whole active board as text (any channel, including cli)
/board auth                filtered by text
/board switch site redo    switch to another board
/board list                every board with its counts
/boards                    the same list, as its own command
```

## Install

1. Put this folder in OpenLumara's user modules directory
   (default `openlumara/user_modules/`, or wherever `user_modules.path` points).
2. Restart OpenLumara.
3. Enable it: `/module project-board` (then `/restart`), or tick it in the WebUI settings.

No Python dependencies. With the WebUI channel enabled the board panel appears in the chat
header; on other channels (`/board`, cli, telegram, …) the tools and the commands still work.

## Settings

| Setting | Default | Description |
|---|---|---|
| `insert_system_prompt` | `true` | Keep the active board in your AI's system prompt so it always knows what is on it without having to look it up. Only open cards are listed |
| `max_cards_in_prompt` | `40` | Maximum amount of cards listed there; board totals are always included |
| `default_board_name` | `General` | Name of the board created the first time the module runs, and the name the first project gets when it takes over board-less storage from an older install |
| `default_columns` | `Backlog, To Do, In Progress, Done` | The column layout every new board starts out with. A column named Done, Closed, Complete or Completed counts as finished work. Changing it later does not touch existing boards |
| `keep_chat_input` | `true` | Keep the chat input bar visible while the board is open, so you can tell your AI to change the board without leaving it. Off = full-screen board |
| `refresh_interval` | `15` | Seconds between automatic refreshes while open (`0` disables polling). Board changes are pushed instantly either way |
| `enable_webui_extension` | `true` | Auto-added by the framework; toggles the board panel and its API routes |

## Files

```
module.py                                       <- module: tools, commands, prompt, /api/ext/project-board routes
webui/templates/chat/index.html                 <- the board panel (below_header slot: it takes the chat panel over)
webui/templates/chat/header.html                <- chat header toggle button (right slot)
webui/templates/modals/project_board_card.html  <- card dialog (fields + comments)
webui/templates/svg/board.svg                   <- board icon used by the header button
webui/assets/js/project_board.js                <- panel logic (Alpine store "projectBoard"), boards, drag & drop, keyboard
webui/assets/css/project_board.css              <- board + dialog styles (everything is namespaced under .pb-)
tests/conftest.py                               <- self-contained fixtures (tmp data folder, fake manager)
tests/test_board.py                             <- tool surface, routes, stats, boards and prompts
LICENSE                                         <- GPL-3.0-or-later
README.md                                       <- this file
.gitignore                                      <- python/editor/OS artifacts
```

Board data lives in OpenLumara's data folder, as plain JSON you can eyeball or hand-edit:

```
<data>/project_board_boards.json    <- one entry per board, with the active one flagged
<data>/project_board_columns.json   <- every board's columns; "board" says which one, "order" where it sits
<data>/project_board_cards.json     <- every board's cards; "board" and "column" say where a card lives
```

## Notes

- **WIP limits warn, they do not block.** Going over a limit is a decision, not an error, so both
  the panel and the tools answer with a warning instead of a refusal.
- **Deleting a board deletes its cards.** It refuses while the board still has cards unless you
  pass `force`, the panel asks you to confirm, and the last board left on the install cannot be
  deleted. If you meant to clean a project rather than remove it, delete the cards instead.
- Cards never move between boards by themselves. Moving a card "to another project" means creating
  it there (or duplicating it there and deleting the original), which keeps the two boards honest
  about what each project still owes.
- Deleting a column moves its cards to the first remaining open column of that board (or the
  column you name, or deletes them when asked), and the last column on a board cannot be deleted.
- Deleting a card is immediate but always confirmed in the panel. The AI will only do it when you
  asked for it.
- `duplicate_card` puts the copy right below the original and appends ` (copy)`, so it is obvious
  which one you are looking at.
- Hand-edited storage is repaired instead of being lost: cards whose column disappeared are
  adopted by the first column of their board, items pointing at a board that no longer exists are
  adopted by the first board, and a board list with nothing flagged active falls back to the first
  board.
- Storage from before boards existed (one set of cards and columns, no `board` field) is migrated
  on the first start after updating: it becomes the `default_board_name` board with its columns in
  the order they were in, and nothing is renamed or dropped.

## License

Copyright (C) 2026 theunknownmuncher <theunknownmuncher@protonmail.com>

GPL-3.0-or-later (see [LICENSE](LICENSE)).
