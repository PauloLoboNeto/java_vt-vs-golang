#!/usr/bin/env bash
# run-variante.sh <imagem> <nome> <vus>: rodada de diagnóstico (30 s + 30 s), com os limites dos alvos.
set -uo pipefail
IMG=$1 NAME=$2 VUS=$3 DG=results/diagnostico-python
NET=$(docker inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}{{end}}' bench-mock-api)
docker rm -f bench-diag >/dev/null 2>&1
docker run -d --name bench-diag --network "$NET" --cpus 2 -m 1g --memory-swap 1g --ulimit nofile=65535 \
  --sysctl net.core.somaxconn=65535 --sysctl net.ipv4.ip_local_port_range="1024 65535" \
  -v "$PWD/$DG/profile:/out" "$IMG" >/dev/null
sleep 3
( sleep 40; { date -u +%T; docker top bench-diag -eo pid,pcpu,rss,nlwp; } >"$DG/profile/top-$NAME.txt" ) &
python3 scripts/collect_stats.py bench-diag "$DG/stats-$NAME-$VUS.csv" & S=$!
VUS=$VUS WARMUP=30 DURATION=30 MODE=vus docker compose --profile tools run --rm -T --no-deps --name bench-k6 \
  -e TARGET_URL=http://bench-diag:8080/api/io -e VUS -e WARMUP -e DURATION -e MODE -e OUT="/$DG/k6-$NAME-$VUS.json" \
  k6 run --quiet /scripts/io.js 2>&1 | tail -1 | cut -c1-220
kill $S 2>/dev/null; wait 2>/dev/null
docker logs bench-diag >"$DG/logs-$NAME-$VUS.log" 2>&1
docker exec bench-diag cat /sys/fs/cgroup/memory.events | grep oom_kill | head -1
docker rm -f bench-diag >/dev/null 2>&1
