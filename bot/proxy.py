"""Optional VLESS proxy support via an embedded, resource-safe sing-box process.

Design goals (hard lessons from the prior outage):
- NEVER crash-loop the container. Every proxy failure is handled in-process with
  bounded backoff; the bot keeps running no matter what.
- Node selection / failover happens INSIDE sing-box via an `urltest` outbound, so
  there is no "try each node then exit" logic that could kill the container.
- A daemon thread supervises sing-box and restarts it with capped backoff.
- Every PROXY_HEALTH_INTERVAL seconds (default 60) the supervisor probes Telegram
  through the local SOCKS proxy. On failure it refreshes the full subscription,
  rewrites sing-box config, and restarts the process.

This module is import-safe and only does work when PROXY_ENABLED is truthy.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import ssl
import subprocess
import threading
import time
import urllib.request
from urllib.parse import parse_qs, unquote, urlparse

logger = logging.getLogger(__name__)

SINGBOX_BIN = os.getenv("SINGBOX_BIN", "/usr/local/bin/sing-box")
SINGBOX_RUNTIME_BIN = "/app/.cache/sing-box"
SINGBOX_CONFIG = os.getenv("SINGBOX_CONFIG", "/tmp/sing-box.json")

# Network types we can faithfully translate into a sing-box outbound. Anything
# else (xhttp, kcp, quic, splithttp, ...) is skipped so we never emit a broken
# bare-TCP node that urltest would still try to dial.
SUPPORTED_NETS = {"", "tcp", "ws", "grpc", "http", "h2"}

# Prefer clients that return base64 URI lists. clash-meta / stash often return
# Clash YAML which this generator cannot consume.
SUBSCRIPTION_USER_AGENTS = (
    "v2rayN/6.45",
    "Shadowrocket/2018",
    "clash-verge/1.7.0",
    "stash",
)


def _maybe_b64_lines(raw: str) -> list[str]:
    """Subscriptions are often a base64 blob of newline-separated URIs."""
    if "://" in raw:
        return raw.splitlines()
    try:
        padded = raw + "=" * (-len(raw) % 4)
        decoded = base64.b64decode(padded).decode(errors="replace")
        if "://" in decoded:
            return decoded.splitlines()
    except Exception:  # noqa: BLE001
        pass
    return raw.splitlines()


def _looks_like_clash(raw: str) -> bool:
    head = raw.lstrip()[:200].lower()
    return head.startswith("mode:") or "proxies:" in head or "mixed-port:" in head


def _proxy_uri_lines(lines: list[str]) -> list[str]:
    return [
        line.strip()
        for line in lines
        if line.strip().startswith(("vless://", "vmess://", "trojan://", "ss://"))
    ]


def _fetch_subscription(url: str, timeout: int = 20) -> list[str]:
    """Fetch a VLESS subscription; try several UAs until URI list appears."""
    clean_url = url.split("#", 1)[0].strip()
    last_exc: Exception | None = None

    for user_agent in SUBSCRIPTION_USER_AGENTS:
        for verify_tls in (True, False):
            try:
                request = urllib.request.Request(
                    clean_url,
                    headers={"User-Agent": user_agent},
                )
                context: ssl.SSLContext | None = None
                if not verify_tls:
                    context = ssl.create_default_context()
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                with urllib.request.urlopen(  # noqa: S310
                    request,
                    timeout=timeout,
                    context=context,
                ) as resp:
                    raw = resp.read().decode(errors="replace").strip()

                if not verify_tls:
                    host = urlparse(clean_url).hostname or clean_url
                    logger.warning(
                        "Subscription fetched with TLS verify disabled for %s (%s)",
                        host,
                        user_agent,
                    )

                if _looks_like_clash(raw):
                    logger.info(
                        "Subscription UA %s returned Clash YAML; trying next UA",
                        user_agent,
                    )
                    break

                lines = [line.strip() for line in _maybe_b64_lines(raw) if line.strip()]
                uris = _proxy_uri_lines(lines)
                if uris:
                    logger.info(
                        "Subscription OK via UA %s (%d proxy URI(s))",
                        user_agent,
                        len(uris),
                    )
                    return uris

                logger.warning(
                    "Subscription UA %s returned no proxy URIs; trying next",
                    user_agent,
                )
                break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if verify_tls:
                    logger.warning(
                        "Subscription fetch failed with UA %s (will retry without TLS verify): %s",
                        user_agent,
                        exc,
                    )
                    continue
                logger.warning(
                    "Subscription fetch failed with UA %s: %s",
                    user_agent,
                    exc,
                )

    if last_exc is not None:
        raise last_exc
    return []


def _transport(net: str, q: dict[str, str]) -> dict | None:
    if net in ("", "tcp"):
        return None
    if net == "ws":
        transport: dict = {"type": "ws", "path": q.get("path", "/")}
        if q.get("host"):
            transport["headers"] = {"Host": q["host"]}
        return transport
    if net == "grpc":
        return {"type": "grpc", "service_name": q.get("serviceName", q.get("path", ""))}
    if net in ("http", "h2"):
        transport = {"type": "http"}
        if q.get("host"):
            transport["host"] = q["host"].split(",")
        if q.get("path"):
            transport["path"] = q["path"]
        return transport
    return None


def _parse_vless(uri: str, tag: str) -> dict | None:
    """Convert a vless:// URI into a sing-box outbound (tcp/ws/grpc, tls/reality)."""
    try:
        parsed = urlparse(uri)
        if parsed.scheme != "vless":
            return None
        uuid = unquote(parsed.username or "")
        host = parsed.hostname
        port = parsed.port or 443
        if not uuid or not host:
            return None

        q = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        security = q.get("security", "none")
        net = q.get("type", "tcp")
        if net not in SUPPORTED_NETS:
            logger.info("Skipping node %s with unsupported transport %r", tag, net)
            return None

        out: dict = {
            "type": "vless",
            "tag": tag,
            "server": host,
            "server_port": int(port),
            "uuid": uuid,
            "packet_encoding": "xudp",
        }
        if q.get("flow"):
            out["flow"] = q["flow"]

        if security in ("tls", "reality"):
            tls: dict = {"enabled": True, "server_name": q.get("sni") or q.get("peer") or host}
            if q.get("fp"):
                tls["utls"] = {"enabled": True, "fingerprint": q["fp"]}
            if q.get("alpn"):
                tls["alpn"] = q["alpn"].split(",")
            if security == "reality":
                reality: dict = {"enabled": True}
                if q.get("pbk"):
                    reality["public_key"] = q["pbk"]
                if q.get("sid"):
                    reality["short_id"] = q["sid"]
                tls["reality"] = reality
                tls.setdefault("utls", {"enabled": True, "fingerprint": "chrome"})
            out["tls"] = tls

        transport = _transport(net, q)
        if transport:
            out["transport"] = transport
        return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("Skipping unparsable node %s: %s", tag, exc)
        return None


