FROM python:3.12-slim-bookworm

# Build: docker build -t alertsify-scraper .
# Run:  docker run --rm --env-file .env alertsify-scraper

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 --shell /usr/sbin/nologin app

COPY pyproject.toml ./
COPY src ./src

RUN pip install .

RUN chown -R app:app /app

USER app

CMD ["alertsify-scraper"]
