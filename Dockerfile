FROM python:3.12-slim AS builder

WORKDIR /build

COPY pyproject.toml README.md ./
COPY netscan/ netscan/

RUN pip wheel --no-cache-dir --wheel-dir /build/wheels .[test]

FROM python:3.12-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    nmap curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /build/wheels /tmp/wheels
RUN pip install --no-cache-dir /tmp/wheels/*.whl && rm -rf /tmp/wheels

RUN useradd -m -s /bin/bash netscan && chown -R netscan:netscan /app
USER netscan

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import httpx; r=httpx.get('http://localhost:8000/health'); r.raise_for_status()"

CMD ["netscan", "serve", "--host", "0.0.0.0", "--port", "8000"]
