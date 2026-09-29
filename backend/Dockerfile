FROM python:3.12-slim AS base

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY telegram_snowball ./telegram_snowball

RUN pip install --no-cache-dir .

ENV SNOWBALL_BIND=0.0.0.0 \
    SNOWBALL_API_PORT=8000 \
    SNOWBALL_DATA_DIR=/data \
    PYTHONUNBUFFERED=1

FROM base AS embed

RUN apt-get update \
    && apt-get install -y --no-install-recommends git libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch \
    && pip install --no-cache-dir --index-url https://pypi.org/simple ".[embed]"

ENV TOKENIZERS_PARALLELISM=false \
    SNOWBALL_EMBED_BIND=0.0.0.0 \
    SNOWBALL_EMBED_PORT=8001 \
    SNOWBALL_WORKER_KIND=embed

EXPOSE 8001

CMD ["python", "-m", "telegram_snowball.embed"]

FROM base AS scrape

EXPOSE 8000

CMD ["uvicorn", "telegram_snowball.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
