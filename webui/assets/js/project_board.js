/* project-board -- Copyright (C) 2026 theunknownmuncher <theunknownmuncher@protonmail.com>
 * SPDX-License-Identifier: GPL-3.0-or-later
 * See the LICENSE file for the full GPL-3.0 text.
 */
/* -- AI-GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-26) status:reviewed harness:openlumara --
   Kanban / scrum board panel: takes over the chat panel, drag & drop, filtering and the
   card + column editors. Talks to the module's /api/ext routes and to its
   {type: "project_board"} websocket broadcasts. */

/* the interval auto-refresh starts out with, and what the panel falls back to when the
   number in the status bar is not usable. board changes are pushed over the websocket, so
   the timer is the safety net for anything the push missed - and it is optional */
/* -- AI GENERATED CODE (unknown model) :: (2026-11-12) status:pending-review harness:openlumara --
   /api/ext is namespaced by the folder name the module was installed under, which is not
   something the repo can know (upstream ships it as openlumara-project-board, but any folder
   name works). this file is served from /ext-assets/<that name>/js/, so ask it. */
const PB_API = (() => {
    const here = document.currentScript || document.querySelector("script[src*='/js/project_board.js']");
    const served_from = /\/ext-assets\/([^/]+)\//.exec(here ? here.src : "");
    return `/api/ext/${served_from ? served_from[1] : "openlumara-project-board"}/`;
})();

const PB_REFRESH_SECONDS = 5;

