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
- the board covers the chat instead of resetting it: close it and the chat is scrolled back to
  exactly where you left it, even if the AI added messages in the meantime. A chat you opened
  while the board was covering it comes back at its newest message
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
- `n` new card, `shift + N` new board, `/` search, `r` reload, `a` prompt actions, `s` process a
  spec, `c` copy what you can see as a brief, `Esc` back to the chat, and `alt + ←/→/↑/↓` to move
  the focused card between columns or reorder it — no mouse needed
- it keeps itself current. It loads the moment you open it, and while it stays on screen it
  reloads on a timer you control from the bottom status bar: an **auto-refresh** checkbox plus a
  field for the interval in seconds (5 by default). With the box unticked and its field greyed
  out, the board still reloads when you open it, when you come back to the tab, on `r`, and the
  instant your AI changes something (websocket push). Both choices are remembered per browser.
  Changes you make by hand are picked up by the AI the same way: every tool reloads from disk
  first
- works on a phone: the switcher and both strips wrap, one column at a time, swipe sideways,
  card dialogs stack vertically

### Play buttons: prompts *you* wrote, one press

The board can hold **prompt actions**: prompt templates you wrote, with `{placeholders}` for a
card's fields in them. Each one becomes a ▶ button on a card, and pressing it drops the finished
prompt into the chat input and focuses it — **it never sends anything**, so you always read what
is about to be asked and press enter yourself.

- press ▶ (or `p` on a focused card) and the card's own fields are already filled in:
  `Work on card 7QK3MZ ("Add the toggle") on the General board, which sits in In Progress…`
- one button when one action applies to the card; a small menu when several do (`shift + p`), and
  every action there can be **copied** instead of filled in, which is the quick way to paste a
  task into any prompt you are typing
- an action can be scoped to **one column**, so play means something different in the backlog
  ("plan this, write no code") than it does in review ("go through the diff against the card")
- optionally a press also moves the card ("this stage is done") and leaves the prompt on the card
  as a comment, so there is a trail of what each button asked for
- **nothing is canned.** `a` opens the action editor: 17 shipped examples fill the form so you
  never start from a blank page, and what you save is yours to rewrite. They are never created
  behind your back, and they live on the board they belong to
- placeholders: `{id} {title} {description} {column} {board} {type} {priority} {assignee}`
  `{labels} {points} {due} {comments} {change} {date}`. Braces around anything else are left
  exactly as you wrote them, so json or code inside a prompt survives untouched
- **copy brief** (`c`, or the copy icon) puts the cards you can see on the clipboard as a numbered
  markdown list (`1. [7QK3MZ] Add the toggle (3p, high)`), honouring your filters — handy for
  "work through these in order" or for pasting today's plan somewhere else

