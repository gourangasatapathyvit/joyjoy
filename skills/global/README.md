# Global skills (read-only, shared by all users)

Drop one folder per skill here, each containing a `SKILL.md` (deepagents/Claude
skill format). These are surfaced to every user's agent as **read-only**; users
cannot edit them. Per-user skills live in each user's store namespace instead.

Wiring (loading these into the agent + exposing them in the UI as read-only) is
**Phase 3** in [`../../PLAN.md`](../../PLAN.md).

Example:
```
skills/global/
  code-review/
    SKILL.md
  summarize/
    SKILL.md
```
