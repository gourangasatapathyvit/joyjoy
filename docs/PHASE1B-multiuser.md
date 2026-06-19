# Phase 1b — multi-user accounts in hermes-webui → per-user backend isolation

Goal: hermes-webui authenticates real per-user accounts and forwards the logged-in
username to the joyjoy backend as `X-User-Id`, so each user gets an isolated
tenant (memory / virtual FS / skills / threads). Backend already reads `X-User-Id`.

## Done (additive, backward-compatible — single-password mode untouched)
- `webui/api/users.py` — JSON user store (`STATE_DIR/users.json`, 0600): `add_user`, `verify_user`, `list_users`, `remove_user`, `multi_user_enabled`.
- `webui/api/auth.py` — sessions now bind to a username:
  - `create_session(username=None)` records `token → username` in `STATE_DIR/.session_users.json`.
  - `session_username(cookie_value)` returns the username for a verified session (None if anonymous).
  - `invalidate_session` clears the username mapping too.
- `webui/manage_users.py` — CLI: `add` / `list` / `remove`.

## Wiring — ✅ IMPLEMENTED (py-compile clean; end-to-end run validation pending)
The seams below are now wired:
1. **Login route** — `webui/api/routes.py` `/api/auth/login` (~line 10553):
   - Parse `username` from the JSON body.
   - If `users.multi_user_enabled()`: require `users.verify_user(username, password)`, then `cookie = create_session(username=users.normalize(username))`.
   - Else (legacy): keep `verify_password(password)` + `create_session()`.
   - Keep the existing rate-limiter / CSRF / `set_auth_cookie` flow.
2. **Auth status** — `/api/auth/status` (~line 2767 / 7182): add `"multi_user": users.multi_user_enabled()` so the login page knows to show the username field.
3. **Identity forward** — `webui/api/routes.py` `_start_chat_stream_for_session` (~line 14148) and the worker dispatch (`worker_target = _run_gateway_chat_streaming`, ~14280):
   - At request time capture `username = session_username(parse_cookie(handler))`.
   - Thread it into `_run_gateway_chat_streaming(...)` (new kwarg, default None).
4. **Send header** — `webui/api/gateway_chat.py`, both header blocks (`_run_gateway_runs_api_streaming` ~line 270 and `_run_gateway_chat_streaming` ~line 603):
   - `if username: headers["X-User-Id"] = username`  (omit when falsy → backend falls back to `DEV_DEFAULT_USER`).
5. **Login page** — `webui/static/login.js` + login HTML: show a username input when `status.multi_user` is true; POST `{username, password}`.

## Test
```bash
cd ~/joyjoy/webui
python3 manage_users.py add alice      # prompts password
python3 manage_users.py add bob
# start backend (:8080) + webui (:8787), log in as alice in one browser, bob in another,
# write a file as alice, confirm bob cannot see it (same isolation test as Phase 0).
```

## Hardening backlog
- Per-user salt in `users.py` (currently shared install salt; identical passwords → identical hashes).
- Admin-gated user management endpoint (so the first admin can add users from the UI).
- Optional: map to SSO/JWT later (backend already supports JWT `sub`).
