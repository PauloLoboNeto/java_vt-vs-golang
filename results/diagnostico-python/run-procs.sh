#!/usr/bin/env bash
# run-procs.sh <imagem> <nome> <vus>: 30 s + 30 s, com amostras por processo aos 40 s e aos 60 s.
set -uo pipefail
IMG=$1 NAME=$2 VUS=$3 DG=results/diagnostico-python
NET=$(docker inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}{{end}}' bench-mock-api)
docker rm -f bench-diag >/dev/null 2>&1
docker run -d --name bench-diag --network "$NET" --cpus 2 -m 1g --memory-swap 1g --ulimit nofile=65535 \
  --sysctl net.core.somaxconn=65535 --sysctl net.ipv4.ip_local_port_range="1024 65535" "$IMG" >/dev/null
sleep 3; docker cp $DG/sample_procs.py bench-diag:/tmp/s.py
( sleep 40; docker exec bench-diag python /tmp/s.py; sleep 10; echo ---; docker exec bench-diag python /tmp/s.py ) >"$DG/profile/procs-$NAME-$VUS.txt" 2>&1 &
VUS=$VUS WARMUP=30 DURATION=30 MODE=vus docker compose --profile tools run --rm -T --no-deps --name bench-k6 \
  -e TARGET_URL=http://bench-diag:8080/api/io -e VUS -e WARMUP -e DURATION -e MODE -e OUT="/$DG/k6-procs-$NAME-$VUS.json" \
  k6 run --quiet /scripts/io.js 2>&1 | tail -1 | cut -c1-200
wait
docker exec bench-diag cat /sys/fs/cgroup/memory.events | grep oom_kill | head -1
docker rm -f bench-diag >/dev/null 2>&1
cat "$DG/profile/procs-$NAME-$VUS.txt"
