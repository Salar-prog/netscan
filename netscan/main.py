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
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text
from netscan.api.v1.router import api_v1_router
from netscan.config import settings
from netscan.db import init_db, engine
from netscan.limiter import limiter
from netscan.services.scheduler_service import scheduler


access_logger = logging.getLogger("netscan.access")


class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/health":
            return await call_next(request)

        from netscan.limiter import get_client_ip

        start = time.monotonic()
        client_ip = get_client_ip(request)
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
    logger.info("Running Alembic migrations...")
    from alembic.config import Config as AlembicConfig
    from alembic import command as alembic_command

    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    alembic_cfg.attributes["connectable"] = engine
    alembic_command.upgrade(alembic_cfg, "head")
    logger.info("Recovering stale scan jobs...")
    from sqlmodel import Session as _Session
    from netscan.services.scan_service import recover_stale_scan_jobs

    with _Session(engine) as _session:
        recover_stale_scan_jobs(_session)
    if settings.RETENTION_DAYS > 0:
        logger.info("Pruning records older than %d days...", settings.RETENTION_DAYS)
        from netscan.services.retention import prune_old_records

        with _Session(engine) as _session:
            prune_old_records(_session, settings.RETENTION_DAYS)
    logger.info("Starting NetScan scheduler...")
    scheduler.start()
    yield
    logger.info("Stopping NetScan scheduler...")
    scheduler.shutdown()


def create_app(dashboard: bool = True) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        dashboard: If True, include the web dashboard routes.
    """
    from importlib.metadata import version

    app = FastAPI(
        title="NetScan API",
        description="Production-Grade IP Discovery and Availability Platform",
        version=version("netscan"),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    from netscan.api.errors import NetScanException, netscan_exception_handler

    app.add_exception_handler(NetScanException, netscan_exception_handler)

    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(AccessLogMiddleware)

    from netscan.api.idempotency import IdempotencyKeyMiddleware

    app.add_middleware(IdempotencyKeyMiddleware)

    allowed_origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
    if allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Mount API router (always loaded)
    app.include_router(api_v1_router)

    # Mount web dashboard (optional plugin)
    if dashboard:
        from netscan.web.views import web_router

        app.include_router(web_router)

    @app.get("/health", tags=["System"])
    @limiter.exempt
    def health_check(request: Request):
        from importlib.metadata import version

        checks = {"database": "ok", "nmap": "ok", "scheduler": "ok"}
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

        from netscan.services.scheduler_service import scheduler

        if not scheduler.scheduler.running:
            checks["scheduler"] = "not running"
            status_code = "degraded"

        return {"status": status_code, "service": "NetScan", "version": version("netscan"), "checks": checks}

    @app.get("/metrics", tags=["System"])
    @limiter.exempt
    def metrics(request: Request):
        from sqlmodel import select, func
        from netscan.models import Subnet, IPAddress, IPStatus, ScanJob, ScanStatus

        with engine.connect() as conn:
            subnets = conn.execute(select(func.count()).select_from(Subnet)).scalar() or 0
            total_ips = conn.execute(select(func.count()).select_from(IPAddress)).scalar() or 0
            active_ips = conn.execute(
                select(func.count()).select_from(IPAddress).where(IPAddress.status == IPStatus.ACTIVE_DETECTED)
            ).scalar() or 0
            scans_completed = conn.execute(
                select(func.count()).select_from(ScanJob).where(ScanJob.status == ScanStatus.COMPLETED)
            ).scalar() or 0
            scans_failed = conn.execute(
                select(func.count()).select_from(ScanJob).where(ScanJob.status == ScanStatus.FAILED)
            ).scalar() or 0

        lines = [
            f'netscan_subnets_total {subnets}',
            f'netscan_ips_total {total_ips}',
            f'netscan_ips_active {active_ips}',
            f'netscan_scans_completed_total {scans_completed}',
            f'netscan_scans_failed_total {scans_failed}',
        ]
        return "\n".join(lines) + "\n"

    return app


# Default app instance for backward compatibility (uvicorn netscan.main:app)
app = create_app()
