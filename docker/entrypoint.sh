#!/bin/bash
set -e

DATA_DIR="${DATA_DIR:-/data}"
DB_PATH="${DATA_DIR}/cert_speedrun.db"

echo "=== Cert Speedrun Optimizer Container Starting ==="
echo "Data directory: ${DATA_DIR}"

# Ensure data directory exists
mkdir -p "${DATA_DIR}"

# Ensure log directory exists
mkdir -p /var/log/supervisor

# Initialize database if it doesn't exist
if [ ! -f "${DB_PATH}" ]; then
    echo "Initializing database..."
    cd /app
    python -c "
from cert_speedrun.db.database import init_db
import asyncio
asyncio.run(init_db())
"
    echo "Database initialized at ${DB_PATH}"

    # Seed sample data if SEED_DATA is true (default)
    if [ "${SEED_DATA:-true}" = "true" ]; then
        echo "Seeding sample data..."
        python /app/seed_data.py
        echo "Sample data seeded successfully"
    fi
else
    echo "Database already exists at ${DB_PATH}"
fi

echo "Starting services..."
exec "$@"