def _build_config(nodes: list[dict], socks_port: int) -> dict:
    tags = [n["tag"] for n in nodes]
    outbounds: list[dict] = list(nodes)
    outbounds.append({
        "type": "urltest",
        "tag": "auto",
        "outbounds": tags,
        "url": "https://www.gstatic.com/generate_204",
        "interval": "1m0s",
        "tolerance": 100,
    })
    outbounds.append({"type": "direct", "tag": "direct"})
    # No explicit "dns" block: sing-box 1.12+ made the legacy DNS server format a
    # FATAL error, and the new format differs across releases. Letting sing-box use
    # the container's system resolver is version-proof and sufficient here.
    return {
        "log": {"level": "warn", "timestamp": True},
        "inbounds": [{
            "type": "socks",
            "tag": "socks-in",
            "listen": "127.0.0.1",
            "listen_port": socks_port,
        }],
        "outbounds": outbounds,
        "route": {"final": "auto"},
    }


def _telegram_probe_url() -> str:
    """Prefer getMe so the probe matches the bot's real HTTPS path."""
    token = os.getenv("BOT_TOKEN", "").strip()
    if token:
        return f"https://api.telegram.org/bot{token}/getMe"
    return "https://api.telegram.org/"


def _probe_telegram_via_socks(socks_port: int, timeout: float = 12.0) -> bool:
    """Return True when Telegram Bot API HTTPS works through local SOCKS.

    A bare TCP connect is not enough: some dead VLESS nodes accept the
    handshake then reset mid-request (exactly what breaks aiogram polling).
    """
    probe_url = _telegram_probe_url()

    # curl does a full HTTPS request through the SOCKS proxy.
    try:
        result = subprocess.run(  # noqa: S603
            [
                "curl",
                "-sS",
                "-x",
                f"socks5h://127.0.0.1:{socks_port}",
                "--max-time",
                str(max(1, int(timeout))),
                "-o",
                "/dev/null",
                "-w",
                "%{http_code}",
                probe_url,
            ],
            capture_output=True,
            text=True,
            timeout=timeout + 5,
            check=False,
        )
        code = (result.stdout or "").strip()
        if code == "200":
            return True
        logger.debug("curl Telegram probe HTTP %s", code or "empty")
    except Exception as exc:  # noqa: BLE001
        logger.debug("curl Telegram probe failed: %s", exc)

    # Fallback: python-socks + TLS + minimal HTTP GET.
    try:
        from python_socks.sync import Proxy

        parsed = urlparse(probe_url)
        host = parsed.hostname or "api.telegram.org"
        port = parsed.port or 443
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        proxy = Proxy.from_url(f"socks5://127.0.0.1:{socks_port}")
        raw_sock = proxy.connect(dest_host=host, dest_port=port, timeout=timeout)
        context = ssl.create_default_context()
        with context.wrap_socket(raw_sock, server_hostname=host) as tls_sock:
            tls_sock.settimeout(timeout)
            request = (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {host}\r\n"
                "Connection: close\r\n"
                "User-Agent: homa-proxy-health/1\r\n"
                "\r\n"
            ).encode()
            tls_sock.sendall(request)
            first = tls_sock.recv(128)
        return first.startswith(b"HTTP/1.1 200") or first.startswith(b"HTTP/1.0 200")
    except Exception as exc:  # noqa: BLE001
        logger.debug("python-socks Telegram probe failed: %s", exc)
        return False


