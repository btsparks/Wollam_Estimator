"""WEIS v2 — FastAPI application entry point.

Serves both the REST API and the static frontend.
Run with: uvicorn app.main:app --reload --port 8000
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import STATIC_DIR
from app.database import init_db
from app.api.interview import router as interview_router
from app.api.diary import router as diary_router
from app.api.documents import router as documents_router
from app.api.settings import router as settings_router
from app.api.chat import router as chat_router
from app.api.estimates import router as estimates_router
from app.api.bidding import router as bidding_router

# Initialize database (runs migrations if needed)
init_db()

app = FastAPI(
    title="WEIS v2",
    description="Wollam Estimating Intelligence System",
    version="2.0.0",
)

# API routes
app.include_router(interview_router)
app.include_router(diary_router)
app.include_router(documents_router)
app.include_router(settings_router)
app.include_router(chat_router)
app.include_router(estimates_router)
app.include_router(bidding_router)

# Static files (CSS, JS, assets)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# SPA entry point — serve index.html for the root
@app.get("/")
async def root():
    return FileResponse(str(STATIC_DIR / "index.html"))
