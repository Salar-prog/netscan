from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address


def _make_limited_app(rate: str = "2/minute") -> FastAPI:
    """Build a minimal FastAPI app with its own Limiter at the given rate."""
    test_limiter = Limiter(key_func=get_remote_address, default_limits=[rate])
    app = FastAPI()
    app.state.limiter = test_limiter
    app.add_middleware(SlowAPIMiddleware)

    @app.get("/ok")
    @test_limiter.exempt
    def ok():
        return "ok"

    @app.get("/limited")
    def limited():
        return "hit"

    def _handler(request: Request, exc: RateLimitExceeded):
        return JSONResponse({"detail": "rate limit exceeded"}, status_code=429)

    app.add_exception_handler(RateLimitExceeded, _handler)
    return app


def test_rate_limit_enforced():
    app = _make_limited_app("2/minute")
    with TestClient(app) as client:
        assert client.get("/limited").status_code == 200
        assert client.get("/limited").status_code == 200
        resp = client.get("/limited")
        assert resp.status_code == 429


def test_exempt_endpoint_not_limited():
    app = _make_limited_app("2/minute")
    with TestClient(app) as client:
        for _ in range(5):
            assert client.get("/ok").status_code == 200
