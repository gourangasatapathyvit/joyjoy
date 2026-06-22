"""Generate the committed global-skills seed bundle from a skills/global directory.

Run this ONCE (while skills/global still exists) to capture every shipped global
skill — SKILL.md + all helper files (base64 for binaries) — into a single JSON
bundle. After that the bundle (backend/app/db/seeds/global_skills.json) is the
source of truth: the DB seed loads it, and the loose skills/global tree can be
deleted. Re-run only if the shipped global skills change.

Usage:  .venv/bin/python scripts/build_global_skills_seed.py [SKILLS_DIR]
"""

from __future__ import annotations

import base64
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SRC = os.path.abspath(os.path.join(HERE, "..", "..", "skills", "global"))
OUT = os.path.join(HERE, "..", "app", "db", "seeds", "global_skills.json")


def _description(md: str) -> str:
    lines = md.splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    for ln in lines[1:]:
        if ln.strip() == "---":
            break
        if ln.lstrip().lower().startswith("description:"):
            return ln.split(":", 1)[1].strip().strip("\"'")
    return ""


def main() -> None:
    src = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SRC
    if not os.path.isdir(src):
        raise SystemExit(f"skills dir not found: {src}")
    skills = []
    for name in sorted(os.listdir(src)):
        d = os.path.join(src, name)
        skill_md = os.path.join(d, "SKILL.md")
        if not (os.path.isdir(d) and os.path.isfile(skill_md)):
            continue
        with open(skill_md, encoding="utf-8") as f:
            content = f.read()
        files = []
        for root, _dirs, fnames in os.walk(d):
            for fn in sorted(fnames):
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, d).replace("\\", "/")
                if rel == "SKILL.md":
                    continue
                raw = open(full, "rb").read()
                try:
                    files.append({"filename": rel, "content": raw.decode("utf-8"), "encoding": "utf-8"})
                except UnicodeDecodeError:
                    files.append(
                        {"filename": rel, "content": base64.b64encode(raw).decode("ascii"), "encoding": "base64"}
                    )
        skills.append({"name": name, "description": _description(content), "content": content, "files": files})

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(skills, f, ensure_ascii=False)
    nfiles = sum(len(s["files"]) for s in skills)
    size = os.path.getsize(OUT)
    print(f"wrote {len(skills)} skills, {nfiles} helper files -> {OUT} ({size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
