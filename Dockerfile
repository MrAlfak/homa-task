FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    BOT_MODE=polling \
    FATAL_RESTART_DELAY=20

ARG SINGBOX_VERSION=1.13.14
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates wget \
    && rm -rf /var/lib/apt/lists/*

# Bundled sing-box — GitHub is often blocked on the build host.
COPY vendor/sing-box /usr/local/bin/sing-box
RUN chmod +x /usr/local/bin/sing-box

ARG APP_BUILD_ID=unknown
ENV APP_BUILD_ID=${APP_BUILD_ID}

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY build_id.txt ./
COPY config.py .
COPY bot ./bot
RUN grep -q "sheets_async" bot/main.py
COPY services ./services

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/.cache \
    && chown -R appuser:appuser /app
USER appuser

CMD ["python", "-m", "bot.runner"]
