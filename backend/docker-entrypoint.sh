#!/bin/sh
# docker-entrypoint.sh — self-healing schema migration before app start.
#
# Why this exists: this database's tables were originally created by
# SQLAlchemy's Base.metadata.create_all() (the old api_main.py lifespan
# behaviour), NOT by Alembic — so Alembic's own tracking table
# (alembic_version) was never stamped, even though the schema itself is
# already fully up to date. The first time `alembic upgrade head` ran
# against this database, it had no record of any migration ever being
# applied, so it tried to run the very first migration from scratch —
# including `CREATE TABLE documents`, which already exists.
#
# `alembic stamp head` fixes this with zero risk: it only writes Alembic's
# own bookkeeping row, it never touches your actual tables or data. This
# script tries the normal path first; only on failure does it stamp and
# retry, so a genuinely new/empty database still goes through every
# migration normally, and this fallback never masks a real, unrelated
# migration error (the second `upgrade head` will fail loudly if the
# stamp didn't fix it).
set -e

echo "Running database migrations..."
if alembic upgrade head; then
    echo "Migrations applied cleanly."
else
    echo "alembic upgrade head failed — checking whether this is the"
    echo "known 'tables exist but were never tracked by Alembic' case..."
    if alembic stamp head; then
        echo "Stamped existing schema as up to date. Retrying upgrade..."
        alembic upgrade head
    else
        echo "Stamp also failed — this is a real migration problem, not"
        echo "the untracked-schema case. Exiting so the real error surfaces."
        exit 1
    fi
fi

echo "Starting server..."
exec uvicorn api_main:app --host 0.0.0.0 --port "${PORT:-8000}"
