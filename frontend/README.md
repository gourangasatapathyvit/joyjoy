# joyjoy — frontend (React SPA)

The joyjoy chat UI: a Vite + React 19 + TypeScript single-page app. It is built to
`dist/` and **served by the FastAPI backend** (`app.frontend()`), so in production
there is no separate UI server — the backend serves both the SPA and the `/v1` API
on one origin.

## Stack
- **Vite** (build/dev) · **React 19** + **TypeScript**
- **assistant-ui** — chat thread/composer primitives
- **Tailwind CSS v4** + **shadcn/ui** + **next-themes** (dark/light/system; brand default = dark)
- **TanStack Query** — server-state cache for all `/v1` calls
- **react-router** — routing + the `RequireAuth` gate
- **react-i18next** — 16 locales (default **English**; see `src/i18n/`)
- **zustand** — small client stores (chat selection, appearance)
- **Biome** — lint/format

## Run
```bash
npm install
npm run dev      # Vite dev server on :5173, proxies /v1 → backend :8080
npm run build    # type-check (tsc -b) + bundle to dist/  (what the backend serves)
npm run check    # Biome lint + format
```
When iterating on UI, run the backend (`:8080`) and `npm run dev` (`:5173`). For a
production-like check, `npm run build` and open the backend at `:8080`.

## How it talks to the backend
- Same-origin `fetch` to `/v1/*` with `credentials: "include"`. Auth is an
  **httpOnly session cookie** the backend sets on sign-in; the app learns its auth
  state only from `GET /v1/auth/me` (drives `RequireAuth`). See `src/api/`.
- Real auth screens: sign-in / sign-up (live username-taken check) / forgot +
  email-OTP reset (`src/routes/AuthPage.tsx`).

## Server-persisted preferences
Appearance/UX prefs live in the DB (`UserConfig`) and follow the user across
devices — they are **not** localStorage-only:
- `src/api/prefs.ts` `persistPref()` mirrors each change to `PUT /v1/settings/ui`
  and keeps the `["ui-settings"]` query cache in sync.
- `src/components/PrefsSync.tsx` (mounted in `AppShell`) hydrates skin, theme,
  locale, activity display, auto-follow, and the default model/reasoning **once**
  after login (saving is suspended during hydration to avoid an echo write).
- Skins come from the DB via `GET /v1/skins` (`useSkins`). The skin is applied as a
  `data-skin` attribute on `<html>`; `src/index.css` maps it to accent overrides.

## Structure (high level)
- `src/api/` — typed clients + TanStack hooks (`auth`, `usersettings`, `prefs`, `sessions`, `data`, `workspace`, …)
- `src/routes/` — pages: chat, Settings (Profile/Appearance/Providers), Skills, MCP, Memory, Workspace, Auth
- `src/components/` — `layout/AppShell`, `chat/*`, `assistant-ui/*` (incl. media rendering), `auth/RequireAuth`, `PrefsSync`
- `src/store/` — `chat` (model/reasoning/thread), `settings` (skin/activity/auto-follow)
- `src/i18n/` — `config.ts`, `languages.ts` (default `en`), `locales/*`
