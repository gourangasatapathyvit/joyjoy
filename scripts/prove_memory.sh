#!/usr/bin/env bash
echo "--- HERMES memory files contain the marker? [expect: NONE] ---"
if grep -rl "MARKER-9921" /home/gourangasatapathy/.hermes/memories /home/gourangasatapathy/.hermes/SOUL.md 2>/dev/null; then
  echo "!! FOUND IN HERMES"
else
  echo "NONE -> hermes files untouched"
fi
echo "--- DEEPAGENT store contains the marker? [expect: 3] ---"
grep -a -o "MARKER-9921" /home/gourangasatapathy/joyjoy/data/dev_store.sqlite 2>/dev/null | wc -l
echo "--- hermes USER.md still holds its OWN original content (proves separation) ---"
head -2 /home/gourangasatapathy/.hermes/memories/USER.md 2>/dev/null || echo "(no hermes USER.md)"
