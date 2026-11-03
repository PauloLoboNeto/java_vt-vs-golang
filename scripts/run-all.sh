#!/usr/bin/env bash
# Executa o benchmark completo: build, startup, rodadas de carga e relatório.
set -uo pipefail
cd "$(dirname "$0")/.."

TARGETS="${TARGETS:-go-fiber java-jvm java-native rust-axum}"
LEVELS="${LEVELS:-1000 5000 10000}"
REPS="${REPS:-3}"
WARMUP="${WARMUP:-30}"
DURATION="${DURATION:-180}"
STARTUP_RUNS="${STARTUP_RUNS:-10}"
MODE="${MODE:-vus}"
export WARMUP DURATION MODE
export BENCH_UID="$(id -u)" BENCH_GID="$(id -g)"

TS="$(date -u +%Y%m%d-%H%M%S)"
DIR="results/$TS"
mkdir -p "$DIR/logs"
echo "resultados em $DIR"

# Eventos de OOM e memória do host ajudam a explicar anomalias depois da rodada.
BG=()
docker events --filter event=oom --format '{{.Time}} {{.Actor.Attributes.name}}' >"$DIR/docker-oom-events.log" &
BG+=($!)
(
  echo "ts_ms,mem_available_kb,conntrack_count"
  while true; do
    avail=$(awk '/MemAvailable/ {print $2}' /proc/meminfo)
    ct=$(cat /proc/sys/net/netfilter/nf_conntrack_count 2>/dev/null || echo 0)
    echo "$(date +%s%3N),$avail,$ct"
    sleep 5
  done
) >"$DIR/host.csv" &
BG+=($!)
trap 'kill "${BG[@]}" 2>/dev/null; wait 2>/dev/null' EXIT

profiles=()
for t in $TARGETS; do
  case "$t" in
    go-fiber) profiles+=(--profile go) ;;
    java-jvm) profiles+=(--profile jvm) ;;
    java-native) profiles+=(--profile native) ;;
    rust-axum) profiles+=(--profile rust) ;;
    go-fiber-opt) profiles+=(--profile go-opt) ;;
    java-jvm-opt) profiles+=(--profile jvm-opt) ;;
    java-native-opt) profiles+=(--profile native-opt) ;;
    rust-axum-opt) profiles+=(--profile rust-opt) ;;
    java-native-g1) profiles+=(--profile native-g1) ;;
    java-jvm-zgc) profiles+=(--profile jvm-zgc) ;;
    py-fastapi|py-fastapi-aiohttp|py-aiohttp|py-flask-gevent|py-flask-threads) profiles+=(--profile "$t") ;;
    *) echo "alvo desconhecido: $t" >&2; exit 2 ;;
  esac
done

# Builda só o necessário: o Native Image é caro e pode ficar de fora.
# shellcheck disable=SC2086
docker compose "${profiles[@]}" build --progress=plain mock-api $TARGETS >"$DIR/logs/build.log" 2>&1 || {
  echo "falha no build; veja $DIR/logs/build.log" >&2; exit 1; }

CFG_TARGETS="$TARGETS" CFG_LEVELS="$LEVELS" CFG_REPS="$REPS" CFG_STARTUP_RUNS="$STARTUP_RUNS" \
python3 - "$DIR" <<'PY'
import json, os, sys
sys.path.insert(0, "scripts")
import dockerapi
d = sys.argv[1]
json.dump({"info": dockerapi.info(), "version": dockerapi.version()},
          open(f"{d}/docker-info.json", "w"), indent=2)
json.dump({k: os.environ[k] for k in ("WARMUP", "DURATION", "MODE")} | {
    "TARGETS": os.environ["CFG_TARGETS"], "LEVELS": os.environ["CFG_LEVELS"],
    "REPS": os.environ["CFG_REPS"], "STARTUP_RUNS": os.environ["CFG_STARTUP_RUNS"],
}, open(f"{d}/config.json", "w"), indent=2)
PY

# STARTUP_RUNS=0 pula a medição de startup, que não depende do modo de carga.
[ "$STARTUP_RUNS" -gt 0 ] && for t in $TARGETS; do
  echo "== startup: $t"
  python3 scripts/startup.py "$t" "$STARTUP_RUNS" "$DIR/startup-$t.json" || \
    echo "startup falhou: $t" | tee -a "$DIR/failures.log"
done

read -r -a LIST <<<"$TARGETS"
N=${#LIST[@]}
for ((rep = 1; rep <= REPS; rep++)); do
  for level in $LEVELS; do
    # A ordem dos alvos gira a cada repetição, para nenhum correr sempre primeiro.
    for ((i = 0; i < N; i++)); do
      t=${LIST[$(((i + rep - 1) % N))]}
      echo "== carga: rep=$rep vus=$level alvo=$t ($(date -u +%H:%M:%S))"
      scripts/load.sh "$t" "$level" "$rep" "$DIR" || \
        echo "rodada com falha: $t $level $rep" | tee -a "$DIR/failures.log"
      sleep 5
    done
  done
done

docker compose --profile go --profile jvm --profile native --profile rust --profile go-opt --profile jvm-opt --profile native-opt --profile rust-opt --profile native-g1 --profile jvm-zgc --profile py-fastapi --profile py-fastapi-aiohttp --profile py-aiohttp --profile py-flask-gevent --profile py-flask-threads --profile tools down >/dev/null 2>&1

# Sem matplotlib o relatório sai só com as tabelas.
PY=python3
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv >/dev/null 2>&1 && .venv/bin/pip install -q -r report/requirements.txt >/dev/null 2>&1
fi
[ -x .venv/bin/python ] && PY=.venv/bin/python
"$PY" report/generate.py "$DIR"
echo "concluído: $DIR"
