#!/bin/bash
# Emergency recovery on the Dokploy host (217.114.40.67).
# Goal: relieve CPU saturation so Dokploy/Traefik (blob.firstdata.ir) responds again.
# Strategy: kill the crash-looping Homa VLESS bot first, then stop all *app*
# containers while KEEPING infrastructure (dokploy, traefik, postgres, redis).

set +e

echo "================ 1) Current load ================"
uptime
echo
echo "Top containers by CPU:"
docker stats --no-stream --format "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" \
  | sort -t$'\t' -k2 -hr | head -25

echo
echo "================ 2) Kill Homa bot (root cause) ================"
homa=$(docker ps -aq --filter "name=homa-task-bot")
if [ -n "$homa" ]; then
  docker rm -f $homa
  echo "Removed homa-task-bot containers: $homa"
else
  echo "No homa-task-bot containers found."
fi

echo
echo "================ 3) Stop ALL app containers (keep infra) ================"
# Keep these running so the panel/proxy/db survive.
KEEP_RE='dokploy|traefik|postgres|redis|mariadb|mysql|mongo|database|-db'

apps=$(docker ps --format '{{.ID}} {{.Names}}' | grep -Ev "$KEEP_RE" | awk '{print $1}')
if [ -n "$apps" ]; then
  echo "Stopping app containers:"
  docker ps --format '{{.Names}}' | grep -Ev "$KEEP_RE"
  docker stop $apps
else
  echo "No app containers to stop."
fi

echo
echo "================ 4) Verify infra is alive ================"
docker ps --filter "name=dokploy" --format "table {{.Names}}\t{{.Status}}"
docker ps --filter "name=traefik" --format "table {{.Names}}\t{{.Status}}"

echo
echo "================ 5) Load after cleanup ================"
uptime

echo
echo "Done. Wait ~30s, then open https://blob.firstdata.ir"
echo "If still down, restart proxy/panel:"
echo "  docker restart \$(docker ps -q --filter name=traefik)"
echo "  docker restart \$(docker ps -q --filter name=dokploy)"
