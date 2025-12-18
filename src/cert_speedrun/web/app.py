"""FastAPI application for cert speedrun optimizer web UI."""

from fastapi import FastAPI

from ..db.database import ensure_db_exists
from .routes import router

# Initialize FastAPI app
app = FastAPI(
    title="Cert Speedrun Optimizer",
    description="Practice certification exams with speedrun methodology",
)

# Include routes
app.include_router(router)


@app.on_event("startup")
async def startup():
    """Initialize database on startup."""
    await ensure_db_exists()
