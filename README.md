# Benchmark de I/O: Java com virtual threads, Go com Fiber e Rust com Axum

## Objetivo

Comparar o custo de **esperar I/O**. Cada requisição recebida chama uma API externa com **5s de latência fixa** e devolve a resposta, sem trabalho de CPU no handler. O que muda entre os alvos é quanto cada plataforma gasta em memória, CPU e latência adicional para manter milhares de chamadas paradas ao mesmo tempo.

- **Comparativo A:** Go (Fiber) vs Java (Spring Boot com virtual threads) na JVM.
- **Comparativo B:** Go (Fiber) vs o mesmo Java em Native Image.
- **Comparativo C:** Go (Fiber) vs Rust (Axum com reqwest).
- **Métricas:** startup, latência, memória e CPU.
- **Carga:** 1.000, 5.000 e 10.000 VUs simultâneos, com um alvo por vez em Docker Compose.

O resultado publicado está em [`docs/index.html`](docs/index.html).

## Versões

Verificadas em 02/11/2026 nos registries e no Maven Central.

| Componente | Versão | Imagem ou fonte |
|---|---|---|
| Go | 1.27.3 | `golang:1.27.3` |
| Fiber | v3.6.1 | módulo Go |
| fasthttp | v1.77.0 | módulo Go |
| Spring Boot | 4.1.2 | Maven Central (4.2 ainda em RC1) |
| JDK da variante JVM | 27 (Temurin 27+35) | `eclipse-temurin:27-jre`, build com `maven:3.10.0-eclipse-temurin-27` |
| Native Image | GraalVM CE 25.4.4.1.1, JDK 25.0.4.1 | `ghcr.io/graalvm/native-image-community:25i4-25.0.4.1.1-ol9` |
| Rust | 1.99.1 | `rust:1.99.1-slim-bookworm` |
| Axum, hyper, reqwest, Tokio | 0.8.9, 1.12.0, 0.13.5, 1.54.1 | crates.io, com `Cargo.lock` |
| k6 | 2.3.0 | `grafana/k6:2.3.0` |

### Nota sobre o JDK do Native Image

**Não existe GraalVM para JDK 27** na data da verificação: a imagem e os releases da GraalVM CE terminam no JDK 25. Por isso o Java é compilado com `java.version=25`, para o código ser igual nas duas variantes, e:

- a variante **JVM** roda esse bytecode no **JDK 27**;
- a variante **Native Image** é gerada com o **JDK 25**.

O comparativo B, portanto, não compara só JVM com compilação nativa: a versão do JDK também é diferente.

### Coletor de lixo real

| Variante | GC | Heap máximo | Como foi verificado |
|---|---|---|---|
| JVM (JDK 27, 2 vCPU / 1 GB) | G1 | 75% do limite (768 MiB) | `-XX:+PrintFlagsFinal`: `UseG1GC = true`, `MaxHeapSize = 805306368` |
| Native Image (GraalVM CE) | Serial | 80% do limite (padrão) | Saída do build: `Garbage collector: Serial GC (max heap size: 80% of RAM)` |

O G1 do Native Image só existe na edição Oracle GraalVM, e os percentuais de heap ficaram nos valores definidos e padrão de cada variante.

## Arquitetura

```
k6 (4 vCPU) ──> alvo (2 vCPU / 1 GB) ──> mock-api (4 vCPU / 2 GB, espera 5s)
                 go-fiber | java-jvm | java-native | rust-axum
```

Todos os containers ficam na rede `bench`. O k6 fala direto com o alvo pela rede do Docker, e só a medição de startup usa as portas publicadas (8081, 8082, 8083 e 8084).

Todos os alvos têm o mesmo contrato:

- `GET /health` retorna `200 ok`, sem Actuator, para não pesar no startup;
- `GET /api/io` chama `UPSTREAM_URL` e devolve o JSON recebido. Falha ao chamar a API externa retorna 502.

## Ajustes de configuração