const PROJECT_BOARD = {
    open: localStorage.getItem("pb.open") === "true",
    loading: false,
    saving: false,
    loaded: false,
    error: "",
    notice: "",
    refreshedAt: null,

    columns: [],
    cards: [],
    stats: null,
    options: { types: [], priorities: [], placeholders: [], spec_placeholders: [], openspec_units: [] },
    settings: { keep_chat_input: true, enable_prompt_actions: true, openspec: { ready: false } },

    // prompt actions: play buttons whose prompts the user wrote. a press only fills the chat
    // input, so nothing here can start the agent by accident
    actions: [],
    examples: [],
    actionEditor: null,        // { id: null | "AB12CD" } while the action dialog is open
    actionForm: {},
    actionExample: "",
    openMenu: "",              // card id whose action menu is open
    copied: "",                // what was copied last, so the panel can say so briefly

    // the process-spec dialog: paste a spec in, get the templated prompt into the chat
    specDraft: { title: "", spec: "", preview: "", showPreview: false, busy: false },

    // openspec: the changes in flight, read from the project when the strip is opened
    showOpenspec: false,
    openspecLoading: false,
    openspecNote: "",
    openspec: { ready: false, enabled: true, roots: [], changes: [], problem: "",
                unit: "requirements", as_epic: true },

    boards: [],                // every board, with its counts
    activeBoardId: "",
    showBoardSettings: false,
    boardDraft: { name: "", description: "" },
    creatingBoard: false,
    newBoardName: "",
    newBoardDescription: "",
    copyLayout: true,

    query: "",
    filterAssignee: "",
    filterLabel: "",
    filterPriority: "",
    filterType: "",
    hideDone: false,
    sort: localStorage.getItem("pb.sort") || "manual",
    showHelp: false,

    quickAdd: null,          // { column, text } while the inline composer is open
    renaming: null,          // column id whose name is being edited inline
    renameValue: "",
    editingColumn: null,     // column id whose wip / done editor is open
    columnForm: { wip_limit: 0, done: false },
    newColumn: { name: "", adding: false },

    // one card being edited in the card modal, plus its form and comments
    editing: null,
    form: {},
    comments: [],
    commentText: "",

    drag: { card: null, column: null, target: null, index: -1, kind: "" },
    columnDrag: null,

    // auto-refresh is optional and tuned from the status bar; the choice is kept per browser
    autoRefresh: localStorage.getItem("pb.autorefresh") !== "0",
    refreshSecondsText: localStorage.getItem("pb.refresh-seconds") || String(PB_REFRESH_SECONDS),

    _timer: null,
    _timerSeconds: 0,          // the interval the running timer was started with
    _watchingTab: false,
    _chatScroll: null,         // where the chat was scrolled to while the board covers it
    _peekTimer: null,          // while a prompt sits in the chat input, the input stays visible
    _chain: Promise.resolve(),

    /* ------------------------------------------------------------------
       panel visibility: the board replaces the chat panel, so opening it
       hides the message history (and optionally the chat input bar).
       ------------------------------------------------------------------ */

    toggle() {
        this.open ? this.hide() : this.show();
    },

    async show() {
        this.open = true;
        localStorage.setItem("pb.open", "true");

        // the board covers the chat, it does not reset it: remember where the chat was
        // scrolled to while it is still laid out, hide() puts it back
        this.captureChatScroll();

        this.applyBodyClass();

        // opening the panel always pulls the current board, and the timer starts with it
        await this.refresh(true);
        this.startPolling();
    },

    hide() {
        this.open = false;
        localStorage.setItem("pb.open", "false");
        this.applyBodyClass();
        this.stopPolling();
        this.hideInputPeek();

        // #messages is laid out again from here, so the reading position goes back to the
        // chat once the browser has had a frame to remeasure the turns
        this.restoreChatScroll();
    },

    applyBodyClass() {
        document.body.classList.toggle("pb-board-open", this.open);
        // keep_chat_input off: the board is full-screen, so the input goes too - unless a play
        // button just filled it with a prompt, which is what pb-input-peek is for
        document.body.classList.toggle("pb-hide-input", this.open && !this.settings.keep_chat_input);
    },

    /* ------------------------------------------------------------------
       chat scroll handoff. opening the board takes #messages out of the
       layout, and a display:none container has no scroll position left to
       come back to, so where the chat was is remembered here and restored
       when the board is closed again.
       ------------------------------------------------------------------ */

    captureChatScroll() {
        const el = document.getElementById("messages");

        this._chatScroll = null;
        if (!el) return;

        const containerTop = el.getBoundingClientRect().top;
        const anchor = [...el.querySelectorAll("[data-turn-index]")]
            .find(turn => turn.getBoundingClientRect().bottom > containerTop);

        this._chatScroll = {
            // switching to another chat while the board is open means there is nothing of
            // yours to put back, the new chat is where the chat itself left it
            chat: Alpine.store("chat") ? Alpine.store("chat").selectedChat : null,

            // the chat's own follow-the-bottom tolerance: sitting there means you want the
            // newest message, not the exact pixel you were at
            atBottom: el.scrollHeight - el.scrollTop - el.clientHeight < 50,

            top: el.scrollTop,

            // anchored on the turn at the top of the view rather than on a bare pixel
            // offset, because turns are lazily mounted and an unmounted one only stands as
            // tall as the height the chat captured for it - so pixel offsets drift while
            // the turn itself does not
            turn: anchor ? Number(anchor.dataset.turnIndex) : null,
            gap: anchor ? anchor.getBoundingClientRect().top - containerTop : 0,
        };
    },

    async restoreChatScroll() {
        const saved = this._chatScroll;
        this._chatScroll = null;

        const chat = Alpine.store("chat");
        const switched = Boolean(saved && saved.chat && chat && chat.selectedChat !== saved.chat);

        // with no anchor - the board was already open when the page loaded - or with the
        // chat switched underneath the board, the chat tried to place itself while
        // #messages had no layout at all and would come back sitting at its top. a chat you
        // have just opened belongs at its newest message, so that is where it is handed back
        if (!saved || switched || saved.atBottom) return this._placeChatScroll({ bottom: true });

        return this._placeChatScroll(saved);
    },

    async _placeChatScroll(where) {
        const ui = Alpine.store("ui");

        // same shape as the chat's own scrollToTurn: heights settle over several frames as
        // turns are mounted back in, markdown renders and images arrive, so the position is
        // re-applied until it stops moving instead of being guessed once
        let lastTop = -1;
        let lastHeight = -1;

        for (let attempt = 0; attempt < 24; attempt++) {
            const el = document.getElementById("messages");
            if (!el) return;

            if (ui) ui.updateMounts();
            await Alpine.nextTick();

            if (where.bottom) {
                el.scrollTo({ top: el.scrollHeight, behavior: "instant" });
            } else {
                const turn = where.turn === null ? null : el.querySelector(`[data-turn-index="${where.turn}"]`);

                if (turn) {
                    const drift = turn.getBoundingClientRect().top - el.getBoundingClientRect().top - where.gap;
                    el.scrollTo({ top: el.scrollTop + drift, behavior: "instant" });
                } else {
                    el.scrollTo({ top: where.top, behavior: "instant" });
                }
            }

            await new Promise(resolve => requestAnimationFrame(resolve));

            if (el.scrollTop === lastTop && el.scrollHeight === lastHeight) return;

            lastTop = el.scrollTop;
            lastHeight = el.scrollHeight;
        }
    },

    async mount() {
        this.applyBodyClass();

        // always fetched: the chat header shows how many cards are waiting, and
        // opening the board then costs nothing extra
        await this.load();

        if (this.open) this.startPolling();

        // coming back to the tab counts as opening the board again, so the board is
        // never the stale one you left behind
        if (!this._watchingTab) {
            this._watchingTab = true;

            document.addEventListener("visibilitychange", () => {
                if (!this.open || document.visibilityState !== "visible") return;

                this.load();
                this.startPolling();
            });
        }
    },

    /* while the board is on screen and auto-refresh is ticked, it reloads every
       refreshSeconds() so it is never the state you left behind. a hidden tab is left
       alone - browsers throttle its timers anyway, and the visibilitychange handler in
       mount() catches it up the moment it is looked at again. with auto-refresh unticked
       the board still reloads on open, on tab focus, on the r key and on every push. */
    startPolling() {
        this.stopPolling();
        if (!this.open || !this.autoRefresh) return;

        this._timerSeconds = this.refreshSeconds();
        this._timer = setInterval(() => {
            if (document.visibilityState === "visible") this.load();
        }, this._timerSeconds * 1000);
    },

    /* the seconds live in a text field, so they are parsed and clamped here instead of
       being trusted: anything silly you typed falls back to the default interval */
    refreshSeconds() {
        const seconds = parseInt(this.refreshSecondsText, 10);

        if (!Number.isFinite(seconds) || seconds < 1) return PB_REFRESH_SECONDS;

        return Math.min(seconds, 24 * 3600);
    },

    // one handler for the checkbox and for the seconds field: remember the choice and put
    // the timer into the state it describes, without waiting for a reopen
    applyRefreshPrefs() {
        const seconds = this.refreshSeconds();
        this.refreshSecondsText = String(seconds);

        localStorage.setItem("pb.autorefresh", this.autoRefresh ? "1" : "0");
        localStorage.setItem("pb.refresh-seconds", String(seconds));

        this.startPolling();
    },

    stopPolling() {
        if (this._timer !== null) clearInterval(this._timer);

        this._timer = null;
        this._timerSeconds = 0;
    },

    onBroadcast() {
        // the module pushes one of these whenever anything changed, including
        // changes made by the AI with its tools
        if (this.open) this.load();
    },

    flash(text) {
        this.notice = text;
        setTimeout(() => { if (this.notice === text) this.notice = ""; }, 2500);
    },

    /* ------------------------------------------------------------------
       loading
       ------------------------------------------------------------------ */

    async refresh(force = false) {
        if (force || !this.loaded) await this.load();
    },

    // one fetch at a time, but a refresh asked for while one is still in flight must
    // still see fresh data - so requests are chained instead of dropped
    load() {
        this._chain = this._chain.then(() => this._fetchBoard()).catch(() => {});
        return this._chain;
    },

    async _fetchBoard() {
        this.loading = true;
        this.error = "";

        try {
            const board = await simpleApiFetch(`${PB_API}board`);

            this.columns = board.columns || [];
            this.cards = board.cards || [];
            this.stats = board.stats || null;
            this.options = board.options || this.options;

            // the switcher: one entry per project board, with the active one marked
            this.boards = board.boards || [];
            this.activeBoardId = board.active ? board.active.id : "";
            if (!this.showBoardSettings) this.syncBoardDraft();

            // the play buttons of this board, and the placeholder cheat-sheet for the editor
            this.actions = board.actions || [];
            if (board.options) this.options = board.options;

            // a press's menu is about cards of the board it was opened on
            this.openMenu = "";

            // settings can change in the module settings dialog without a page reload
            if (board.settings) {
                this.settings = board.settings;
                this.openspec = Object.assign({}, this.openspec, board.settings.openspec || {});
                this.applyBodyClass();
            }

            this.loaded = true;
            this.refreshedAt = new Date();

            // a page that loads with the board already open (from localStorage) starts
            // its timer here, and a tab that is merely open stays on its existing phase
            if (this.open && this._timer === null) this.startPolling();
        } catch (e) {
            this.error = this.errorText(e);
        } finally {
            this.loading = false;
        }
    },

    errorText(e) {
        if (typeof e === "string") return e;
        if (e && typeof e === "object") return e.message || JSON.stringify(e);
        return String(e);
    },

    /* ------------------------------------------------------------------
       boards: one per project, the active one is what this panel shows
       ------------------------------------------------------------------ */

    activeBoard() {
        // the board the server says is active. activeBoardId follows the select box and
        // moves the moment something is picked, so it is not what the panel is showing yet
        return this.boards.find(board => board.active) || null;
    },

    activeBoardName() {
        const board = this.activeBoard();
        return board ? board.name : "Project board";
    },

    boardMeta() {
        const board = this.activeBoard();
        if (!board) return "";

        return `${board.cards} cards · ${board.columns} columns · ${board.points} points open`;
    },

    syncBoardDraft() {
        const board = this.activeBoard();
        this.boardDraft = board ? { name: board.name, description: board.description || "" } : { name: "", description: "" };
    },

    async switchBoard(id) {
        // x-model has already moved activeBoardId to the picked board, so the board that
        // is active right now comes from the list, not from activeBoardId
        const current = this.boards.find(board => board.active) || { id: this.activeBoardId };

        if (!id || current.id === id) {
            // picking the board you are on: put the select back where it belongs
            return this.load();
        }

        try {
            await simpleApiPost(`${PB_API}board/activate`, { id: id });
        } catch (e) {
            this.error = this.errorText(e);
        } finally {
            await this.load();
        }

        // labels and assignees belong to a board, so carrying a filter over from the
        // previous one usually just looks like an empty board
        this.clearFilters();
        this.flash(`board: ${this.activeBoardName()}`);
    },

    startNewBoard() {
        this.showBoardSettings = false;
        this.creatingBoard = true;
        this.newBoardName = "";
        this.newBoardDescription = "";
    },

    async createBoard() {
        const name = this.newBoardName.trim();
        if (!name) return (this.creatingBoard = false);

        try {
            await simpleApiPost(`${PB_API}board/create`, {
                name: name,
                description: this.newBoardDescription.trim(),
                like: this.copyLayout ? this.activeBoardId : null,
                activate: true,
            });

            this.creatingBoard = false;
            await this.load();
            this.clearFilters();
            this.flash(`created ${name}`);
        } catch (e) {
            this.error = this.errorText(e);
        }
    },

    toggleBoardSettings() {
        this.creatingBoard = false;
        this.showBoardSettings = !this.showBoardSettings;
        if (this.showBoardSettings) this.syncBoardDraft();
    },

    async saveBoard() {
        const board = this.activeBoard();
        if (!board) return;

        try {
            await simpleApiPost(`${PB_API}board/update`, {
                id: board.id,
                name: this.boardDraft.name.trim(),
                description: this.boardDraft.description,
            });

            await this.load();
            this.flash("board saved");
        } catch (e) {
            this.error = this.errorText(e);
        }
    },

    async deleteBoard() {
        const board = this.activeBoard();
        if (!board) return;

        if (this.boards.length < 2) return this.flash("that is your only board");

        const warning = `Delete the board "${board.name}"? Its ${board.cards} card(s) and `
            + `${board.columns} column(s) go with it. This cannot be undone.`;
        if (!confirm(warning)) return;

        try {
            await simpleApiPost(`${PB_API}board/delete`, { id: board.id, force: true });

            this.showBoardSettings = false;
            await this.load();
            this.clearFilters();
            this.flash(`deleted ${board.name}`);
        } catch (e) {
            this.error = this.errorText(e);
        }
    },

    /* ------------------------------------------------------------------
       derived board data
       ------------------------------------------------------------------ */

    filtersActive() {
        return Boolean(this.query.trim() || this.filterAssignee || this.filterLabel
            || this.filterPriority || this.filterType);
    },

    clearFilters() {
        this.query = "";
        this.filterAssignee = "";
        this.filterLabel = "";
        this.filterPriority = "";
        this.filterType = "";

        // the search box writes into the model with a debounce, so clearing only the
        // model would have the typed text come back a moment later
        const search = document.getElementById("pb-search");
        if (search) search.value = "";
    },

    matches(card) {
        if (this.filterAssignee && (card.assignee || "") !== this.filterAssignee) return false;
        if (this.filterPriority && card.priority !== this.filterPriority) return false;
        if (this.filterType && card.type !== this.filterType) return false;

        if (this.filterLabel) {
            const labels = card.labels || [];
            if (!labels.includes(this.filterLabel)) return false;
        }

        const query = this.query.trim().toLowerCase();
        if (query) {
            const haystack = [
                card.title,
                card.description,
                card.assignee,
                (card.labels || []).join(" "),
                (card.comments || []).map(comment => comment.text).join(" "),
            ].join(" ").toLowerCase();

            if (!haystack.includes(query)) return false;
        }

        return true;
    },

    sortCards(cards) {
        const urgency = this.options.priorities || [];
        const weight = card => {
            const index = urgency.indexOf(card.priority);
            return index === -1 ? urgency.length : index;
        };

        const list = [...cards];

        switch (this.sort) {
            case "priority":
                return list.sort((a, b) => weight(a) - weight(b) || a.order - b.order);
            case "points":
                return list.sort((a, b) => (b.points || 0) - (a.points || 0) || a.order - b.order);
            case "due":
                return list.sort((a, b) => (a.due || "9999").localeCompare(b.due || "9999") || a.order - b.order);
            case "added":
                return list.sort((a, b) => (b.created || "").localeCompare(a.created || ""));
            case "title":
                return list.sort((a, b) => (a.title || "").localeCompare(b.title || ""));
            default:
                return list.sort((a, b) => a.order - b.order);
        }
    },

    columnCards(columnId) {
        return this.sortCards(this.cards.filter(card => card.column === columnId));
    },

    visibleCards(columnId) {
        return this.columnCards(columnId).filter(card => this.matches(card));
    },

    shownColumns() {
        return this.columns.filter(column => !this.hideDone || !column.done);
    },

    visibleCount() {
        return this.columns.reduce((total, column) => total + this.visibleCards(column.id).length, 0);
    },

    columnPoints(columnId) {
        return this.visibleCards(columnId).reduce((total, card) => total + (card.points || 0), 0);
    },

    overWip(column) {
        const limit = parseInt(column.wip_limit || 0, 10);
        if (!limit) return false;

        const cards = this.filtersActive() ? this.visibleCards(column.id) : this.columnCards(column.id);
        return cards.length > limit;
    },

    cardById(id) {
        return this.cards.find(card => card.id === id) || null;
    },

    columnById(id) {
        return this.columns.find(column => column.id === id) || null;
    },

    columnIndex(columnId) {
        return this.columns.findIndex(column => column.id === columnId);
    },

    typeIcon(card) {
        return { epic: "◆", story: "●", task: "■", bug: "▲", chore: "✚" }[card.type] || "■";
    },

    dueLabel(card) {
        if (!card.due) return "";
        return card.due.substring(5);
    },

    initials(card) {
        const name = String(card.assignee || "").trim();
        if (!name) return "";
        return name.split(/\s+/).map(word => word[0]).join("").substring(0, 2).toUpperCase();
    },

    timeAgo(date) {
        if (!date) return "";
        const minutes = Math.round((Date.now() - new Date(date).getTime()) / 60000);
        if (isNaN(minutes)) return "";
        if (minutes < 1) return "just now";
        if (minutes < 60) return `${minutes} min ago`;
        const hours = Math.round(minutes / 60);
        if (hours < 24) return `${hours} h ago`;
        return `${Math.round(hours / 24)} d ago`;
    },

    /* ------------------------------------------------------------------
       drag & drop
       ------------------------------------------------------------------ */

    startCardDrag(event, card) {
        this.drag = { card: card.id, column: card.column, target: null, index: -1, kind: "card" };
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("text/plain", card.id);
    },

    endCardDrag() {
        this.drag = { card: null, column: null, target: null, index: -1, kind: "" };
    },

    startColumnDrag(event, column) {
        this.columnDrag = column.id;
        this.drag.kind = "column";
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("text/plain", column.id);
    },

    endColumnDrag() {
        this.columnDrag = null;
        this.drag = { card: null, column: null, target: null, index: -1, kind: "" };
    },

    // one dragover handler for the whole column: while dragging a column it marks
    // the column, while dragging a card it works out which gap of the list the
    // pointer is over so the drop line follows the cursor
    onDragOver(event, column) {
        if (this.drag.kind === "column") {
            if (this.columnDrag === column.id) return;

            event.preventDefault();
            event.dataTransfer.dropEffect = "move";
            this.drag.target = column.id;
            return;
        }

        if (this.drag.kind !== "card") return;

        event.preventDefault();
        event.dataTransfer.dropEffect = "move";

        const elements = event.currentTarget.querySelectorAll(".pb-card");
        let index = elements.length;

        for (let position = 0; position < elements.length; position++) {
            const box = elements[position].getBoundingClientRect();
            if (event.clientY < box.top + box.height / 2) {
                index = position;
                break;
            }
        }

        this.drag.target = column.id;
        this.drag.index = index;
    },

    showDropLine(columnId, index) {
        return this.drag.kind === "card" && this.drag.target === columnId && this.drag.index === index;
    },

    async drop(event, column) {
        event.preventDefault();

        // snapshot and clear first: the handler fires once per element it bubbles
        // through, and an awaited reload must not be able to act on stale state
        const { kind, card, target, index } = this.drag;
        const columnDrag = this.columnDrag;
        this.endCardDrag();
        this.endColumnDrag();

        if (kind === "card" && card && target === column.id) {
            // dropping above the dragged card's own slot means "stay where you are"
            const cards = this.visibleCards(column.id);
            let beforeId = null;

            for (const candidate of cards.slice(Math.max(index, 0))) {
                if (candidate.id !== card) { beforeId = candidate.id; break; }
            }

            await this.moveCard(card, column.id, beforeId);
        }
        else if (kind === "column" && columnDrag && target === column.id) {
            await this.moveColumnTo(columnDrag, this.columnIndex(column.id));
        }
    },

    /* ------------------------------------------------------------------
       keyboard
       ------------------------------------------------------------------ */

    shortcuts(event) {
        // alt+b also works while the board is hidden, so it stays reachable even
        // with the chat header (and its button) turned off in the webui settings
        if (event.altKey && !event.ctrlKey && !event.metaKey && event.key.toLowerCase() === "b") {
            event.preventDefault();
            return this.toggle();
        }

        // the rest only applies while the board is the visible panel, and never
        // while typing, while a dialog is open, or while a press is in flight
        if (!this.open || Alpine.store("ui").currentModal) return;

        const tag = (event.target.tagName || "").toLowerCase();
        if (tag === "input" || tag === "textarea" || tag === "select") {
            if (event.key === "Escape") event.target.blur();
            return;
        }
        if (event.altKey || event.ctrlKey || event.metaKey) return;

        // the letter keys below fire from a plain if-chain, one of which is awaited
        // (playAction), so the whole handler is async by nature
        return this._shortcuts(event);
    },

    async _shortcuts(event) {
        if (event.key === "Escape") {
            // escape backs out of an open strip first, and only then out of the board
            if (this.showBoardSettings) return (this.showBoardSettings = false);
            if (this.creatingBoard) return (this.creatingBoard = false);
            if (this.showOpenspec) return (this.showOpenspec = false);
            if (this.openMenu) return (this.openMenu = "");

            return this.hide();
        }

        if (event.key === "n") {
            event.preventDefault();
            this.openCreate();
        }
        else if (event.key === "N") {
            event.preventDefault();
            this.startNewBoard();
        }
        else if (event.key === "/") {
            event.preventDefault();
            const search = document.getElementById("pb-search");
            if (search) search.focus();
        }
        else if (event.key === "r") {
            this.refresh(true);
        }
        else if (event.key === "a") {
            event.preventDefault();
            this.openActions();
        }
        else if (event.key === "s") {
            event.preventDefault();
            this.openSpec();
        }
        else if (event.key === "c") {
            event.preventDefault();
            this.copyBrief();
        }
        else if (event.key === "p") {
            // play the first action that applies to the focused card. the prompt only ends up in
            // the chat input, so the key is as safe as clicking the button
            const card = this.focusedCard();
            if (!card) return;

            event.preventDefault();

            const actions = this.actionsFor(card);
            if (!actions.length) return this.flash("no prompt action applies to this card - press a to set some up");

            if (actions.length > 1 && event.shiftKey) return this.toggleMenu(card);

            await this.playAction(card, actions[0]);
        }
    },

    /* the card the keyboard is on, which is how p and alt+arrows know what you mean */
    focusedCard() {
        const element = document.activeElement;
        if (!element || !element.closest) return null;

        const card = element.closest(".pb-card");
        return card ? this.cardById(card.dataset.cardId) : null;
    },

    /* ------------------------------------------------------------------
       card actions
       ------------------------------------------------------------------ */

    async moveCard(cardId, columnId, beforeId = null) {
        try {
            const result = await simpleApiPost(`${PB_API}card/move`, {
                id: cardId,
                column: columnId,
                before_card: beforeId,
            });

            await this.load();

            if (result && result.wip_warning) this.flash(result.wip_warning);
        } catch (e) {
            this.error = this.errorText(e);
        }
    },

    async shiftColumn(card, direction) {
        const index = this.columnIndex(card.column);
        const target = this.columns[index + (direction === "next" ? 1 : -1)];
        if (!target) return;

        await this.moveCard(card.id, target.id, null);
    },

    // alt + up/down on a focused card: one slot up or down inside the column.
    // walking past either end hands the card to the neighbouring column instead
    // of wrapping around, which is what "keep going" means on a board.
    async nudge(card, direction) {
        const cards = this.visibleCards(card.column);
        const position = cards.findIndex(entry => entry.id === card.id);
        const offset = direction === "up" ? -1 : 1;

        if (position === -1 || position + offset < 0 || position + offset >= cards.length) {
            return this.shiftColumn(card, direction === "up" ? "previous" : "next");
        }

        const neighbour = cards[position + offset];
        const ids = cards.map(entry => entry.id).filter(id => id !== card.id);
        const at = ids.indexOf(neighbour.id);

        ids.splice(direction === "up" ? at : at + 1, 0, card.id);

        await this.reorder(card.column, ids);
    },

    async reorder(columnId, cardIds) {
        try {
            await simpleApiPost(`${PB_API}card/reorder`, { column: columnId, card_ids: cardIds });
            await this.load();
        } catch (e) {
            this.error = this.errorText(e);
        }
    },

    startQuickAdd(columnId) {
        this.quickAdd = { column: columnId, text: "" };
    },

    async commitQuickAdd() {
        if (!this.quickAdd) return;

        const title = this.quickAdd.text.trim();
        const columnId = this.quickAdd.column;
        if (!title) return (this.quickAdd = null);

        try {
            await simpleApiPost(`${PB_API}card/create`, { title: title, column: columnId });
            this.quickAdd = { column: columnId, text: "" };
            await this.load();
        } catch (e) {
            this.error = this.errorText(e);
        }
    },

    openCreate(column = null) {
        this.editing = { id: null };
        this.form = {
            title: "",
            description: "",
            type: "task",
            priority: "medium",
            column: column || (this.columns.find(entry => !entry.done) || this.columns[0] || {}).id || "",
            assignee: "",
            labels: "",
            points: 0,
            due: "",
            blocked: false,
        };
        this.error = "";
        Alpine.store("ui").openModal("project_board_card");
    },

    openEdit(card) {
        if (!card) return;

        this.editing = { id: card.id };
        this.form = {
            title: card.title || "",
            description: card.description || "",
            type: card.type || "task",
            priority: card.priority || "medium",
            column: card.column,
            assignee: card.assignee || "",
            labels: (card.labels || []).join(", "),
            points: card.points || 0,
            due: card.due || "",
            blocked: !!card.blocked,
        };
        this.comments = card.comments || [];
        this.commentText = "";
        this.error = "";
        Alpine.store("ui").openModal("project_board_card");
    },

    closeModal() {
        this.editing = null;
        this.form = {};
        Alpine.store("ui").closeModal();
    },

    labelsInForm() {
        return String(this.form.labels || "")
            .split(",")
            .map(label => label.trim().replace(/^#/, ""))
            .filter(label => label);
    },

    async saveCard() {
        if (this.saving) return;

        const title = String(this.form.title || "").trim();
        if (!title) return (this.error = "a card needs a title");

        this.saving = true;
        this.error = "";

        const payload = {
            title: title,
            description: this.form.description || "",
            type: this.form.type,
            priority: this.form.priority,
            assignee: this.form.assignee || "",
            labels: this.labelsInForm(),
            points: parseInt(this.form.points || 0, 10) || 0,
            due: this.form.due || "",
            blocked: !!this.form.blocked,
        };

        try {
            if (this.editing && this.editing.id) {
                const before = this.cardById(this.editing.id);

                await simpleApiPost(`${PB_API}card/update`, { ...payload, id: this.editing.id });

                // a column change goes through the move endpoint, which also keeps
                // the wip limit warnings coming from one place
                if (before && this.form.column !== before.column) {
                    await simpleApiPost(`${PB_API}card/move`, {
                        id: this.editing.id, column: this.form.column,
                    });
                }
            } else {
                await simpleApiPost(`${PB_API}card/create`, { ...payload, column: this.form.column });
            }

            await this.load();
            this.closeModal();
        } catch (e) {
            this.error = this.errorText(e);
        } finally {
            this.saving = false;
        }
    },

    async deleteCard(card) {
        if (!window.confirm(`Delete the card "${card.title}" and its comments?`)) return;

        try {
            await simpleApiPost(`${PB_API}card/delete`, { id: card.id });
            await this.load();

            if (this.editing && this.editing.id === card.id) this.closeModal();
        } catch (e) {
            this.error = this.errorText(e);
        }
    },

    async duplicateCard(card) {
        try {
            await simpleApiPost(`${PB_API}card/duplicate`, { id: card.id });
            await this.load();
            this.closeModal();
        } catch (e) {
            this.error = this.errorText(e);
        }
    },

    async addComment(card) {
        const text = this.commentText.trim();
        if (!text) return;

        try {
            await simpleApiPost(`${PB_API}comment/add`, { id: card.id, text: text });
            this.commentText = "";
            await this.load();
            this.editing = { id: card.id };
            this.comments = (this.cardById(card.id) || {}).comments || [];
        } catch (e) {
            this.error = this.errorText(e);
        }
    },

    async deleteComment(card, comment) {
        try {
            await simpleApiPost(`${PB_API}comment/delete`, { id: card.id, comment: comment.id });
            await this.load();
            this.comments = (this.cardById(card.id) || {}).comments || [];
        } catch (e) {
            this.error = this.errorText(e);
        }
    },

    /* ------------------------------------------------------------------
       prompt actions: the play buttons

       a press renders the action's template for that card on the server, puts the
       result in the chat input and focuses it. it never sends: the user always sees the
       prompt and presses enter themselves, which is why there is no "send immediately"
       option to fear. the action's own side effects (move the card, log the prompt on it)
       are applied at press time, so other tabs see the same thing.
       ------------------------------------------------------------------ */

    actionsEnabled() {
        return this.settings.enable_prompt_actions !== false;
    },

    actionsFor(card) {
        if (!this.actionsEnabled() || !card) return [];

        // no column on an action means the whole board, a column means that stage only - which
        // is how play means something different in review than it does in the backlog
        return this.actions.filter(action => !action.column || action.column === card.column);
    },

    primaryAction(card) {
        return this.actionsFor(card)[0] || null;
    },

    menuOpen(card) {
        return this.openMenu === card.id;
    },

    toggleMenu(card) {
        this.openMenu = this.openMenu === card.id ? "" : card.id;
    },

    async playAction(card, action) {
        if (!card || !action) return;

        this.openMenu = "";

        try {
            const rendered = await simpleApiPost("/api/ext/project-board/action/render", {
                action: action.id,
                card: card.id,
            });

            this.prefillChat(rendered.prompt);

            await simpleApiPost("/api/ext/project-board/action/launched", {
                action: action.id,
                card: card.id,
                prompt: rendered.prompt,
            });

            await this.load();
            this.flash(`"${rendered.name}" is in the chat input - enter sends it`);
        } catch (e) {
            this.error = this.errorText(e);
        }
    },

    async copyActionPrompt(card, action) {
        if (!card || !action) return;

        this.openMenu = "";

        try {
            const rendered = await simpleApiPost("/api/ext/project-board/action/render", {
                action: action.id,
                card: card.id,
            });

            await this.copyText(rendered.prompt, `prompt for ${card.id}`);
        } catch (e) {
            this.error = this.errorText(e);
        }
    },

    /* the whole point of a press is that the prompt lands where you can still edit it, so
       with keep_chat_input off (board full-screen, input bar hidden) the bar is revealed for
       the moment - and goes back once the prompt has been sent or cleared */
    prefillChat(text) {
        const chat = Alpine.store("chat");
        if (chat) chat.user_input = text;

        this.revealInput();

        setTimeout(() => {
            const el = document.getElementById("user-input");
            if (!el) return;

            el.focus();
            // the autosize library only reacts to real input events, and a prompt that is
            // twelve lines long wants a twelve line box
            el.dispatchEvent(new Event("input", { bubbles: true }));
            el.selectionStart = el.selectionEnd = String(el.value).length;
        }, 30);
    },

    revealInput() {
        document.body.classList.add("pb-input-peek");

        if (this._peekTimer !== null) clearInterval(this._peekTimer);
        this._peekTimer = setInterval(() => {
            const chat = Alpine.store("chat");
            if (!this.open || !chat || !String(chat.user_input || "").trim()) this.hideInputPeek();
        }, 400);
    },

    hideInputPeek() {
        if (this._peekTimer !== null) {
            clearInterval(this._peekTimer);
            this._peekTimer = null;
        }

        document.body.classList.remove("pb-input-peek");
    },

    /* clipboard, with a fallback: /api and the panel are usually served over plain http on a
       LAN address, where navigator.clipboard does not exist at all */
    async copyText(text, label) {
        let copied = false;

        try {
            if (navigator.clipboard && window.isSecureContext) {
                await navigator.clipboard.writeText(text);
                copied = true;
            }
        } catch (e) {
            copied = false;
        }

        if (!copied) {
            const area = document.createElement("textarea");
            area.value = text;
            area.setAttribute("readonly", "");
            area.style.position = "fixed";
            area.style.top = "-1000px";
            document.body.appendChild(area);
            area.select();

            try {
                copied = document.execCommand("copy");
            } catch (e) {
                copied = false;
            }

            area.remove();
        }

        if (!copied) return (this.error = "your browser would not let me copy - select and copy it yourself");

        this.copied = label || "copied";
        setTimeout(() => { if (this.copied === (label || "copied")) this.copied = ""; }, 2500);
    },

    /* the visible cards as a numbered list, which is the shape a session brief or a "work
       through these in order" message wants. filters are honoured, so a filtered board copies
       the slice you are looking at rather than the whole project */
    briefText() {
        const lines = [];
        let index = 0;

        for (const column of this.shownColumns()) {
            const cards = this.visibleCards(column.id);
            if (!cards.length) continue;

            lines.push(`## ${column.name}`);

            for (const card of cards) {
                index += 1;

                const meta = [
                    card.points ? `${card.points}p` : "",
                    card.priority === "critical" || card.priority === "high" ? card.priority : "",
                    card.blocked ? "blocked" : "",
                    card.due ? `due ${card.due}` : "",
                ].filter(Boolean).join(", ");

                lines.push(`${index}. [${card.id}] ${card.title}${meta ? ` (${meta})` : ""}`);
            }

            lines.push("");
        }

        return lines.join("\n").trim();
    },

    async copyBrief() {
        const text = this.briefText();
        if (!text) return this.flash("nothing to copy - no card matches the filters");

        await this.copyText(text, `${text.split("\n").length} lines copied`);
    },

    /* ------------------------------------------------------------------
       the action editor: your templates, your buttons
       ------------------------------------------------------------------ */

    async loadExamples() {
        if (this.examples.length) return this.examples;

        try {
            const data = await simpleApiFetch("/api/ext/project-board/actions/examples");
            this.examples = data.examples || [];
        } catch (e) {
            this.error = this.errorText(e);
        }

        return this.examples;
    },

    blankAction() {
        return { name: "", template: "", column: "", move_to: "", log_as_comment: false, order: null };
    },

    async openActions() {
        if (!this.actionsEnabled()) return this.flash("prompt actions are switched off in the module settings");

        this.error = "";
        await this.loadExamples();

        this.actionEditor = { id: null };
        this.actionForm = this.blankAction();
        this.actionExample = "";

        Alpine.store("ui").openModal("project_board_actions");
    },

    editAction(action) {
        this.actionEditor = { id: action.id };
        this.actionForm = {
            name: action.name || "",
            template: action.template || "",
            column: action.column || "",
            move_to: action.move_to || "",
            log_as_comment: !!action.log_as_comment,
            order: null,
        };
        this.actionExample = "";
        this.error = "";
    },

    newAction() {
        this.actionEditor = { id: null };
        this.actionForm = this.blankAction();
        this.actionExample = "";
        this.error = "";
    },

    // picking an example fills the editor with it. nothing is saved until you press save, and
    // the example is never added to the board behind your back
    applyExample() {
        const example = this.examples.find(entry => entry.name === this.actionExample);
        if (!example) return;

        this.actionForm.name = example.name;
        this.actionForm.template = example.template;
        // an example suggests a stage; keep it only when this board actually has that column
        const column = this.columns.find(entry => entry.name.toLowerCase() === String(example.column || "").toLowerCase());
        this.actionForm.column = column ? column.id : "";
    },

    closeActions() {
        this.actionEditor = null;
        this.actionForm = {};
        Alpine.store("ui").closeModal();
    },

    async saveAction() {
        if (this.saving) return;

        const name = String(this.actionForm.name || "").trim();
        if (!name) return (this.error = "the button needs a name - that is what it says");

        const template = String(this.actionForm.template || "");
        if (!template.trim()) return (this.error = "the action needs a prompt template");

        this.saving = true;
        this.error = "";

        const payload = {
            name: name,
            template: template,
            column: this.actionForm.column || "",
            move_to: this.actionForm.move_to || "",
            log_as_comment: !!this.actionForm.log_as_comment,
        };

        try {
            if (this.actionEditor && this.actionEditor.id) {
                await simpleApiPost("/api/ext/project-board/action/save", {
                    ...payload, id: this.actionEditor.id,
                });
            } else {
                await simpleApiPost("/api/ext/project-board/action/save", payload);
            }

            await this.load();
            this.newAction();
            this.flash("prompt actions saved");
        } catch (e) {
            this.error = this.errorText(e);
        } finally {
            this.saving = false;
        }
    },

    async deleteAction(action) {
        if (!window.confirm(`Delete the prompt action "${action.name}"? The cards stay.`)) return;

        try {
            await simpleApiPost("/api/ext/project-board/action/delete", { id: action.id });
            await this.load();

            if (this.actionEditor && this.actionEditor.id === action.id) this.newAction();
        } catch (e) {
            this.error = this.errorText(e);
        }
    },

    // the module swaps the two actions' positions, which is how the one you press most ends up
    // in front without anyone having to renumber anything
    async shiftAction(action, direction) {
        const index = this.actions.indexOf(action);
        const target = index + (direction === "up" ? -1 : 1);
        if (index < 0 || target < 0 || target >= this.actions.length) return;

        try {
            await simpleApiPost("/api/ext/project-board/action/save", { id: action.id, order: target });
            await this.load();

            const moved = this.actions.find(entry => entry.id === action.id);
            if (moved && this.actionEditor && this.actionEditor.id === action.id) this.editAction(moved);
        } catch (e) {
            this.error = this.errorText(e);
        }
    },

    /* ------------------------------------------------------------------
       process spec: a spec goes in, stories come back on the board
       ------------------------------------------------------------------ */

    openSpec() {
        this.specDraft = { title: "", spec: "", preview: "", showPreview: false, busy: false };
        this.error = "";
        Alpine.store("ui").openModal("project_board_spec");
    },

    closeSpec() {
        Alpine.store("ui").closeModal();
    },

    // pasting a whole spec into a chat message is a thing to be deliberate about, so say what
    // a very large paste means instead of letting the model choke on it silently
    specWarning() {
        const chars = String(this.specDraft.spec || "").length;
        if (chars < 40000) return "";

        return `${chars.toLocaleString()} characters is a lot for one message. It often works better to put the spec in a file and tell your AI to read that file - then this button is only needed once.`;
    },

    specLandingNote() {
        /** why this board cannot land the stories the spec prompt asks for, in the dialog where
         *  the user is about to ask for them. an empty string means it can, so nothing is shown. */
        if (this.openspecReady()) return "";

        if (this.openspec.enabled === false) {
            return "openspec support is switched off in the module settings, so this prompt is on "
                + "its own: your AI writes the files, and nothing is landed on the board for you";
        }

        const settings = this.settings && this.settings.openspec ? this.settings.openspec : {};
        const problem = String(settings.problem || this.openspec.problem || "").trim();
        return "your AI can write the change, but this board cannot land its stories yet - "
            + (problem || "no openspec folder is configured in openspec_roots");
    },

    async renderSpec() {
        return simpleApiPost("/api/ext/project-board/spec/render", {
            title: this.specDraft.title,
            spec: this.specDraft.spec,
        });
    },

    async previewSpec() {
        if (this.specDraft.busy) return "";

        this.specDraft.busy = true;
        this.error = "";

        try {
            const data = await this.renderSpec();
            this.specDraft.preview = data.prompt;
            this.specDraft.showPreview = true;
            return data.prompt;
        } catch (e) {
            this.error = this.errorText(e);
            return "";
        } finally {
            this.specDraft.busy = false;
        }
    },

    async processSpec() {
        if (this.specDraft.busy) return;

        this.specDraft.busy = true;
        this.error = "";

        try {
            const data = await this.renderSpec();

            this.prefillChat(data.prompt);
            Alpine.store("ui").closeModal();
            this.flash(`spec for ${data.board} is in the chat input - enter sends it`);
        } catch (e) {
            this.error = this.errorText(e);
        } finally {
            this.specDraft.busy = false;
        }
    },

    /* ------------------------------------------------------------------
       openspec strip: what is specified, and what is on the board
       ------------------------------------------------------------------ */

    openspecOffered() {
        /** whether the strip is worth offering at all: on unless the module has openspec turned
         *  off entirely. It stays offered when no folder is configured yet, because that is the
         *  one state where the panel can actually tell you what to set - a hidden button leaves
         *  the whole feature undiscoverable on a fresh install. */
        return this.openspec.enabled !== false;
    },

    openspecReady() {
        return Boolean(this.openspec.enabled !== false && this.openspec.ready);
    },

    async toggleOpenspec() {
        this.showOpenspec = !this.showOpenspec;
        if (this.showOpenspec) await this.loadOpenspec();
    },

    async loadOpenspec() {
        this.openspecLoading = true;

        try {
            const data = await simpleApiFetch("/api/ext/project-board/openspec/changes");

            // the unit chosen in the strip is a browser preference, the rest comes from settings
            this.openspec = Object.assign({}, this.openspec, data, {
                unit: localStorage.getItem("pb.openspec-unit") || data.unit || "requirements",
            });
        } catch (e) {
            this.error = this.errorText(e);
        } finally {
            this.openspecLoading = false;
        }
    },

    setOpenspecUnit(unit) {
        localStorage.setItem("pb.openspec-unit", unit);
        this.openspec.unit = unit;
    },

    /* the dry run comes first so the confirmation can quote real numbers - importing is a
       write to the board, and a spec that turns into 40 cards deserves one click of doubt */
    async importChange(change) {
        if (this.openspecLoading) return;

        this.openspecLoading = true;
        this.error = "";

        const base = { change: change.id, root: change.root, unit: this.openspec.unit,
                       as_epic: !!this.openspec.as_epic };

        try {
            const plan = await simpleApiPost("/api/ext/project-board/openspec/import",
                                             { ...base, dry_run: true });

            if (!window.confirm(`${change.id} -> ${this.openspec.unit} cards\n\n${plan}

Add them to the board? The files are never written to.`)) return;

            const result = await simpleApiPost("/api/ext/project-board/openspec/import", base);

            this.openspecNote = String(result).split("\n")[0];
            await this.load();
            await this.loadOpenspec();
            this.flash(this.openspecNote);
        } catch (e) {
            this.error = this.errorText(e);
        } finally {
            this.openspecLoading = false;
        }
    },

    /* ------------------------------------------------------------------
       column actions
       ------------------------------------------------------------------ */

    startAddColumn() {
        this.newColumn = { name: "", adding: true };
    },

    async commitAddColumn() {
        const name = this.newColumn.name.trim();
        if (!name) return (this.newColumn.adding = false);

        try {
            await simpleApiPost(`${PB_API}column/create`, { name: name });
            this.newColumn = { name: "", adding: false };
            await this.load();
        } catch (e) {
            this.error = this.errorText(e);
        }
    },

    startRename(column) {
        this.renaming = column.id;
        this.renameValue = column.name;
    },

    async commitRename(column) {
        if (this.renaming !== column.id) return;
        this.renaming = null;

        const name = this.renameValue.trim();
        if (!name || name === column.name) return;

        try {
            await simpleApiPost(`${PB_API}column/update`, { id: column.id, name: name });
            await this.load();
        } catch (e) {
            this.error = this.errorText(e);
        }
    },

    toggleColumnEditor(column) {
        if (this.editingColumn === column.id) return (this.editingColumn = null);

        this.editingColumn = column.id;
        this.columnForm = { wip_limit: column.wip_limit || 0, done: !!column.done };
    },

    async saveColumn(column) {
        try {
            await simpleApiPost(`${PB_API}column/update`, {
                id: column.id,
                wip_limit: parseInt(this.columnForm.wip_limit || 0, 10) || 0,
                done: !!this.columnForm.done,
            });
            this.editingColumn = null;
            await this.load();
        } catch (e) {
            this.error = this.errorText(e);
        }
    },

    async moveColumnTo(columnId, position) {
        if (position < 0 || position >= this.columns.length) return;

        try {
            await simpleApiPost(`${PB_API}column/update`, { id: columnId, position: position });
            await this.load();
        } catch (e) {
            this.error = this.errorText(e);
        }
    },

    async shiftColumnOrder(column, direction) {
        await this.moveColumnTo(column.id, this.columnIndex(column.id) + (direction === "next" ? 1 : -1));
    },

    async deleteColumn(column) {
        const inside = this.columnCards(column.id).length;
        const extra = inside ? `${inside} card(s) will be moved to another column.` : "";
        if (!window.confirm(`Delete the column "${column.name}"? ${extra}`)) return;

        try {
            await simpleApiPost(`${PB_API}column/delete`, { id: column.id });
            await this.load();
        } catch (e) {
            this.error = this.errorText(e);
        }
    },

    /* ------------------------------------------------------------------
       pickers for the filter bar
       ------------------------------------------------------------------ */

    get assignees() {
        return Object.keys((this.stats && this.stats.assignees) || {}).sort();
    },

    get labels() {
        return Object.keys((this.stats && this.stats.labels) || {}).sort();
    },
};

document.addEventListener("alpine:init", () => {
    Alpine.store("projectBoard", PROJECT_BOARD);
});

// -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-26) harness:openlumara status:reviewed
// fresh Proxy per mount (see calendar.js for why x-data must never receive the
// store object directly)
function projectBoardComponent() {
    const target = {};
    const src = () => Alpine.store("projectBoard") || PROJECT_BOARD;

    return new Proxy(target, {
        get(t, key) {
            if (key === Symbol.unscopables) return undefined;
            if (key in t) return t[key];
            const value = src()[key];
            return typeof value === "function" ? value.bind(src()) : value;
        },
        set(t, key, value) {
            if (key in t) {
                t[key] = value;
                return true;
            }
            src()[key] = value;
            return true;
        },
        has(t, key) {
            return key in t || key in src();
        },
        ownKeys() {
            return [...new Set([...Reflect.ownKeys(target), ...Object.keys(src())])];
        },
        getOwnPropertyDescriptor(t, key) {
            if (key in t) return Reflect.getOwnPropertyDescriptor(t, key);
            if (key in src()) {
                return { value: src()[key], enumerable: true, configurable: true, writable: true };
            }
            return undefined;
        },
    });
}

// card modal: shares the board store, so the modal template just reads $store.projectBoard
function projectBoardCardModal() {
    return {
        get store() {
            return Alpine.store("projectBoard");
        },
        get card() {
            const store = this.store;
            return store && store.editing ? store.cardById(store.editing.id) : null;
        },
        timeAgo(date) {
            return this.store.timeAgo(date);
        },
    };
}

// swallow project_board broadcasts before the core handler sees them (it would
// only log "unknown websocket command"); everything else is forwarded untouched
(() => {
    const original = window.handleWebSocketMessage;

    window.handleWebSocketMessage = function (data) {
        if (data && data.type === "project_board") {
            try { Alpine.store("projectBoard").onBroadcast(data); } catch (e) {}
            return;
        }
        return original ? original(data) : undefined;
    };
})();
