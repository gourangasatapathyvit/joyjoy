# joyjoy frontend

The React SPA for **joyjoy**. It is **not a standalone app** — it's built to `frontend/dist` and served by the FastAPI backend from the same origin (`:8080`), so there's no separate UI server in production. It talks to the backend's `/v1/*` API with `credentials: "include"` (httpOnly session cookie = identity).

## Stack

React 19 + TypeScript + **Vite** · **assistant-ui** (chat runtime/UI) · Tailwind v4 + shadcn (Radix / base-ui) · **TanStack Query** (server state) · **Zustand** (UI state) · **react-i18next** (16 locales) · **Biome** (lint/format).

## Scripts

```bash
npm install          # first time (start_all.sh / serve.sh do this for you)
npm run dev          # Vite dev server on :5173, proxies /v1 → :8080 (hot reload)
npm run build        # tsc -b && vite build → frontend/dist (what the backend serves)
npm run check        # biome check --write .   (lint + format, autofix)
npm run lint         # biome lint .
npm run preview      # preview the production build
```

**Type-check is part of the build** (`tsc -b`). Before committing, `npx tsc --noEmit` and `npm run check` must be clean. To iterate on the UI: run the backend (`scripts/restart_backend.sh`) on `:8080`, then `npm run dev`. To update what the backend actually serves, `npm run build` (or `scripts/serve.sh`).

## Structure (`src/`)

- `api/` — the typed `/v1` client (`client.ts`) + TanStack Query hooks: `sessions.ts`, `workspace.ts`, `usersettings.ts`/`prefs.ts` (UI prefs), `queries.ts`, `types.ts`.
- `runtime/JoyjoyRuntimeProvider.tsx` — the heart of chat: an assistant-ui **ExternalStore** runtime that drives a turn via `POST /v1/runs` + an SSE `EventSource` (`/v1/runs/{id}/events`), streams text/reasoning/tool events, and surfaces **HITL tool approvals** (incl. per-chat auto-approve).
- `components/`
  - `assistant-ui/` — chat surface (mostly vendored registry components). Notable joyjoy edits: `tool-fallback.tsx` (approval cards + "Allow for rest of chat"), `thread.tsx` (auto-expands the tool group on a pending approval; per-message copy button), `media-part.tsx` (inline image/audio/video/pdf/office/text with a **"Media inaccessible"** fallback that probes each URL).
  - `chat/` — `WorkspaceDock.tsx` (resizable, per-session file dock), `ModelPicker.tsx` (model + reasoning + **Auto-approve** toggle), `ConversationSidebar.tsx`.
  - `settings/` `skills/` `memory/` `auth/` `layout/` `ui/` — Settings panes, Skills/MCP/Memory CRUD, login, app shell, shadcn primitives.
- `routes/` — pages (`ChatPage`, `SettingsPage` + panels, `AuthPage`) wired with react-router.
- `store/chat.ts` — Zustand: active `threadId`, model/reasoning, `autoApprove` (+ account default), workspace dock open/width. The runtime reads it at send-time via `getState()`.
- `i18n/` — `locales/*.ts`; **`en.ts` is the source of truth** (`Resources = typeof en`), so every other locale must carry the same keys or `tsc` fails. Default language English.
- `lib/` — `media.ts` (media-type detection + URL builders, incl. `mediaUrl(threadId, path)`), `constants.ts` (storage keys, dock bounds).

## Conventions

- **Same-origin, cookie auth** — never send credentials in the URL; `client.ts` uses `credentials: "include"`. Identity is the backend session cookie.
- **Server state via TanStack Query; UI state via Zustand.** Per-user prefs persist to `UserConfig` through `/v1/settings/ui` (`api/prefs.ts persistPref()` writes + keeps the query cache in sync; `components/PrefsSync.tsx` hydrates once after login).
- **i18n every user-facing string** and keep all locales key-parity with `en.ts` (the build enforces it). A few vendored assistant-ui registry strings are intentionally left English.
- **assistant-ui components are vendored** (copied into `components/assistant-ui/`), so edits live here rather than in `node_modules`; keep changes minimal so they stay close to upstream.

See the repo root `README.md` (run/setup), `ARCHITECTURE.md` (system overview), and `CLAUDE.md` (contributor/agent guide).
