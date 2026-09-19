"""Resilient process entrypoint.

The previous outage was caused by a container that exited immediately and was
restarted dozens of times per second, pinning the host CPU to load ~140.

This wrapper guarantees that *any* fatal error (including import/config errors)
results in a delayed exit, so the orchestrator's restart loop can never become a
tight, CPU-burning loop. It is intentionally dependency-free and import-safe.
"""

from __future__ import annotations

import logging
import os
import socket
import subprocess
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("runner")


def _fatal_delay() -> int:
    try:
        return max(5, int(os.getenv("FATAL_RESTART_DELAY", "20")))
    except ValueError:
        return 20


def _wait_tcp(host: str, port: int, attempts: int = 40) -> bool:
    for _ in range(attempts):
        try:
            with socket.create_connection((host, port), timeout=0.4):
                return True
        except OSError:
            time.sleep(0.25)
    return False


def _wait_tun(attempts: int = 60) -> bool:
    for _ in range(attempts):
        if os.path.exists("/sys/class/net/tun0"):
            return True
        time.sleep(0.5)
    return False


def _start_openvpn() -> None:
    """Connect this container to the Docker-only MikroTik OpenVPN (not a user VPN)."""
    user = os.getenv("OVPN_USER", "").strip()
    password = os.getenv("OVPN_PASSWORD", "").strip()
    ca_b64 = os.getenv("OVPN_CA_B64", "").strip()
    remote = os.getenv("OVPN_REMOTE", "155.117.197.30").strip()
    if not (user and password and ca_b64):
        return

    import base64

    try:
        ca_pem = base64.b64decode(ca_b64).decode("ascii")
    except Exception as exc:  # noqa: BLE001
        logger.warning("OVPN_CA_B64 is invalid: %s", exc)
        return

    if not os.path.exists("/dev/net/tun"):
        os.makedirs("/dev/net", exist_ok=True)
        subprocess.call(["mknod", "/dev/net/tun", "c", "10", "200"])  # noqa: S603,S607

    conf_path = "/tmp/homa.ovpn"
    auth_path = "/tmp/ovpn-auth"
    conf = (
        "client\n"
        "dev tun\n"
        "proto tcp\n"
        f"remote {remote} 443\n"
        f"remote {remote} 10880\n"
        "nobind\n"
        "persist-tun\n"
        "persist-key\n"
        "resolv-retry infinite\n"
        "remote-cert-tls server\n"
        "auth SHA256\n"
        "cipher AES-256-CBC\n"
        "data-ciphers AES-256-GCM:AES-256-CBC\n"
        "data-ciphers-fallback AES-256-CBC\n"
        f"auth-user-pass {auth_path}\n"
        "redirect-gateway def1\n"
        "dhcp-option DNS 1.1.1.1\n"
        "verb 3\n"
        "<ca>\n"
        f"{ca_pem.strip()}\n"
        "</ca>\n"
    )
    with open(conf_path, "w", encoding="utf-8") as handle:
        handle.write(conf)
    with open(auth_path, "w", encoding="utf-8") as handle:
        handle.write(f"{user}\n{password}\n")
    os.chmod(conf_path, 0o600)
    os.chmod(auth_path, 0o600)

    subprocess.Popen(  # noqa: S603
        ["openvpn", "--config", conf_path],
        stdout=sys.stdout,
        stderr=sys.stderr,
        start_new_session=True,
    )
    if _wait_tun():
        try:
            with open("/etc/resolv.conf", "w", encoding="utf-8") as handle:
                handle.write("nameserver 1.1.1.1\n")
        except OSError as extra:
            logger.warning("Could not set VPN DNS: %s", extra)
        os.environ.pop("TELEGRAM_PROXY", None)
        logger.info("Telegram egress via MikroTik OpenVPN tun0 (Docker-only VPN)")
    else:
        logger.warning("OpenVPN started but tun0 is not up")


def _start_wireproxy() -> None:
    """Userspace WireGuard → local SOCKS. Telegram only; not a host-wide VPN."""
    private = os.getenv("WG_PRIVATE_KEY", "").strip()
    peer = os.getenv("WG_PEER_PUBLIC_KEY", "").strip()
    endpoint = os.getenv("WG_ENDPOINT", "").strip()
    address = os.getenv("WG_ADDRESS", "10.77.77.2/32").strip()
    if not (private and peer and endpoint):
        return

    binary = os.getenv("WIREPROXY_BIN", "/usr/local/bin/wireproxy")
    if not os.path.isfile(binary):
        logger.warning("WG env set but %s is missing", binary)
        return

    conf_path = "/tmp/wireproxy.conf"
    conf = (
        "[Interface]\n"
        f"Address = {address}\n"
        f"PrivateKey = {private}\n"
        "DNS = 1.1.1.1\n"
        "\n"
        "[Peer]\n"
        f"PublicKey = {peer}\n"
        f"Endpoint = {endpoint}\n"
        "AllowedIPs = 0.0.0.0/0\n"
        "PersistentKeepalive = 25\n"
        "\n"
        "[Resolve]\n"
        "ResolveStrategy = ipv4\n"
        "\n"
        "[Socks5]\n"
        "BindAddress = 127.0.0.1:1080\n"
    )
    with open(conf_path, "w", encoding="utf-8") as handle:
        handle.write(conf)
    os.chmod(conf_path, 0o600)

    subprocess.Popen(  # noqa: S603
        [binary, "-c", conf_path],
        stdout=sys.stdout,
        stderr=sys.stderr,
        start_new_session=True,
    )
    if _wait_tcp("127.0.0.1", 1080):
        os.environ["TELEGRAM_PROXY"] = "socks5://127.0.0.1:1080"
        logger.info("Telegram egress via userspace WireGuard SOCKS (not a user VPN)")
    else:
        logger.warning("wireproxy started but SOCKS 127.0.0.1:1080 is not ready")


def main() -> int:
    try:
        _start_openvpn()
        if not os.getenv("OVPN_USER", "").strip():
            _start_wireproxy()
        from bot.main import main as run_bot

        run_bot()
        return 0
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutdown requested.")
        return 0
    except BaseException as exc:  # noqa: BLE001 - last-resort guard
        delay = _fatal_delay()
        logger.exception("Fatal error, sleeping %ss before exit to avoid crash loop: %s", delay, exc)
        time.sleep(delay)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