Ask your AI to set your buttons up ("give me a play button for the backlog that plans instead of
implements") — it has tools for that too, and `list_prompt_actions` tells it what your buttons
will do when you say "I just played that card".

### OpenSpec: from a spec to testable stories

If your project uses [OpenSpec](https://github.com/Fission-AI/OpenSpec), the board reads it
instead of retyping it.

- the **process spec** button, dressed like **new card** because it is the other way a card gets
  made, opens the dialog: paste what you want built, preview the prompt, and it
  fills your chat with a prompt (from the `spec_action_prompt` setting, yours to rewrite) that
  tells your AI to turn the spec into an OpenSpec change and land its stories in the backlog.
  The spec itself never lands on the board — only the work it produced
- `project-board_import_openspec` then reads `openspec/changes/<change>/`: each
  `### Requirement:` becomes a **story** whose acceptance criteria are the requirement's
  `#### Scenario:` GIVEN/WHEN/THEN lines — the testable unit, not a vibe. Ask for `unit="tasks"`
  instead and the board mirrors `tasks.md` one checkbox per card
- re-importing **refreshes instead of duplicating**: a card remembers the requirement or task it
  came from, so the files stay the truth about what a story says while the column, priority,
  points, assignee and title stay yours. A task ticked off in `tasks.md` moves to a done column,
  and nothing is ever dragged backwards out of one
- imported cards carry an `openspec/<change>` label, so a whole change is one filter away, and
  `read_openspec` answers "what is specified, what is on the board, and which requirements have
  no scenario yet?"
- the layers button opens a strip listing the changes in flight with their numbers (a real
  project had thirty, so the list scrolls and says how many it is holding), and *land stories*
  quotes the counts before it writes anything
- with nothing configured the strip is still offered, and opens to tell you which setting to
  change, because a hidden button only leaves the feature undiscoverable
- a change that only has a proposal so far - created, not yet written up - gets its epic card and
  a note that the stories follow once it has requirements or tasks, rather than a refusal
- a `tasks.md` line that runs to 700 characters (they do) is cut at a word for the card title and
  kept in full in that card's description, so nothing is lost and nothing needs scrolling sideways
- `read_openspec` ends with the answer instead of a raw list: `on this board: 3/4 requirement(s),
  1 without a scenario`
- `openspec_roots` is a list because people have more than one repo: every folder in it that
  holds an `openspec/changes` is read, the strip shows them all and labels each row with its
  project once more than one is in play, and a change in your second repo can be imported by name
  alone. Two repos with a change of the same name are *reported*, never guessed about (`root=`
  settles it), and messages name the project by its folder rather than dumping your path
- **strictly read-only.** The module parses OpenSpec's markdown, never runs the `openspec` CLI and
  never writes into your project — ticking a box in `tasks.md` stays the job of whatever module
  you edit code with. Only the folders in `openspec_roots` can be read at all, the archive folder
  is finished work and never backlog, and a change that declares `skip_specs` still gets its
  task list

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
| `project-board_add_cards` | A whole batch in one call — the shape to use when you break a spec or a project down: one write, one push, and a per-item report of what landed and what was skipped |
| `project-board_edit_card` | Change any field; empty values clear description / assignee / labels / due |
| `project-board_move_card` | Move to another column, optionally above a specific card (use it whenever work progresses) |
| `project-board_reorder_column` | Set the top-to-bottom order of a column, i.e. prioritize the work |
| `project-board_duplicate_card` | Copy a card, keeping its fields (never its comments) |
| `project-board_delete_card` | Remove a card and its comments |
| `project-board_add_comment` / `project-board_delete_comment` | Leave progress notes and questions on a card |
| `project-board_add_column` / `project-board_update_column` / `project-board_delete_column` | Shape a board's workflow: rename, WIP limits, done flags, reordering, and where the cards of a deleted column go |
| `project-board_list_prompt_actions` | The user's own play buttons on this board, with the templates — so you know what "I played that card" is about to ask for |
| `project-board_add_prompt_action` / `project-board_edit_prompt_action` / `project-board_delete_prompt_action` | Set those buttons up: label, template, which columns it shows on, and what a press does besides filling the chat input. Pressing one stays a human gesture — no tool can press it |
| `project-board_list_prompt_action_examples` | The shipped templates, so you can offer a starting point instead of a blank page |
| `project-board_import_openspec` | Turn `openspec/changes/<change>/` into cards (requirements with their scenarios, or the `tasks.md` checklist). Read-only, idempotent, and `dry_run=true` says the numbers first |
| `project-board_read_openspec` | The changes in flight: what is specified, how much is on the board already, and which requirements have no scenario yet |

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
3. Enable it: `/module openlumara-project-board` (then `/restart`), or tick it in the WebUI
   settings. A module's name is the folder it lives in, so if you rename the folder, use that
   name - the panel and its API follow the folder name automatically.

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
| `enable_prompt_actions` | `true` | The play buttons and the action editor. Off hides them and nothing writes them either - the panel's save route and the AI's tools both refuse, and your templates stay on the board. Even on, a press only fills the chat input — nothing is sent for you |
| `spec_action_prompt` | *(the OpenSpec-shaped prompt)* | What the process-spec button fills into the chat, with the pasted spec in it. Placeholders `{title}`, `{spec}`, `{board}`, `{backlog}`, `{date}`. Rewrite it if your project plans differently |
| `enable_openspec` | `true` | Read `openspec/changes/<change>/` and turn it into cards. The board never writes to your project and never runs the openspec CLI |
| `openspec_roots` | *(empty)* | The folders your OpenSpec projects live in: the repository root that contains `openspec/`, or an `openspec` folder itself — same shape as the coder module's `sandbox_paths`. Nothing outside this list is ever read, so the feature sleeps until you point it at a repo - and until then the panel says so out loud and names this setting |
| `openspec_default_unit` | `requirements` | What one card stands for: one testable story per requirement (its scenarios become the acceptance criteria), one card per `tasks.md` checkbox, or both |
| `openspec_max_cards` | `60` | How many cards one import may create, so a monster spec cannot flood the backlog. Cards already on the board are refreshed regardless |
| `enable_webui_extension` | `true` | Auto-added by the framework; toggles the board panel and its API routes |

## Files

```
module.py                                       <- module: tools, commands, prompt, /api/ext routes, openspec reader
webui/templates/chat/index.html                 <- the board panel (below_header slot: it takes the chat panel over)
webui/templates/chat/header.html                <- chat header toggle button (right slot)
webui/templates/modals/project_board_card.html  <- card dialog (fields, comments, play buttons)
webui/templates/modals/project_board_actions.html <- prompt action editor (your templates + the examples)
webui/templates/modals/project_board_spec.html  <- process spec dialog (paste a spec, preview, fill the chat)
webui/assets/js/project_board.js                <- panel logic (Alpine store "projectBoard"), boards, drag & drop, keyboard
webui/assets/css/project_board.css              <- board + dialog styles (everything is namespaced under .pb-)
tests/conftest.py                               <- self-contained fixtures (tmp data folder, fake manager)
tests/test_board.py                             <- tool surface, routes, templates, openspec reader, stats and prompts
tests/fixtures/openspec/                        <- a real-shaped openspec project the reader is tested against
pytest.ini                                      <- so the suite runs on its own, wherever the repo's own pytest config lives
LICENSE                                         <- GPL-3.0-or-later
README.md                                       <- this file
.gitignore                                      <- python/editor/OS artifacts
```

Run the suite with `pytest user_modules/openlumara-project-board/tests`. The module ships its own
`pytest.ini`, so that works from anywhere and needs nothing from openlumara's own pytest config.

Board data lives in OpenLumara's data folder, as plain JSON you can eyeball or hand-edit:

```
<data>/project_board_boards.json    <- one entry per board, with the active one flagged
<data>/project_board_columns.json   <- every board's columns; "board" says which one, "order" where it sits
<data>/project_board_cards.json     <- every board's cards; "board" and "column" say where a card lives,
                                       "source" what it was imported from (empty for cards you typed)
<data>/project_board_actions.json   <- the prompt actions; "board" and "column" scope each button
```

## Notes

- auto-refresh is a preference of the panel (status bar, kept in `localStorage`), not a module
  setting. It used to be the `refresh_interval` module setting; a leftover line for it in
  `config.yml` is ignored.
- **A play button never runs the agent.** It renders the template, fills the chat input and
  focuses it; you read it and press enter. That is also why a tool cannot press one — setting the
  buttons up is the AI's job, launching work is yours. With `keep_chat_input` off the board is
  full-screen, so a press reveals the input bar for as long as the prompt sits there.
- **Prompt templates are plain text.** `{placeholder}` substitution, nothing else: no `str.format`,
  no evaluation, so a template cannot reach into anything and unknown `{braces}` are left alone.
- **OpenSpec reading is read-only by design**, and limited to `openspec_roots`. Writing
  `tasks.md` stays with your code tools, which is also why the board can read a change whether or
  not the openspec CLI is installed.
- An imported card remembers its `source`, which is what makes re-importing a refresh instead of a
  duplicate. Delete the card and the next import creates it again.
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
  adopted by the first board, a prompt action whose column vanished goes back to working board-wide,
  and a board list with nothing flagged active falls back to the first board.
- Storage from before boards existed (one set of cards and columns, no `board` field) is migrated
  on the first start after updating: it becomes the `default_board_name` board with its columns in
  the order they were in, and nothing is renamed or dropped.

## License

Copyright (C) 2026 theunknownmuncher <theunknownmuncher@protonmail.com>

GPL-3.0-or-later (see [LICENSE](LICENSE)).
