#!/usr/bin/env python3
"""joyjoy: manage hermes-webui multi-user accounts.

Run from the webui directory (so `api` is importable) using the webui venv:

    cd ~/joyjoy/webui
    python3 manage_users.py add alice
    python3 manage_users.py list
    python3 manage_users.py remove alice

Adding the first user switches the login page into username+password mode
(see docs/PHASE1B-multiuser.md). With zero users, single-password auth is
unchanged.
"""

import getpass
import sys

from api import users


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: manage_users.py {add|list|remove} [username]")
        return 2
    cmd = argv[0]
    if cmd == "list":
        names = users.list_users()
        print("\n".join(names) if names else "(no users; single-password mode)")
        return 0
    if cmd == "add":
        if len(argv) < 2:
            print("username required")
            return 2
        pw = getpass.getpass("password: ")
        if pw != getpass.getpass("confirm:  "):
            print("passwords do not match")
            return 1
        try:
            users.add_user(argv[1], pw)
        except ValueError as exc:
            print(f"error: {exc}")
            return 1
        print(f"user '{users.normalize(argv[1])}' saved")
        return 0
    if cmd == "remove":
        if len(argv) < 2:
            print("username required")
            return 2
        print("removed" if users.remove_user(argv[1]) else "not found")
        return 0
    print(f"unknown command: {cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
