# syntax=docker/dockerfile:1

FROM node:22-slim-bookworm AS web

WORKDIR /web

COPY dashboard/web/package.json dashboard/web/package-lock.json ./
RUN npm ci

COPY dashboard/web/ ./
RUN npm run build

FROM python:3.12-slim-bookworm

# Build: docker build -t alertsify-dashboard .
# Run:  docker run --rm -p 8080:8080 --env-file .env alertsify-dashboard

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DASHBOARD_HOST=0.0.0.0 \
    DASHBOARD_PORT=8080

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 --shell /usr/sbin/nologin app

COPY pyproject.toml ./
COPY src ./src
COPY --from=web /web/dist ./dashboard/web/dist

RUN pip install .

RUN chown -R app:app /app

USER app

EXPOSE 8080

CMD ["alertsify-dashboard"]
