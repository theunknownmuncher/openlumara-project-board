/* project-board -- Copyright (C) 2026 theunknownmuncher <theunknownmuncher@protonmail.com>
 * SPDX-License-Identifier: GPL-3.0-or-later
 * See the LICENSE file for the full GPL-3.0 text.
 */
/* -- AI-GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-26) status:reviewed harness:openlumara --
   Kanban / scrum board panel: takes over the chat panel, drag & drop, filtering and the
   card + column editors. Talks to /api/ext/project-board/ and to the module's
   {type: "project_board"} websocket broadcasts. */

/* the interval auto-refresh starts out with, and what the panel falls back to when the
   number in the status bar is not usable. board changes are pushed over the websocket, so
   the timer is the safety net for anything the push missed - and it is optional */
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
    options: { types: [], priorities: [] },
    settings: { keep_chat_input: true },

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
    },

    applyBodyClass() {
        document.body.classList.toggle("pb-board-open", this.open);
        // keep_chat_input off: the board is full-screen, so the input goes too
        document.body.classList.toggle("pb-hide-input", this.open && !this.settings.keep_chat_input);
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
            const board = await simpleApiFetch("/api/ext/project-board/board");

            this.columns = board.columns || [];
            this.cards = board.cards || [];
            this.stats = board.stats || null;
            this.options = board.options || this.options;

            // the switcher: one entry per project board, with the active one marked
            this.boards = board.boards || [];
            this.activeBoardId = board.active ? board.active.id : "";
            if (!this.showBoardSettings) this.syncBoardDraft();

            // settings can change in the module settings dialog without a page reload
            if (board.settings) {
                this.settings = board.settings;
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
            await simpleApiPost("/api/ext/project-board/board/activate", { id: id });
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
            await simpleApiPost("/api/ext/project-board/board/create", {
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
            await simpleApiPost("/api/ext/project-board/board/update", {
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
            await simpleApiPost("/api/ext/project-board/board/delete", { id: board.id, force: true });

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
        // while typing or while a dialog is open
        if (!this.open || Alpine.store("ui").currentModal) return;

        const tag = (event.target.tagName || "").toLowerCase();
        if (tag === "input" || tag === "textarea" || tag === "select") {
            if (event.key === "Escape") event.target.blur();
            return;
        }
        if (event.altKey || event.ctrlKey || event.metaKey) return;

        if (event.key === "Escape") {
            // escape backs out of an open strip first, and only then out of the board
            if (this.showBoardSettings) return (this.showBoardSettings = false);
            if (this.creatingBoard) return (this.creatingBoard = false);

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
    },

    /* ------------------------------------------------------------------
       card actions
       ------------------------------------------------------------------ */

    async moveCard(cardId, columnId, beforeId = null) {
        try {
            const result = await simpleApiPost("/api/ext/project-board/card/move", {
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
            await simpleApiPost("/api/ext/project-board/card/reorder", { column: columnId, card_ids: cardIds });
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
            await simpleApiPost("/api/ext/project-board/card/create", { title: title, column: columnId });
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

                await simpleApiPost("/api/ext/project-board/card/update", { ...payload, id: this.editing.id });

                // a column change goes through the move endpoint, which also keeps
                // the wip limit warnings coming from one place
                if (before && this.form.column !== before.column) {
                    await simpleApiPost("/api/ext/project-board/card/move", {
                        id: this.editing.id, column: this.form.column,
                    });
                }
            } else {
                await simpleApiPost("/api/ext/project-board/card/create", { ...payload, column: this.form.column });
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
            await simpleApiPost("/api/ext/project-board/card/delete", { id: card.id });
            await this.load();

            if (this.editing && this.editing.id === card.id) this.closeModal();
        } catch (e) {
            this.error = this.errorText(e);
        }
    },

    async duplicateCard(card) {
        try {
            await simpleApiPost("/api/ext/project-board/card/duplicate", { id: card.id });
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
            await simpleApiPost("/api/ext/project-board/comment/add", { id: card.id, text: text });
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
            await simpleApiPost("/api/ext/project-board/comment/delete", { id: card.id, comment: comment.id });
            await this.load();
            this.comments = (this.cardById(card.id) || {}).comments || [];
        } catch (e) {
            this.error = this.errorText(e);
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
            await simpleApiPost("/api/ext/project-board/column/create", { name: name });
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
            await simpleApiPost("/api/ext/project-board/column/update", { id: column.id, name: name });
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
            await simpleApiPost("/api/ext/project-board/column/update", {
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
            await simpleApiPost("/api/ext/project-board/column/update", { id: columnId, position: position });
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
            await simpleApiPost("/api/ext/project-board/column/delete", { id: column.id });
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
