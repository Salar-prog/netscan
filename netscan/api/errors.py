from fastapi import Request
from fastapi.responses import JSONResponse


class NetScanException(Exception):
    """Structured API error with machine-parseable error_code."""

    def __init__(self, error_code: str, message: str, status_code: int = 400, details: dict | None = None):
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


async def netscan_exception_handler(request: Request, exc: NetScanException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error_code": exc.error_code,
            "message": exc.message,
            "details": exc.details,
        },
    )
