FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY pyproject.toml ./
COPY alembic.ini ./
COPY migrations ./migrations
COPY src ./src

RUN pip install --upgrade pip \
    && pip install ".[database]"

USER app

EXPOSE 8000

CMD ["sh", "-c", "exec uvicorn compute_provisioner.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

