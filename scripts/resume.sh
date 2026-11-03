#!/usr/bin/env bash
# Retoma uma rodada interrompida: resume.sh <dir>. Mantém a ordem de run-all.sh e pula
# as rodadas completas, identificadas pelo arquivo oom-*, o último gravado por load.sh.
set -uo pipefail
cd "$(dirname "$0")/.."
DIR=$1
TARGETS="${TARGETS:?defina TARGETS com a mesma ordem da rodada}"
LEVELS="${LEVELS:-1000 5000 10000}"
REPS="${REPS:-3}"
export BENCH_UID="$(id -u)" BENCH_GID="$(id -g)"

docker events --filter event=oom --format '{{.Time}} {{.Actor.Attributes.name}}' >>"$DIR/docker-oom-events.log" &
EVENTS=$!
(
  while true; do
    avail=$(awk '/MemAvailable/ {print $2}' /proc/meminfo)
    ct=$(cat /proc/sys/net/netfilter/nf_conntrack_count 2>/dev/null || echo 0)
    echo "$(date +%s%3N),$avail,$ct"
    sleep 5
  done
) >>"$DIR/host.csv" &
HOST=$!
trap 'kill "$EVENTS" "$HOST" 2>/dev/null; wait 2>/dev/null' EXIT

read -r -a LIST <<<"$TARGETS"
N=${#LIST[@]}
for ((rep = 1; rep <= REPS; rep++)); do
  for level in $LEVELS; do
    for ((i = 0; i < N; i++)); do
      t=${LIST[$(((i + rep - 1) % N))]}
      [ -f "$DIR/oom-$t-$level-$rep.txt" ] && continue
      echo "== carga: rep=$rep vus=$level alvo=$t ($(date -u +%H:%M:%S))"
      scripts/load.sh "$t" "$level" "$rep" "$DIR" || \
        echo "rodada com falha: $t $level $rep" | tee -a "$DIR/failures.log"
      sleep 5
    done
  done
done

docker compose --profile go-opt --profile jvm-opt --profile native-opt --profile rust-opt \
  --profile native-g1 --profile jvm-zgc --profile tools down >/dev/null 2>&1
.venv/bin/python report/generate.py "$DIR"
echo "concluído: $DIR"
