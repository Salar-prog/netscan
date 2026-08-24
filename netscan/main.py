import logging
import shutil
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from netscan.api.v1.router import api_v1_router
from netscan.config import settings
from netscan.db import init_db, engine
from netscan.limiter import limiter
from netscan.services.scheduler_service import scheduler
from netscan.web.views import web_router

logging.basicConfig(level=logging.INFO if not settings.DEBUG else logging.DEBUG)
logger = logging.getLogger("netscan")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_for_production()
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
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Routers
app.include_router(api_v1_router)
app.include_router(web_router)


@app.get("/health", tags=["System"])
@limiter.exempt
def health_check(request: Request):
    checks = {"database": "ok", "nmap": "ok"}
    status_code = "healthy"

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        checks["database"] = "unavailable"
        status_code = "degraded"

    if not shutil.which("nmap"):
        checks["nmap"] = "not found"
        status_code = "degraded"

    return {"status": status_code, "service": "NetScan", "version": "0.1.0", "checks": checks}
