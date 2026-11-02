cd /home/ubuntu/projetos/benchmarks/java_vt-vs-golang
X=results/diagnostico-gc; mkdir -p $X
export WARMUP=30 DURATION=60
COMPOSE_FILE=docker-compose.yml:/tmp/diag/gc.yml scripts/load.sh java-native 5000 1 $X
COMPOSE_FILE=docker-compose.yml:/tmp/diag/gc.yml scripts/load.sh java-native 1000 1 $X
COMPOSE_FILE=docker-compose.yml:/tmp/diag/gc.yml scripts/load.sh java-jvm 5000 1 $X
Y=results/diagnostico-native-2g; mkdir -p $Y
COMPOSE_FILE=docker-compose.yml:/tmp/diag/gc2g.yml scripts/load.sh java-native 5000 1 $Y
docker compose --profile go --profile jvm --profile native --profile tools down >/dev/null 2>&1
