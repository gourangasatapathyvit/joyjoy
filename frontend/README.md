# joyjoy frontend

The joyjoy web client: a **React 19 + Vite** single-page app built on **assistant-ui** (external-store runtime). In production it's compiled to `dist/` and served by the FastAPI backend on the same origin as the `/v1` API (`:8080`) — there is no separate web server.

> Big-picture architecture lives in [`../ARCHITECTURE.md`](../ARCHITECTURE.md); the API it talks to is in [`../backend/README.md`](../backend/README.md). This README is the frontend dev guide.

## Stack

- **React 19** + **TypeScript** (strict), **Vite 8**
- **@assistant-ui/react** — chat UI primitives; used in **external-store** mode (app owns chat state)
- **Tailwind CSS v4** + **shadcn** / **radix-ui** / **base-ui** components, `lucide-react` icons, Geist font
- **zustand** (client state) + **@tanstack/react-query** (server cache)
- **react-router 7**, **i18next** (16 locales), **next-themes** (default dark), **sonner** (toasts)
- **Biome** (lint + format)

## Layout (`src/`)

```
main.tsx  App.tsx  providers.tsx   # entry, routes, app-wide providers (QueryClient, theme, tooltips)
runtime/        # JoyjoyRuntimeProvider.tsx — assistant-ui external-store runtime + custom SSE client
                #   workspaceAttachment.ts — composer attachments → agent workspace
routes/         # ChatPage, SettingsPage, McpPanel, SkillsPanel, MemoryPanel, ProvidersPanel, AuthPage
components/
  assistant-ui/ # thread, tool-uis, generative-ui (render_ui kit), html-canvas (render_html iframe),
                #   reasoning, media-part, dot-matrix, model-selector, tool-approval/group, …
  chat/         # ConversationSidebar, ModelPicker, WorkspaceDock, DownloadButton
  layout/       # AppShell, PanelLayout, ConnectionStatus
  memory/ skills/ settings/ auth/ ui/(shadcn primitives)
store/          # zustand stores: chat.ts, settings.ts
api/            # client.ts (fetch wrapper), queries.ts (TanStack hooks), sessions/auth/workspace/types…
i18n/           # config + languages + 16 locale files (strict Resources = typeof en)
lib/            # media.ts (workspace:<path> → /v1/media), utils, nav, text, diff, useFileDownload
```

Routes (`App.tsx`): `/signin` (public) and, behind `RequireAuth` + `AppShell`, `/` & `/session/:id` (chat), `/mcp`, `/skills`, `/memory`, `/settings`.

## Develop

```bash
cd frontend
npm install
npm run dev        # Vite dev server on http://localhost:5173
```

The dev server proxies `/v1` → backend `:8080` and **injects `x-user-id: alice`** so you can hit the API without signing in (EventSource can't set headers, so the proxy also covers the SSE stream). So:

- Start the backend first (`../backend` or `../scripts/start_all.sh`).
- Use **`http://localhost:5173`** (a secure context — `crypto.randomUUID` needs it; a raw WSL IP breaks it). The proxied dev identity is `alice`, so seed a `User(id="alice")` or you'll be stuck at `/signin`.

In production identity comes from the `joyjoy` session cookie (no proxy, single origin).

## Build / lint

```bash
npm run build      # tsc -b && vite build  →  dist/  (baked into the backend image)
npm run check      # Biome lint + format (write)
npm run preview    # serve the production build locally
```

`@` is aliased to `src/` (see `vite.config.ts`).

## Key concepts

- **External-store runtime** (`runtime/JoyjoyRuntimeProvider.tsx`): chat state is owned by the app (zustand + a custom SSE client over `POST /v1/runs`), not by an assistant-ui built-in runtime. The stream carries tokens, tool calls, and HITL approval interrupts.
- **Tool UIs** (`components/assistant-ui/tool-uis.tsx`): a `TOOL_UIS` map renders specific tool calls inline. Notably `render_ui` → `GenerativeUI` (native `MessagePrimitive.GenerativeUI` component kit) and `render_html` → `HtmlCanvas` (sandboxed `<iframe sandbox="allow-scripts">` + `postMessage` bridge `window.aui.{send,compose,link}`, auto-resized). Specs/HTML persist across reloads via the tool-call args.
- **Generative-UI toggle**: a per-session button (left of the model picker) in `chat/ModelPicker.tsx`; persisted in localStorage and sent as `generative_ui` on each run so the backend gates the render tools.
- **Workspace media** (`lib/media.ts`): `workspace:<path>` resolves to `/v1/media?thread_id=…&path=…` (same-origin, cookie-auth).
- **i18n**: every locale file is typed against `en` (`Resources = typeof en`) — add a key to all 16 (or via a one-shot script) to keep types valid.
