"""HTTP routing layer.

The FastAPI route handlers are split by concern into one ``APIRouter`` per
module (auth, models, mcp, skills, memory, workspace, settings, chat, runs,
sessions, health). ``main.py`` builds the app + lifespan and mounts every
router via ``app.include_router``; the routers themselves hold no app state —
they read ``request.app.state`` (checkpointer/store) and the shared
``deps.settings`` singleton.
"""
