#!/usr/bin/env bash
# Emit base64 of each hermes memory file (section-tagged) for migration.
for pair in \
  "memory:/home/gourangasatapathy/.hermes/memories/MEMORY.md" \
  "user:/home/gourangasatapathy/.hermes/memories/USER.md" \
  "soul:/home/gourangasatapathy/.hermes/SOUL.md"; do
  sec="${pair%%:*}"; f="${pair#*:}"
  if [ -f "$f" ] && [ -s "$f" ]; then
    echo "BEGIN:$sec:$(wc -c < "$f")"
    base64 -w0 "$f"; echo
    echo "END:$sec"
  else
    echo "SKIP:$sec"
  fi
done
