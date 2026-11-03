#!/usr/bin/env bash
# Executa uma rodada de carga: load.sh <alvo> <nivel> <rep> <dir>, com dir dentro de results/.
# O nível é o número de VUs ou, com MODE=rate, a taxa em req/s.
set -uo pipefail

TARGET=$1 VUS=$2 REP=$3 DIR=$4
cd "$(dirname "$0")/.."
export VUS WARMUP="${WARMUP:-30}" DURATION="${DURATION:-180}" MODE="${MODE:-vus}"
export BENCH_UID="$(id -u)" BENCH_GID="$(id -g)"

case "$TARGET" in
  go-fiber)    PROFILE=go;     PORT=8081 ;;
  java-jvm)    PROFILE=jvm;    PORT=8082 ;;
  java-native) PROFILE=native; PORT=8083 ;;
  rust-axum)   PROFILE=rust;   PORT=8084 ;;
  go-fiber-opt)    PROFILE=go-opt;     PORT=8085 ;;
  java-jvm-opt)    PROFILE=jvm-opt;    PORT=8086 ;;
  java-native-opt) PROFILE=native-opt; PORT=8087 ;;
  rust-axum-opt)   PROFILE=rust-opt;   PORT=8088 ;;
  java-native-g1)  PROFILE=native-g1;  PORT=8089 ;;
  java-jvm-zgc)    PROFILE=jvm-zgc;    PORT=8090 ;;
  py-fastapi)       PROFILE=py-fastapi;       PORT=8091 ;;
  py-fastapi-aiohttp) PROFILE=py-fastapi-aiohttp; PORT=8095 ;;
  py-aiohttp)       PROFILE=py-aiohttp;       PORT=8092 ;;
  py-flask-gevent)  PROFILE=py-flask-gevent;  PORT=8093 ;;
  py-flask-threads) PROFILE=py-flask-threads; PORT=8094 ;;
  *) echo "alvo desconhecido: $TARGET" >&2; exit 2 ;;
esac

TAG="$TARGET-$VUS-$REP"
CONTAINER="bench-$TARGET"
mkdir -p "$DIR/logs"

PIDS=()
cleanup() {
  [ "${#PIDS[@]}" -gt 0 ] && kill "${PIDS[@]}" 2>/dev/null
  wait 2>/dev/null
}
trap cleanup EXIT

docker compose --profile "$PROFILE" up -d --force-recreate mock-api "$TARGET" >/dev/null 2>&1 || {
  echo "falha ao subir $TARGET" >&2; exit 1; }

ready=""
for _ in $(seq 1 600); do
  if curl -sf -m 1 "http://127.0.0.1:$PORT/health" >/dev/null; then ready=1; break; fi
  sleep 0.1
done
if [ -z "$ready" ]; then
  echo "$TARGET não respondeu a /health em 60s" >&2
  docker logs "$CONTAINER" >"$DIR/logs/$TAG.log" 2>&1
  exit 1
fi

for pair in "$CONTAINER:$TARGET" "bench-mock-api:mock-api" "bench-k6:k6"; do
  python3 scripts/collect_stats.py "${pair%%:*}" "$DIR/stats-$TAG-${pair##*:}.csv" &
  PIDS+=($!)
done

docker compose --profile tools run --rm -T --no-deps --name bench-k6 \
  -e TARGET_URL="http://$TARGET:8080/api/io" -e VUS -e WARMUP -e DURATION -e MODE \
  -e OUT="/$DIR/k6-$TAG.json" \
  k6 run --quiet /scripts/io.js 2>&1 | tee "$DIR/logs/k6-$TAG.log"
K6_STATUS=${PIPESTATUS[0]}

cleanup
PIDS=()

# Logs e estado de OOM precisam ser lidos antes de remover o alvo.
docker logs "$CONTAINER" >"$DIR/logs/$TAG.log" 2>&1
docker logs bench-mock-api >"$DIR/logs/mock-api-$TAG.log" 2>&1
# Com vários processos, o kernel pode matar um worker sem encerrar o container, e OOMKilled fica
# falso. O contador oom_kill do cgroup registra esse caso. Precisa ser gravado antes de oom-*,
# que marca a rodada como completa em resume.sh.
# Imagens distroless não têm cat: nelas, o arquivo não é gravado.
docker exec "$CONTAINER" cat /sys/fs/cgroup/memory.events >"$DIR/memevents-$TAG.txt" 2>/dev/null || rm -f "$DIR/memevents-$TAG.txt"
docker inspect -f '{{.State.OOMKilled}}' "$CONTAINER" >"$DIR/oom-$TAG.txt"
docker compose --profile "$PROFILE" rm -sf "$TARGET" >/dev/null 2>&1

[ "$K6_STATUS" -eq 0 ] || echo "k6 terminou com status $K6_STATUS em $TAG" >&2
exit "$K6_STATUS"