| Ajuste | Onde | Motivo |
|---|---|---|
| `MaxConnsPerHost: 20000` | Go | O padrão de 512 conexões criaria um gargalo artificial |
| `server.tomcat.max-connections=20000` | Java | O padrão de 8192 cortaria o nível de 10.000 VUs |
| `server.tomcat.accept-count=10000` | Java | Fila de aceitação suficiente para a subida dos VUs |
| `server.tomcat.max-keep-alive-requests=-1` | Java | Sem encerrar conexões por contagem, como no Go |
| `server.tomcat.keep-alive-timeout=60s` | Java | Conexões sobrevivem aos 5s de espera, equivalente ao `MaxIdleConnDuration` do Go |
| `spring.threads.virtual.enabled=true` | Java | Atende cada requisição numa virtual thread |
| `HttpClient` com HTTP/1.1 e executor de virtual threads | Java | Mesmo protocolo do Go, sem tentativa de upgrade para HTTP/2 |
| `c.Response().SetBody(...)` em vez de `c.Send(...)` | Go | `Send` pode reter o buffer, que volta ao pool no `defer` |
| Backlog de 65535 no socket em vez de `TcpListener::bind` | Rust | O padrão de 1024 criaria um gargalo na subida dos VUs. O Go já usa o `somaxconn` |
| `pool_idle_timeout` de 60s e `http1_only` | Rust | Mesmos tempo de conexão ociosa e protocolo do Go. O reqwest não limita conexões por host |
| `strip = true`, sem LTO e com o alocador padrão | Rust | Equivale ao `-s -w` do Go, sem otimizações além do padrão |
| Tratamento de SIGTERM | Rust | Como PID 1, o processo ignoraria o sinal, e o Docker esperaria 10s para encerrá-lo |
| `-XX:MaxRAMPercentage=75` | JVM | Usa o limite de 1 GB do container de forma explícita |
| `nofile` 65535, `somaxconn` 65535, `ip_local_port_range` | Compose, em todos os alvos | Limites do sistema não podem interferir |
| Os mesmos ajustes em mock-api e k6 | Compose | Eles não podem ser o gargalo (não estavam na especificação original) |
| `libz.so.1` copiada do builder | `Dockerfile.native` | O binário depende dela, e nem `distroless/base` nem `distroless/cc` a trazem |
| `user:` do k6 igual ao dono do diretório | Compose | A imagem não roda como root e precisa gravar em `results/` |

Os limites de **2 vCPU e 1 GB** são iguais em todos os alvos e não são alterados.

## Metodologia

**Startup** (`scripts/startup.py`, 10 execuções por padrão). O container é recriado a cada execução, e o início é feito pela API do Docker, porque a CLI adicionaria centenas de ms.

- *Tempo até ficar pronto:* do start até o primeiro `/health` com 200, com poll a cada 5 ms a partir do host. Inclui o custo do Docker.
- *Autodeclarado:* lido dos logs. No Java é o `process running for`. No Go parte de uma variável de pacote, então não inclui o início do runtime e não é comparável.
- *1ª requisição:* duração da primeira chamada a `/api/io` menos os 5.000 ms.
- *Memória parada:* lida 5s depois da primeira requisição.

**Latência e throughput** (`loadtest/io.js`). Executor `constant-vus`, com 30s de warm-up e 180s medidos. Cada VU começa com um atraso aleatório de até 5s para evitar ondas sincronizadas.

- Só contam requisições **iniciadas dentro da janela medida**.
- Status diferente de 200 conta como erro e não entra na latência.
- `req/s real` conta só respostas 200. `req/s ideal` é VUs / 5.
- *Overhead p99* é o p99 menos 5.000 ms.
- `http_req_duration` não inclui o tempo de conexão, por isso `http_req_blocked` e `http_req_connecting` são registrados à parte. Esses dois abrangem o teste inteiro, inclusive o warm-up.

**Memória e CPU** (`scripts/collect_stats.py`). Uma amostra por segundo, pela API do Docker, recortada pela janela medida.

- *Memória:* `usage - inactive_file`.
- *CPU %:* `cpu_delta / system_delta * online_cpus * 100`. 100% equivale a 1 core, e o máximo do alvo é 200%.
- *CPU-segundos:* diferença do contador acumulado de CPU, que não depende da taxa de amostragem.
- *CPU-s por 1.000 requisições:* a medida de eficiência mais direta, porque desconta o throughput. Conta só respostas 200.

**Agregação.** O valor final de cada célula é a **mediana das repetições**. A ordem dos alvos gira a cada repetição.

