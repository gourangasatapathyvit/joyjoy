#!/bin/sh
# Runs ONCE, on first init of the bundled Postgres container (localdb profile), via
# /docker-entrypoint-initdb.d. The image already created the app DB (POSTGRES_DB =
# APP_DB_NAME); this adds the SEPARATE LangGraph checkpointer DB so the two never
# collapse into one. Idempotent: \gexec creates it only if it doesn't exist.
set -e

LG_DB="${LANGGRAPH_CHECKPOINT_DB:-langgraph_db}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
SELECT 'CREATE DATABASE "${LG_DB}"'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${LG_DB}')\gexec
SQL

echo "[db-init] ensured LangGraph database '${LG_DB}' (app database is '${POSTGRES_DB}')"
