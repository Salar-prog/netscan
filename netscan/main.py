import json
import logging
import logging.config
import shutil
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from netscan.api.v1.router import api_v1_router
from netscan.config import settings
from netscan.db import init_db, engine
from netscan.limiter import limiter
from netscan.services.scheduler_service import scheduler
from netscan.web.views import web_router


access_logger = logging.getLogger("netscan.access")


class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/health":
            return await call_next(request)

        start = time.monotonic()
        client_ip = request.client.host if request.client else "unknown"
        response = await call_next(request)
        duration_ms = int((time.monotonic() - start) * 1000)

        log_data = {
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "client_ip": client_ip,
        }

        if response.status_code >= 500:
            access_logger.error("Request error", extra={"extra_data": log_data})
        elif response.status_code >= 400:
            access_logger.warning("Request failed", extra={"extra_data": log_data})
        else:
            access_logger.info("Request completed", extra={"extra_data": log_data})

        return response


class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "extra_data"):
            log_entry["extra"] = record.extra_data
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, default=str)


def setup_logging():
    log_level = logging.DEBUG if settings.DEBUG else getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    handlers = {"console": {"class": "logging.StreamHandler", "level": log_level}}

    if settings.LOG_FORMAT == "json":
        formatter = {"()": "netscan.main.JSONFormatter"}
    else:
        formatter = {"format": "%(asctime)s %(levelname)-8s %(name)s: %(message)s", "datefmt": "%Y-%m-%d %H:%M:%S"}

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {"default": formatter},
            "handlers": {
                "console": {
                    **handlers["console"],
                    "formatter": "default",
                }
            },
            "root": {"level": log_level, "handlers": ["console"]},
        }
    )


setup_logging()
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
app.add_middleware(AccessLogMiddleware)

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
