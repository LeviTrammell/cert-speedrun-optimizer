"""Database connection management for cert speedrun optimizer."""

import os
import aiosqlite
from pathlib import Path
from contextlib import asynccontextmanager
from typing import AsyncGenerator

# Database file location - supports DATA_DIR env var for containerization
_data_dir = os.environ.get("DATA_DIR")
if _data_dir:
    DB_DIR = Path(_data_dir)
else:
    DB_DIR = Path(__file__).parent.parent.parent.parent / "data"

DB_PATH = DB_DIR / "cert_speedrun.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


async def init_db() -> None:
    """Initialize the database with schema."""
    DB_DIR.mkdir(parents=True, exist_ok=True)

    schema = SCHEMA_PATH.read_text()

    async with aiosqlite.connect(DB_PATH) as db:
        # Enable foreign keys
        await db.execute("PRAGMA foreign_keys = ON")
        await db.executescript(schema)
        await db.commit()

    print(f"Database initialized at {DB_PATH}")


@asynccontextmanager
async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Get a database connection as an async context manager."""
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys = ON")
    try:
        yield db
    finally:
        await db.close()


async def ensure_db_exists() -> None:
    """Ensure the database exists, initializing if needed."""
    if not DB_PATH.exists():
        await init_db()
