FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY telegram_snowball ./telegram_snowball

RUN pip install --no-cache-dir --index-url https://pypi.org/simple .

ENV SNOWBALL_BIND=0.0.0.0 \
    SNOWBALL_API_PORT=8000 \
    SNOWBALL_DATA_DIR=/data \
    PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "telegram_snowball.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
