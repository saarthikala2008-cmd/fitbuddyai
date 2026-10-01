"""FitBuddy FastAPI entry point.  Run:  uvicorn app.main:app --reload"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import STATIC_DIR
from app.database import init_db
from app.routes import router


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()  # creates fitbuddy.db + tables on first run
    yield


app = FastAPI(title="FitBuddy - AI Fitness Plan Generator", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(router)
