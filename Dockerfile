FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    nmap \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir -e .[test]

COPY . .

RUN useradd -m -s /bin/bash netscan && chown -R netscan:netscan /app
USER netscan

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import httpx; r=httpx.get('http://localhost:8000/health'); r.raise_for_status()"

CMD ["uvicorn", "netscan.main:app", "--host", "0.0.0.0", "--port", "8000"]