class ProxyManager:
    """Owns the sing-box subprocess and keeps it alive without crash-looping."""

    def __init__(self, sub_url: str, uris: list[str], socks_port: int) -> None:
        self._sub_url = sub_url
        self._static_uris = uris
        self._socks_port = socks_port
        self._proc: subprocess.Popen | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._health_interval = max(
            15,
            int(os.getenv("PROXY_HEALTH_INTERVAL", "60").strip() or "60"),
        )
        self._consecutive_failures = 0
        self._last_healthy = False

    def _collect_uris(self) -> list[str]:
        uris = list(self._static_uris)
        if self._sub_url:
            for attempt in range(3):
                try:
                    fetched = _fetch_subscription(self._sub_url)
                    return fetched + uris
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Subscription fetch failed (%d/3): %s", attempt + 1, exc)
                    self._stop.wait(3 * (attempt + 1))
        return uris

    def _write_config(self) -> bool:
        nodes: list[dict] = []
        for index, uri in enumerate(self._collect_uris()):
            node = _parse_vless(uri, f"node-{index}")
            if node:
                nodes.append(node)
        if not nodes:
            logger.error("No usable VLESS nodes available yet.")
            return False
        with open(SINGBOX_CONFIG, "w", encoding="utf-8") as handle:
            json.dump(_build_config(nodes, self._socks_port), handle)
        logger.info("sing-box config written with %d node(s).", len(nodes))
        return True

    def _start_singbox(self) -> bool:
        singbox_bin = _resolved_singbox_bin()
        if not os.path.exists(singbox_bin):
            logger.error("sing-box binary missing at %s", singbox_bin)
            return False
        self._proc = subprocess.Popen(  # noqa: S603
            [singbox_bin, "run", "-c", SINGBOX_CONFIG],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info(
            "sing-box started (pid=%s) on 127.0.0.1:%s",
            self._proc.pid,
            self._socks_port,
        )
        return True

    def _stop_singbox(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        try:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error while stopping sing-box: %s", exc)

    def _process_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _heal(self, *, reason: str) -> bool:
        """Refresh subscription, rewrite config, and restart sing-box."""
        with self._lock:
            logger.warning("Proxy heal started (%s)", reason)
            self._stop_singbox()
            if not self._write_config():
                logger.error("Proxy heal aborted: no usable nodes from subscription.")
                return False
            if not self._start_singbox():
                logger.error("Proxy heal aborted: sing-box failed to start.")
                return False
            # Give urltest a moment to pick a live node.
            self._stop.wait(5)
            ok = _probe_telegram_via_socks(self._socks_port, timeout=12.0)
            if ok:
                logger.info("Proxy healed successfully after refreshing subscription.")
            else:
                logger.warning("Proxy heal finished but Telegram probe still failing.")
            return ok

    def _supervise(self) -> None:
        backoff = 5
        # Initial bring-up.
        if not self._heal(reason="initial-start"):
            while not self._stop.is_set() and not self._heal(reason="initial-retry"):
                backoff = min(backoff * 2, 120)
                self._stop.wait(backoff)

        backoff = 5
        while not self._stop.is_set():
            running = self._process_running()
            healthy = False
            if running:
                healthy = _probe_telegram_via_socks(self._socks_port, timeout=10.0)

            if healthy:
                if not self._last_healthy:
                    logger.info(
                        "Proxy health OK (interval=%ss)",
                        self._health_interval,
                    )
                self._last_healthy = True
                self._consecutive_failures = 0
                backoff = 5
                self._stop.wait(self._health_interval)
                continue

            self._last_healthy = False
            self._consecutive_failures += 1
            reason = (
                "sing-box-not-running"
                if not running
                else f"telegram-unreachable#{self._consecutive_failures}"
            )
            logger.warning(
                "Proxy unhealthy (%s); refreshing full subscription and restarting",
                reason,
            )
            if self._heal(reason=reason):
                backoff = 5
                self._stop.wait(self._health_interval)
            else:
                backoff = min(backoff * 2, 120)
                logger.warning("Proxy heal failed; retry in %ss", backoff)
                self._stop.wait(backoff)

    def launch(self) -> None:
        threading.Thread(target=self._supervise, name="singbox-supervisor", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        self._stop_singbox()


_ACTIVE_MANAGER: ProxyManager | None = None


def _resolved_singbox_bin() -> str:
    if os.path.exists(SINGBOX_BIN):
        return SINGBOX_BIN
    if os.path.exists(SINGBOX_RUNTIME_BIN):
        return SINGBOX_RUNTIME_BIN
    return SINGBOX_BIN


def _ensure_singbox_binary() -> bool:
    """Install sing-box at runtime when the Docker build could not fetch it."""
    if os.path.exists(SINGBOX_BIN) or os.path.exists(SINGBOX_RUNTIME_BIN):
        return True

    version = os.getenv("SINGBOX_VERSION", "1.13.14").strip()
    archive = f"sing-box-{version}-linux-amd64.tar.gz"
    urls = [
        f"https://github.com/SagerNet/sing-box/releases/download/v{version}/{archive}",
        f"https://ghfast.top/https://github.com/SagerNet/sing-box/releases/download/v{version}/{archive}",
        f"https://mirror.ghproxy.com/https://github.com/SagerNet/sing-box/releases/download/v{version}/{archive}",
    ]
    tmp_tgz = "/tmp/sing-box-runtime.tar.gz"
    extract_dir = f"/tmp/sing-box-{version}-linux-amd64"
    target = SINGBOX_RUNTIME_BIN

    for url in urls:
        try:
            subprocess.run(
                ["wget", "--timeout=25", "--tries=1", "-qO", tmp_tgz, url],
                check=True,
                timeout=40,
            )
            subprocess.run(["tar", "-xzf", tmp_tgz, "-C", "/tmp"], check=True, timeout=30)
            src = f"{extract_dir}/sing-box"
            if not os.path.exists(src):
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            subprocess.run(["cp", src, target], check=True, timeout=10)
            os.chmod(target, 0o755)
            logger.info("sing-box installed at runtime from %s -> %s", url, target)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Runtime sing-box download failed from %s: %s", url, exc)

    logger.error("Could not install sing-box binary at runtime.")
    return False


def start_proxy() -> str | None:
    """Start the embedded proxy if configured.

    Returns the local SOCKS URL when PROXY_ENABLED is truthy (the supervisor brings
    sing-box up shortly after). Returns None when proxying is disabled.
    """
    global _ACTIVE_MANAGER

    if os.getenv("PROXY_ENABLED", "false").strip().lower() not in ("1", "true", "yes", "on"):
        return None

    sub_url = os.getenv("VLESS_SUBSCRIPTION_URL", "").strip()
    uris_raw = os.getenv("VLESS_URIS", "").strip()
    uris = [u.strip() for u in uris_raw.splitlines() if u.strip()]
    single = os.getenv("VLESS_URI", "").strip()
    if single:
        uris.append(single)

    if not sub_url and not uris:
        logger.error("PROXY_ENABLED is set but no VLESS_SUBSCRIPTION_URL / VLESS_URI(S) provided.")
        return None

    _ensure_singbox_binary()

    port = int(os.getenv("PROXY_PORT", "10808"))
    manager = ProxyManager(sub_url, uris, port)
    _ACTIVE_MANAGER = manager
    manager.launch()
    socks_url = f"socks5://127.0.0.1:{port}"
    interval = max(15, int(os.getenv("PROXY_HEALTH_INTERVAL", "60").strip() or "60"))
    logger.info(
        "Proxy enabled; health check every %ss through %s",
        interval,
        socks_url,
    )
    return socks_url
