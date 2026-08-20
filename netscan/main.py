import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from netscan.api.v1.router import api_v1_router
from netscan.config import settings
from netscan.db import init_db
from netscan.services.scheduler_service import scheduler
from netscan.web.views import web_router

logging.basicConfig(level=logging.INFO if not settings.DEBUG else logging.DEBUG)
logger = logging.getLogger("netscan")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing NetScan database...")
    init_db()
    logger.info("Starting NetScan scheduler...")
    scheduler.start()
    yield
    logger.info("Stopping NetScan scheduler...")
    scheduler.shutdown()


app = FastAPI(
    title="NetScan API",
    description="Production-Grade IP Discovery and Availability Platform",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static and Web UI mounting
static_path = Path(__file__).parent / "web" / "static"
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

# Mount Routers
app.include_router(api_v1_router)
app.include_router(web_router)


@app.get("/health", tags=["System"])
def health_check():
    return {"status": "healthy", "service": "NetScan", "version": "0.1.0"}
