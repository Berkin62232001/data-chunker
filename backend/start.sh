#!/bin/bash
set -e

echo "==> Running Alembic migrations..."
alembic upgrade head
echo "==> Migrations complete."

echo "==> Starting uvicorn on 0.0.0.0:8000..."
exec uvicorn main:app --host 0.0.0.0 --port 8000
