FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    BOT_MODE=polling \
    FATAL_RESTART_DELAY=20

ARG APP_BUILD_ID=unknown
ENV APP_BUILD_ID=${APP_BUILD_ID}

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN apt-get update \
    && apt-get install -y --no-install-recommends openvpn iproute2 \
    && rm -rf /var/lib/apt/lists/*

COPY vendor/wireproxy_linux_amd64.tar.gz /tmp/wireproxy.tar.gz
RUN tar -xzf /tmp/wireproxy.tar.gz -C /usr/local/bin \
    && chmod +x /usr/local/bin/wireproxy \
    && test -x /usr/local/bin/wireproxy \
    && rm -f /tmp/wireproxy.tar.gz

COPY build_id.txt ./
COPY config.py .
COPY bot ./bot
RUN grep -q "sheets_async" bot/main.py \
    && test ! -f bot/proxy.py
COPY services ./services

# Root is required to bring up the MikroTik OpenVPN tun device.
CMD ["python", "-m", "bot.runner"]
