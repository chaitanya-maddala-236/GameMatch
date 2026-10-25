FROM python:3.13.1-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app
COPY requirements.txt pyproject.toml ./
COPY src ./src
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && python -m pip install --no-deps .
COPY scripts ./scripts
COPY dashboard ./dashboard
COPY docs ./docs

EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn gamematch.api:app --host 0.0.0.0 --port ${PORT:-8000} --timeout-keep-alive 5 --workers 1"]
