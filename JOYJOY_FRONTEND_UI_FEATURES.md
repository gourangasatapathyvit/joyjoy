# Joyjoy Frontend UI — Feature Inventory

React 19 + Vite SPA built on **assistant-ui** (external-store mode). Auth-gated app shell with a left icon rail, main content, and optional right workspace dock.

---

## 1. App shell & navigation

| Feature | What it does |
|---|---|
| **Icon rail** | Narrow left nav: Home logo, Chat / MCP / Skills / Memory |
| **Drag-reorder tabs** | Drag rail icons to reorder; order saved per-user on the server |
| **Workspace toggle** | Opens/closes the global right-side workspace dock |
| **Settings** | Fixed bottom rail entry |
| **Connection status** | Connecting / Connected / Offline indicator |
| **Active thread restore** | Last conversation (and workspace) restored across reloads |
| **Prefs sync** | Appearance prefs mirrored local + server (cross-device) |

**Routes:** `/signin` · `/` & `/session/:id` (chat) · `/mcp` · `/skills` · `/memory` · `/settings`

---

## 2. Authentication

- **Sign in** (username / password)
- **Sign up** (create account)
- **Forgot password** → email reset code
- **Reset password** (6-digit code + new password)
- **Dev mode** helper (shows reset code when email isn’t configured)
- **RequireAuth** gate on all app routes
- Session cookie auth in prod; Vite proxy injects `x-user-id` in dev

---

## 3. Chat (core surface)

### Conversation management

- Conversation **sidebar** (collapsible, ~300px)
- **New chat**
- **Search** conversations
- **Pin / unpin** (Pinned vs Recent groups)
- **Rename** / **delete** (hover actions)
- Per-session URLs (`/session/:id`)
- Empty/new-chat welcome with centered composer

### Composer

- Multi-line message input
- **Send** / **Stop generating**
- **File attachments** + drag-and-drop dropzone
- Attachments uploaded into the agent **workspace**
- **Voice input / dictation** (mic)
- **Slash commands (`/`)** → enabled skills
- **Mentions (`@`)** → MCP tools (plain `@toolname` text)
- **Quote-to-reply** (select text → quote in composer)
- **Auto-approve tools** toggle (this chat only)
- **Context usage badge** (token ring: input / cached / output / reasoning / total)
- Run **success flash** after clean completion

### Model controls (composer area)

- **Model picker** (searchable, provider filter chips, grouped by provider)
- **Reasoning effort**: Off / Minimal / Low / Medium / High / Extra High (only if model supports it)
- **Generative UI** on/off (per session; gates `render_ui` / `render_html`)
- Capability labels under models

### Streaming & message UI

- Live SSE token streaming
- **Markdown** rendering (GFM)
- Collapsible **reasoning / chain-of-thought** boxes (survive reload)
- **Working indicator** (dot-matrix patterns by tool type: searching, syncing, uploading, loading, waiting for HITL)
- **Streaming indicator** while answer text flows
- Status matrices: stopped / warning / error / success
- **Branch picker** (edit → regenerate alternate branches)
- Scroll-to-bottom; optional **auto-follow** new content
- Welcome + suggestion chips on empty chat

### Message actions

**Assistant:** Copy · Reload/regenerate · Read aloud (Web Speech TTS) · Stop speaking · Export as Markdown

**User:** Edit message · Copy question (hover)

### Media in chat

Inline: images/GIF · audio · video · PDF · Office docs (server→PDF) · markdown/code/text

`workspace:` paths resolve to authenticated media URLs

### Sources

Per-turn **Sources** footer from run telemetry (citations/URLs)

---

## 4. Tool calling & HITL (human-in-the-loop)

### Approval UX

- Allow once · Allow for rest of chat · Always allow
- Deny · Always deny
- Pending approvals auto-expand tool groups
- Per-chat **auto-approve** bypass

### Activity display modes

- **Compact Worklog** — grouped collapsible tool calls
- **Transparent Stream** — more open/streamed tool activity

### Specialized tool UIs

| Tool | UI |
|---|---|
| `read_file` | Numbered code listing |
| `write_file` / `edit_file` | Path + **diff** view |
| `execute` | Terminal (`$ cmd` + stdout) |
| `ls` / `glob` / `grep` | Path/pattern lists |
| `write_todos` | Todo checklist |
| `task` | Subagent card |
| `fetch_content` | URL/content fetch view |
| `render_ui` | Native generative UI kit (standalone) |
| `render_html` | Sandboxed iframe canvas (standalone) |
| Everything else (MCP, etc.) | Generic collapsible fallback; JSON as tables |

---

## 5. Generative UI

- **`render_ui`** — structured component kit rendered inline as the answer
- **`render_html`** — sandboxed iframe (`allow-scripts`) with `postMessage` bridge (`window.aui.{send,compose,link}`), auto-resized
- Specs/HTML live in tool-call args → **persist across reloads**
- Toggle next to model picker

---

