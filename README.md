# project-board — a kanban / scrum board for you and your AI

A user module for [OpenLumara](https://github.com/Rose22/openlumara) that gives you a proper
**project board**: user stories, tasks and bugs on a board with columns, drag & drop, story
points, priorities, labels, due dates, WIP limits and comments.

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
- `n` new card, `/` search, `r` reload, `Esc` back to the chat, and `alt + ←/→/↑/↓` to move the
  focused card between columns or reorder it — no mouse needed
- the board refreshes itself when your AI changes it (websocket push), when another tab changes
  it, and after each AI turn. Changes made by hand are picked up by the AI the same way: every
  tool reloads from disk first
- works on a phone: one column at a time, swipe sideways, card dialogs stack vertically

### For your AI

| Tool | What it does |
|---|---|
| `project-board_read_board` | The whole board as compact lines with short card ids, with column / text / assignee / priority / label / type filters and an option to include descriptions |
| `project-board_board_stats` | Progress, per-column counts, WIP limit breaches, blocked / overdue / unassigned counts, per-person workload and label usage (great for standups) |
| `project-board_add_card` | Create a card (column, type, priority, assignee, labels, points, due date, blocked, top-or-bottom) |
| `project-board_edit_card` | Change any field; empty values clear description / assignee / labels / due |
| `project-board_move_card` | Move to another column, optionally above a specific card (use it whenever work progresses) |
| `project-board_reorder_column` | Set the top-to-bottom order of a column, i.e. prioritize the work |
| `project-board_duplicate_card` | Copy a card, keeping its fields (never its comments) |
| `project-board_delete_card` | Remove a card and its comments |
| `project-board_add_comment` / `project-board_delete_comment` | Leave progress notes and questions on a card |
| `project-board_add_column` / `project-board_update_column` / `project-board_delete_column` | Shape the workflow: rename, WIP limits, done flags, reordering, and where the cards of a deleted column go |

Cards are addressed by their **short id** (`7QK3MZ`, printed by `read_board`), by their exact
title, or by an unambiguous piece of the title. When a phrase matches several cards the tools
refuse to guess and say so, so "the login one" can never quietly edit the wrong card.

Card types are `epic`, `story`, `task`, `bug` and `chore`; priorities are `critical`, `high`,
`medium` and `low`. Column names are yours: the default `Backlog → To Do → In Progress → Done`
works for both kanban and scrum, and a column called `Done` / `Closed` / `Complete(d)` is
treated as finished work (that is what the progress bar and the point totals count from).

While `insert_system_prompt` is on, the AI always sees the open cards, so you can just say
"what is blocked?" or "we shipped the login thing" without making it look first. The prompt
holds board totals plus open cards only, capped by `max_cards_in_prompt`.

### Command

```
/board              # the whole board as text (any channel, including cli)
/board auth         # filtered by text
```

## Install

1. Put this folder in OpenLumara's user modules directory
   (default `openlumara/user_modules/`, or wherever `user_modules.path` points).
2. Restart OpenLumara.
3. Enable it: `/module project-board` (then `/restart`), or tick it in the WebUI settings.

No Python dependencies. With the WebUI channel enabled the board panel appears in the chat
header; on other channels (`/board`, cli, telegram, …) the tools and the command still work.

## Settings

| Setting | Default | Description |
|---|---|---|
| `insert_system_prompt` | `true` | Keep the board in the system prompt so the AI knows what is on it without looking. Only open cards are listed |
| `max_cards_in_prompt` | `40` | Maximum amount of cards listed there; totals are always included |
| `default_columns` | `Backlog, To Do, In Progress, Done` | Columns created on a fresh board. Changing it later does not touch an existing board |
| `keep_chat_input` | `true` | Keep the chat input bar visible while the board is open, so you can talk to your AI without leaving the board. Off = full-screen board |
| `refresh_interval` | `15` | Seconds between automatic refreshes while open (`0` disables polling). Board changes are pushed instantly either way |
| `enable_webui_extension` | `true` | Auto-added by the framework; toggles the board panel and its API routes |

## Files

```
module.py                                 <- module: tools, /board, prompt, /api/ext/project-board routes
webui/templates/chat/index.html           <- the board panel (below_header slot: it takes the chat panel over)
webui/templates/chat/header.html          <- chat header toggle button (right slot)
webui/templates/modals/project_board_card.html  <- card dialog (fields + comments)
webui/templates/svg/board.svg             <- board icon used by the header button
webui/assets/js/project_board.js          <- panel logic (Alpine store "projectBoard"), drag & drop, keyboard
webui/assets/css/project_board.css        <- board + dialog styles (everything is namespaced under .pb-)
tests/conftest.py                         <- self-contained fixtures (tmp data folder, fake manager)
tests/test_board.py                       <- tool surface, routes, stats and prompts
LICENSE                                   <- GPL-3.0-or-later
README.md                                 <- this file
.gitignore                                <- python/editor/OS artifacts
```

Board data lives in OpenLumara's data folder, as plain JSON you can eyeball or hand-edit:

```
<data>/project_board_columns.json
<data>/project_board_cards.json
```

## How the panel replaces the chat panel

Nothing in the core WebUI is touched. The panel is rendered into the chat panel's
`below_header` slot, and while it is open the module's stylesheet hides `#messages` (and
`#input` when `keep_chat_input` is off) via two classes on `<body>`
(`pb-board-open`, `pb-hide-input`). The board is a sibling in the same flex column, so it simply
grows into the space. Closing it (button, `Esc`, or `alt + b`) restores the chat and remembers
the choice in `localStorage`.

## Notes

- **WIP limits warn, they do not block.** Going over a limit is a decision, not an error, so both
  the panel and the tools answer with a warning instead of a refusal.
- Deleting a column moves its cards to the first remaining open column (or the column you name,
  or deletes them if you ask for that explicitly), and the last column left on the board cannot
  be deleted — a board with no columns cannot hold anything.
- Deleting a card is immediate but always confirmed in the panel. The AI will only do it when you
  asked for it.
- `duplicate_card` puts the copy right below the original and appends ` (copy)`, so it is obvious
  which one you are looking at.
- Cards whose column disappeared (hand-edited storage) are adopted by the first column on the
  next read, so nothing becomes invisible.
- There is one board per OpenLumara install. Separate projects by label (the filter bar has a
  label picker) or by column, or point a second install at another `core.data_folder`.

## License

Copyright (C) 2026 theunknownmuncher <theunknownmuncher@protonmail.com>

GPL-3.0-or-later (see [LICENSE](LICENSE)).