**Integridade.** OOM ou queda de throughput dentro do limite de 1 GB é resultado, não erro a corrigir. Mock-api ou k6 saturados invalidam a rodada. Rodadas ruins não são apagadas nem substituídas.

## Pré-requisitos

- Docker com Compose v2, com socket `unix://`, e Python 3.
- Recomendado: 16 vCPU e 32 GB de RAM. Mínimo: 12 CPUs e 16 GB livres para o Docker.
- O build do Native Image atingiu 3,68 GiB de pico de RSS nesta máquina.

## Comandos

```bash
# Benchmark completo (cerca de 2h30)
scripts/run-all.sh

# Validação rápida
REPS=1 LEVELS=1000 DURATION=60 STARTUP_RUNS=3 scripts/run-all.sh

# Teste de limite
REPS=1 LEVELS=10000 DURATION=60 STARTUP_RUNS=1 scripts/run-all.sh

# Só alguns alvos
TARGETS="go-fiber java-jvm" scripts/run-all.sh

# Rodada isolada e relatório de um diretório existente
scripts/load.sh go-fiber 1000 1 results/teste
.venv/bin/python report/generate.py results/<timestamp>
```

Variáveis de `run-all.sh`, com os padrões: `TARGETS="go-fiber java-jvm java-native rust-axum"`, `LEVELS="1000 5000 10000"`, `REPS=3`, `WARMUP=30`, `DURATION=180`, `STARTUP_RUNS=10`.

## Arquivos gerados

Em `results/<timestamp>/`:

| Arquivo | Conteúdo |
|---|---|
| `report.html`, `report.md`, `charts/*.png` | Relatório e gráficos. O HTML traz as imagens embutidas |
| `analise.md` | Análise escrita à mão, incluída no relatório quando existe |
| `config.json`, `docker-info.json` | Parâmetros e ambiente da execução |
| `startup-<alvo>.json` | Execuções de startup, mediana, p90, mínimo, máximo e tamanho da imagem |
| `k6-<alvo>-<vus>-<rep>.json` | Resumo de latência e throughput de cada rodada |
| `stats-<alvo>-<vus>-<rep>-<container>.csv` | Amostras de CPU e memória de alvo, mock-api e k6 |
| `oom-<alvo>-<vus>-<rep>.txt` | Valor de `.State.OOMKilled` do alvo. O OOM de heap, que não encerra o container, é detectado pelo log |
| `logs/` | Logs de build, alvos, mock-api e k6 |
| `docker-oom-events.log`, `host.csv` | Eventos de OOM do Docker; memória livre e conntrack do host a cada 5s |
| `failures.log` | Rodadas que falharam, quando houver |

## Como ler os resultados

1. Comece pela seção **Sanidade do ambiente**. Mock-api ou k6 acima de 320% de CPU, erros, throughput abaixo de 95% do ideal e OOM são sinalizados ali.
2. Confira se o `req/s real` está perto do ideal. Uma latência baixa com throughput baixo não significa que o alvo aguentou a carga.
3. Compare o **overhead p99**, não o p99 bruto: os 5.000 ms são da API externa.
4. Compare **CPU-s por 1.000 requisições** para eficiência e **memória de pico** contra o limite de 1 GB.
5. A memória da JVM reflete também o tamanho que o heap pode ocupar: o G1 usa o espaço disponível antes de coletar, então ela não é uma medida do mínimo necessário.

## Resultado

A análise, as tabelas e os gráficos da rodada completa estão em [`docs/index.html`](docs/index.html). Em resumo, com 2 vCPU e 1 GB, só o Go atendeu aos três níveis. As duas variantes Java esgotaram a memória com 10.000 VUs. O Native Image ficou abaixo do throughput ideal já com 5.000 VUs, por causa das pausas do Serial GC.

O Rust foi medido à parte, com o Go como controle, na rodada [`results/20261102-173102`](results/20261102-173102/report.md). Ele também atendeu aos três níveis com a mesma latência do Go, mas com cerca de 50% mais memória de pico e de 11% a 27% mais CPU por requisição. Esse resultado vale para esta stack, Axum com reqwest, não para a linguagem.

A trilha otimizada, com carga por VUs e por taxa, está descrita em [`opt/README.md`](opt/README.md). Nela, todos os alvos atenderam a 10.000 VUs em 1 GB, sem erros, inclusive o Java, que falha na configuração padrão.