## 6. Workspace dock (global right panel)

- Collapsible, **resizable** width (persisted)
- File **tree** for the active session’s sandbox
- **New file** / **New folder** / **Upload** / **Refresh**
- Rename · delete
- Format-aware viewer:
  - Images inline
  - PDF iframe
  - Markdown rendered
  - Text/code editable
  - Binary → download
- Open external / download links

---

## 7. MCP panel (`/mcp`)

- List configured MCP servers + connection status
- **Add / edit / delete** servers
- Transports: **stdio** (command + args + env) or **HTTP** (URL + headers)
- Per-server **tools** list with args
- Secrets not returned on GET (re-enter to change)

---

## 8. Skills panel (`/skills`)

- Master/detail layout
- Search skills
- **Create** skill (name + `SKILL.md`)
- **Enable / disable**
- **Import / re-import `.zip`**
- Per-skill **file workspace**: `SKILL.md` + helper tree (`scripts/`, `references/`, …)
- Add / delete files in a skill
- Built-in vs user skills
- Delete skill

---

## 9. Memory panel (`/memory`)

- Master/detail like Skills
- Always-loaded core: **Notes**, **About you**, **Persona** (`AGENTS.md`-style)
- Extra **memory files** under `/memories/`
- Search · new file · enable/disable
- Markdown view / edit
- Agent can also read/update these cross-session

---

## 10. Settings (`/settings`)

### Conversation

- Export transcript (**Markdown** or **JSON**)
- **Import** JSON conversation → new chat
- **Clear** current chat
- Default **auto-approve tools in new chats**

### Appearance

- Theme: **Light / Dark / System**
- **Skins** (accent): default, ares, poseidon, sisyphus, mono (+ server-provided)
- Activity display: Compact Worklog vs Transparent Stream
- Auto-follow new content on/off
- Sidebar tab reorder hint
- **Language switcher** (16 locales)

### Providers

- List global (read-only) + user models
- **Add model** with credentials
- **Fetch models** from provider live catalog → multi-select bulk add
- Manual model ID fallback
- **Edit** model / switch deployment via fetch-and-pick
- **Test** connection (ok/fail + reasoning probe)
- Capability tags
- **Default model & reasoning** picker at top
- **xAI (Grok)**: API key **or** OAuth device-code (SuperGrok / X Premium+) as one UI entry with mode toggle

### Profile

- Username · display name · email
- Change password
- **Log out** (also clears active-thread localStorage)

---

## 11. Internationalization & theming

- **16 languages**: en, de, es, fr, it, pt, ru, ja, ko, zh, zh-Hant, tr, uk, hu, ga, af
- Strict typed keys (`Resources = typeof en`)
- Dark-first theming (next-themes)
- Skin accent system via `data-skin` on `<html>`
- Toasts (sonner)

---

## 12. UX polish / platform details

- Single-origin with API (`:8080` prod; Vite `:5173` proxies `/v1` in dev)
- Zustand chat + settings stores; TanStack Query for server data
- Tailwind v4 + shadcn / radix / base-ui + lucide + Geist
- Download helpers for files/exports
- Connection health awareness
- Secure-context requirement (`crypto.randomUUID` — use `localhost`, not raw WSL IP)

---

## Stack (frontend)

- **React 19** + **TypeScript** (strict), **Vite 8**
- **@assistant-ui/react** — chat UI primitives; external-store mode
- **Tailwind CSS v4** + **shadcn** / **radix-ui** / **base-ui**, `lucide-react`, Geist font
- **zustand** (client state) + **@tanstack/react-query** (server cache)
- **react-router 7**, **i18next** (16 locales), **next-themes** (default dark), **sonner** (toasts)
- **Biome** (lint + format)

### Source layout (`frontend/src/`)

```
main.tsx  App.tsx  providers.tsx   # entry, routes, app-wide providers
runtime/        # JoyjoyRuntimeProvider + SSE client + workspace attachments
routes/         # ChatPage, SettingsPage, McpPanel, SkillsPanel, MemoryPanel, ProvidersPanel, AuthPage
components/
  assistant-ui/ # thread, tool-uis, generative-ui, html-canvas, reasoning, media-part, …
  chat/         # ConversationSidebar, ModelPicker, WorkspaceDock, DownloadButton
  layout/       # AppShell, PanelLayout, ConnectionStatus
  memory/ skills/ settings/ auth/ ui/
store/          # chat.ts, settings.ts
api/            # client, queries, sessions, auth, workspace, …
i18n/           # config + 16 locale files
lib/            # media, utils, nav, text, diff, useFileDownload
```

---

## In one line

Joyjoy’s UI is a **full agent workbench**: multi-session chat with streaming, tool HITL, generative UI, sandbox workspace, MCP/skills/memory management, multi-provider model config (including xAI OAuth), and a polished multi-language settings shell — not just a bare chat box.

---

*Generated from frontend source inspection (`frontend/src`, `frontend/README.md`, locale strings, and key UI components).*
