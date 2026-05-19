import os
import logging
import subprocess

from platform_async import ensure_compatible_event_loop

ensure_compatible_event_loop()
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def run_migrations():
    logger.info("Running Alembic migrations...")
    try:
        result = subprocess.run(
            ["python", "-m", "alembic", "upgrade", "head"],
            cwd=os.path.dirname(__file__),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            logger.info(f"Migrations complete: {result.stdout.strip() or 'up to date'}")
        else:
            logger.error(f"Migration failed: {result.stderr}")
    except Exception as e:
        logger.error(f"Migration error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_migrations()
    logger.info("CrisisIQ API server started")
    yield
    logger.info("CrisisIQ API server shutting down")


app = FastAPI(
    title="CrisisIQ API",
    description="Agentic AI Crisis Response System — multi-agent pipeline for urban crisis detection and response",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.staticfiles import StaticFiles

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

from routers.signals import router as signals_router
from routers.crises import router as crises_router
from routers.actions import router as actions_router
from routers.logs import router as logs_router
from routers.seed import router as seed_router
from routers.adk_pipeline import router as adk_pipeline_router

app.include_router(signals_router)
app.include_router(crises_router)
app.include_router(actions_router)
app.include_router(logs_router)
app.include_router(seed_router)
app.include_router(adk_pipeline_router)


@app.get("/")
async def root():
    return {
        "name": "CrisisIQ API",
        "version": "1.0.0",
        "status": "online",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
