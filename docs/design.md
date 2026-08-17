# Design — AgentFactory Studio

Design specification for the web dashboard ("Studio") that manages the AgentFactory platform: sign-up/login, agent creation, tools, skills, MCP, memory, models, profile/themes, and a live terminal.

---

## 1. Design Principles

1. **The factory metaphor, made visible.** A user should always feel they are *building and operating* agents — assembly, wiring, and control are explicit, never hidden.
2. **Configuration before code, code when needed.** 90% of actions are forms, toggles, and drag-and-drop wiring. Raw YAML/JSON editors are available as an "advanced" view, never the default.
3. **Every agent is inspectable.** Runs show live streams, tool calls, costs, verification results, and memory writes — no black boxes.
4. **Safety is a first-class control.** Human-in-the-loop, destructive-action gates, and budgets are prominent, not buried in settings.
5. **One shell, many themes.** The UI is fully themeable (light/dark/custom palettes, font choices) and respects user settings everywhere.

---

## 2. Information Architecture

```
┌─ App shell (sidebar + topbar) ─────────────────────────────────┐
│  Dashboard        — overview: agents, runs, spend, activity    │
│  Agents           — list → editor → run console                │
│  Tools            — built-in catalog | custom | marketplace    │
│  Skills           — built-in | install | create | marketplace  │
│  MCP Servers      — built-in/curated | custom config           │
│  Memory           — per-agent browser, export/import, clear    │
│  Models           — provider connections + custom endpoints    │
│  Approvals        — human-in-the-loop inbox (proposals)        │
│  Terminal         — workspace-scoped shell                     │
│  Settings         — profile | workspace | themes & fonts       │
└────────────────────────────────────────────────────────────────┘
```

Top bar: workspace switcher, environment status (server/worker), daily budget indicator, user menu.

---

## 3. Page-by-Page Design

### 3.1 Auth (`/auth`)
- Split-screen layout: left = product story + live demo of an agent run; right = card with sign-in / sign-up tabs.
- Email + password, plus Google/GitHub OAuth buttons.
- On sign-up: create default workspace ("My Workspace") and one starter agent (e.g., `research` or `excel-engineer` persona) so the first screen after login is alive, not empty.
- Errors inline; password strength meter; "forgot password" (email token) flow.

### 3.2 Dashboard (`/`)
- **Stat row**: agents, runs today, tokens, est. spend vs budget.
- **Recent runs** list (live progress bars while running, stream preview).
- **Pending approvals** widget with approve/reject inline.
- **Quick start** panel: "Create agent", "Connect a model", "Install a skill", "Open terminal".
- Empty state → onboarding checklist (connect API key → create agent → run first task).

### 3.3 Agents
- **List**: cards/table with name, rank/role, model, budget, HITL mode, last run, status badge (Idle/Running/Approval needed/Error).
- **Editor** (two-column): left = form (name, role description, system instructions, temperature, budget, max iterations, HITL toggle, model picker, tool/skill/MCP multi-select with search); right = live preview of the generated system prompt + full tool manifest.
- **Run console** (from agent card "Run"): task input → streaming transcript (user/assistant/tool-call blocks), live token/cost meter, tool-call timeline, verification report, stop button, "save as proposal" for HITL-gated agents.

### 3.4 Tools
- Tabs: **Built-in** (catalog grouped by category, safety badge per tool), **Custom** (list of user tools), **Marketplace**.
- Custom tool editor: name, description, category, safety level, tags, cost, and Python source (`@tool` decorated) with syntax highlighting + **Validate** button (compile + lint + dry-run with sample args).
- Safety badges: SAFE (green), MODIFIED (amber), DESTRUCTIVE (red) — always visible; destructive tools require an extra confirm and show a warning banner.

### 3.5 Skills
- **Built-in**: curated skill cards (icon, name, description, tool count, category, tags) → **Install**.
- **Create**: step wizard — 1) metadata (name, description, category, tags), 2) tools (pick from registry or paste new `@tool` code), 3) prompt prefix, 4) dependencies, 5) review → Save.
- **Marketplace**: browse/search, version + author metadata, install button → confirm installs into workspace.
- Installed skills are assignable to agents from the agent editor.

### 3.6 MCP Servers
- **Curated/Marketplace**: server cards (name, transport, description, enabled) → Connect (downloads/registers config).
- **Custom**: form for name, transport (`stdio` | `SSE`), command + args (stdio) or URL (SSE), env allowlist (key names only — values never displayed), timeout, **Test connection** → lists discovered tools with an enable checkbox per tool.
- Trust banner: "MCP servers can execute commands — only connect servers you trust."

### 3.7 Memory
- **Browser**: pick agent → two views: *Facts* (key/value table with type + confidence, add/edit/delete inline) and *History* (chronological transcript, filterable, paginated).
- **Export**: one-click JSON download of facts + history for the selected agent (or whole workspace).
- **Import**: paste/upload JSON → preview diff → confirm merge (new keys added, conflicts shown).
- **Clear**: destructive action with typed confirmation.

