#!/usr/bin/env bash
# Executa uma rodada de carga: load.sh <alvo> <vus> <rep> <dir>, com dir dentro de results/.
set -uo pipefail

TARGET=$1 VUS=$2 REP=$3 DIR=$4
cd "$(dirname "$0")/.."
export VUS WARMUP="${WARMUP:-30}" DURATION="${DURATION:-180}"
export BENCH_UID="$(id -u)" BENCH_GID="$(id -g)"

case "$TARGET" in
  go-fiber)    PROFILE=go;     PORT=8081 ;;
  java-jvm)    PROFILE=jvm;    PORT=8082 ;;
  java-native) PROFILE=native; PORT=8083 ;;
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
  -e TARGET_URL="http://$TARGET:8080/api/io" -e VUS -e WARMUP -e DURATION \
  -e OUT="/$DIR/k6-$TAG.json" \
  k6 run --quiet /scripts/io.js 2>&1 | tee "$DIR/logs/k6-$TAG.log"
K6_STATUS=${PIPESTATUS[0]}

cleanup
PIDS=()

# Logs e estado de OOM precisam ser lidos antes de remover o alvo.
docker logs "$CONTAINER" >"$DIR/logs/$TAG.log" 2>&1
docker logs bench-mock-api >"$DIR/logs/mock-api-$TAG.log" 2>&1
docker inspect -f '{{.State.OOMKilled}}' "$CONTAINER" >"$DIR/oom-$TAG.txt"
docker compose --profile "$PROFILE" rm -sf "$TARGET" >/dev/null 2>&1

[ "$K6_STATUS" -eq 0 ] || echo "k6 terminou com status $K6_STATUS em $TAG" >&2
exit "$K6_STATUS"