### 3.8 Models
- **Provider connections**: cards for Gemini, OpenAI, Anthropic — "Connect API key" (paste key → stored as secret ref), status dot (configured/tested), test-call button.
- **Custom model**: form for name, base URL, API key, model id, `openai-compatible` protocol — test with a 1-token call; result shown inline.
- Model picker in agent editor lists all connected models in failover order (drag to reorder).

### 3.9 Approvals (human-in-the-loop inbox)
- Card per pending proposal: feature name, plan excerpt, blueprint JSON viewer, source agent, time; buttons **Approve / Modify / Reject** with optional comment.
- History tab: all decisions with audit trail.
- Global + per-agent HITL toggle lives in Settings and agent editor.

### 3.10 Terminal
- Full-height xterm.js pane inside the app shell; workspace-scoped cwd; session banner shows sandbox root; reconnect on drop; **destructive command warning** (e.g., `rm -rf`, `git push`) asks for confirmation once per session toggle.

### 3.11 Settings
- **Profile**: name, email, avatar, change password, OAuth links.
- **Workspace**: name/slug, member list + roles (owner/admin/member), danger zone (delete workspace).
- **Themes & fonts**: theme picker (Light / Dark / custom palette editor with live preview), font picker (UI font + mono font), density (comfortable/compact); persists per user.

---

## 4. Design System

### 4.1 Tokens (CSS variables, following the template's `src/index.css` conventions)
```
--background / --foreground          # app canvas + text
--card / --card-foreground
--primary / --primary-foreground    # actions, accent
--secondary / --secondary-foreground
--muted / --muted-foreground
--accent / --accent-foreground
--destructive / --destructive-foreground
--border / --input / --ring
--radius (sm / md / lg)
--font-sans / --font-mono
--success / --warning               # verification + safety states
```
Dark mode: `class="dark"` on root with a token override block — no hardcoded colors in components.

### 4.2 Typography
- UI font: Inter (default), alternatives (system, Geist, Open Sans) via settings.
- Mono font: JetBrains Mono (default) for code, prompts, terminal, transcripts.
- Type scale: 12/14/16/20/24/30 px; headings use tight tracking; numeric data in tabular-nums.

### 4.3 Components (shadcn/ui primitives)
`Button, Input, Select, Tabs, Card, Badge, Switch, Dialog, Sheet, Table, DropdownMenu, Tooltip, Toast, Skeleton, Progress, Command (search), ResizablePanel (agent editor), ScrollArea (console)`. Custom: `SafetyBadge`, `RunStream`, `ToolCallBlock`, `ModelPicker`, `ThemeEditor`, `JsonViewer`, `KeyValueTable`.

### 4.4 Layout & Spacing
- Sidebar 240 px (collapsible to icons), content max-width 1200 px, 16 px base spacing grid.
- Agent editor uses resizable split panes; run console is a full-height scroll area with sticky stats header.
- Responsive: sidebar → bottom nav under 900 px; tables → cards under 640 px.

### 4.5 Motion & States
- Framer Motion: 150–250 ms fades/slides for panes and dialogs; progress shimmer for running tasks; skeleton loaders; streaming text types in from the SSE buffer (no animation on the text itself — keep latency honest).

### 4.6 Accessibility
- WCAG 2.1 AA contrast in all themes (auto-check in theme editor), full keyboard navigation, focus rings from `--ring`, aria labels on icon buttons, reduced-motion respect.

---

## 5. Key Interaction Flows

### 5.1 Create an Agent (wizard, 3 steps)
1. **Basics** — name, role/rank, description, system instructions (template snippets offered).
2. **Capabilities** — searchable multi-selects: tools, skills, MCP servers; budget slider; temperature; max iterations; HITL mode toggle with explanation.
3. **Review** — generated prompt preview + tool manifest; Save → agent card appears in list with a "Try it" run button.

### 5.2 Run with HITL off
Task input → SSE stream → live transcript → verification report → memory writes shown as they happen → final summary card with cost + tokens + duration.

### 5.3 Run with HITL on
Task input → "Proposal created" → routed to Approvals inbox (and Discord/Gmail if configured) → on Approve, run starts automatically (worker) → same stream as above; on Reject/Modify, feedback shown in the console.

### 5.4 Install a Custom Tool
Open Tools → Custom → New → paste `@tool` code → **Validate** (compile + schema render) → choose safety level → Save → appears in agent editor picker.

---

## 6. API & Error Conventions

- REST JSON; errors as `{ "error": { "code", "message", "details?" } }` with appropriate HTTP status; field-level validation errors keyed by field.
- Streaming: SSE events `run.start | token | tool_call | tool_result | verify | memory | cost | run.end | error` with monotonic sequence ids.
- WebSocket terminal: binary PTY frames + JSON control frames (resize, ping/pong).
- Idempotency: `Idempotency-Key` header on agent run/proposal creation.

---

## 7. Out of Scope for v1 UI

- Mobile native apps (responsive web only).
- Drag-and-drop agent graph canvas (advanced wiring via lists; visual canvas is a v2 exploration).
- Multi-tenant billing/quotas (per-workspace budgets only in v1).
