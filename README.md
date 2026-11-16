# Benchmark de I/O: Java (JVM e Native Image), Go, Rust e Python

## Objetivo

Comparar o custo de **esperar I/O**. Cada requisição recebida chama uma API externa com **5s de latência fixa** e devolve a resposta, sem trabalho de CPU no handler. O que muda entre os alvos é quanto cada plataforma gasta em memória, CPU e latência adicional para manter milhares de chamadas paradas ao mesmo tempo.

**A página com todos os resultados está em [`docs/index.html`](docs/index.html).** Ela reúne as cinco rodadas completas, a explicação dos dois modos de carga e o detalhamento da migração do Java para Jetty, com links para o relatório completo de cada rodada.

| Trilha | Comparativos | Onde está |
|---|---|---|
| Padrão | **A:** Go (Fiber) vs Java (Spring Boot com virtual threads) na JVM. **B:** Go vs o mesmo Java em Native Image. **C:** Go vs Rust (Axum com reqwest) | Este README |
| Otimizada | **D a G:** cada plataforma, padrão vs otimizada. **H a J:** otimizados entre si. **K:** JVM com G1 vs ZGC. **L:** Native com Serial vs G1 | [`opt/README.md`](opt/README.md) e [Java otimizado: do Tomcat ao Jetty](#java-otimizado-do-tomcat-ao-jetty) |
| Python | **M:** cinco pilhas Python, com Go como controle | [`python/README.md`](python/README.md) |

- **Métricas:** startup, latência, throughput, memória e CPU.
- **Carga por VUs:** 1.000, 5.000 e 10.000 usuários virtuais simultâneos, com um alvo por vez em Docker Compose.
- **Carga por taxa:** 100 req/s constantes nos 10 alvos Java, Go e Rust, padrão e otimizados. Veja [Modos de carga](#modos-de-carga-vus-e-taxa).
- **Limites:** 2 vCPU e 1 GB em todos os alvos, sem exceção.

## Versões

Verificadas em 02/11/2026 nos registries e no Maven Central. As versões do Python, verificadas em 03/11/2026, estão em [`python/README.md`](python/README.md).

| Componente | Versão | Imagem ou fonte |
|---|---|---|
| Go | 1.27.3 | `golang:1.27.3` |
| Fiber | v3.6.1 | módulo Go |
| fasthttp | v1.77.0 | módulo Go |
| Spring Boot | 4.1.2 | Maven Central (4.2 ainda em RC1) |
| Servidor HTTP do Java | Tomcat 11.0.27 na trilha padrão, Jetty 12.1.14 na otimizada | gerenciados pelo Spring Boot |
| JDK da variante JVM | 27 (Temurin 27+35) | `eclipse-temurin:27-jre`, build com `maven:3.10.0-eclipse-temurin-27` |
| Native Image | GraalVM CE 25.4.4.1.1, JDK 25.0.4.1 | `ghcr.io/graalvm/native-image-community:25i4-25.0.4.1.1-ol9` |
| Native Image com G1 | Oracle GraalVM para JDK 25, licença GFTC | `container-registry.oracle.com/graalvm/native-image:25-ol9` |
| Rust | 1.99.1 | `rust:1.99.1-slim-bookworm` |
| Axum, hyper, reqwest, Tokio | 0.8.9, 1.12.0, 0.13.5, 1.54.1 | crates.io, com `Cargo.lock` |
| mimalloc (Rust otimizado) | 0.1.52 | crates.io |
| Python | 3.15.2 | `python:3.15.2-slim-bookworm` |
| k6 | 2.3.0 | `grafana/k6:2.3.0` |

### Nota sobre o JDK do Native Image

**Não existe GraalVM para JDK 27** na data da verificação: a imagem e os releases da GraalVM CE terminam no JDK 25. Por isso o Java é compilado com `java.version=25`, para o código ser igual nas duas variantes, e:

- a variante **JVM** roda esse bytecode no **JDK 27**;
- a variante **Native Image** é gerada com o **JDK 25**.

Os comparativos entre JVM e Native, portanto, não comparam só JVM com compilação nativa: a versão do JDK e o coletor também são diferentes.

### Coletor de lixo e heap

| Variante | GC | Heap máximo | Como foi verificado |
|---|---|---|---|
| `java-jvm` (JDK 27, 2 vCPU / 1 GB) | G1 | 75% do limite (768 MiB) | `-XX:+PrintFlagsFinal`: `UseG1GC = true`, `MaxHeapSize = 805306368` |
| `java-native` (GraalVM CE) | Serial | 80% do limite (padrão) | Saída do build: `Garbage collector: Serial GC (max heap size: 80% of RAM)` |
| `java-jvm-opt` | G1 | 70% do limite | `-XX:+PrintCommandLineFlags`: `MaxHeapSize=751619276` |
| `java-jvm-zgc` | ZGC | 60% do limite | `-XX:+PrintCommandLineFlags`: `MaxHeapSize=644245094` |
| `java-native-opt` (GraalVM CE) | Serial, com `-Xmn400m` | 80% do limite (padrão) | `command` no `docker-compose.yml` |
| `java-native-g1` (Oracle GraalVM) | G1 | 70% do limite | `-XX:MaxRAMPercentage=70` no `ENTRYPOINT`. Sem ele, o padrão é 25% |

O G1 do Native Image só existe na edição Oracle GraalVM. A GraalVM CE oferece Serial e Epsilon.

## Arquitetura

```
k6 (4 vCPU) ──> alvo (2 vCPU / 1 GB) ──> mock-api (4 vCPU / 2 GB, espera 5s)
```

Todos os containers ficam na rede `bench`. O k6 fala direto com o alvo pela rede do Docker, e só a medição de startup usa as portas publicadas.

| Trilha | Alvo | Profile do Compose | Porta |
|---|---|---|---|
| Padrão | `go-fiber` | `go` | 8081 |
| Padrão | `java-jvm` | `jvm` | 8082 |
| Padrão | `java-native` | `native` | 8083 |
| Padrão | `rust-axum` | `rust` | 8084 |
| Otimizada | `go-fiber-opt` | `go-opt` | 8085 |
| Otimizada | `java-jvm-opt` | `jvm-opt` | 8086 |
| Otimizada | `java-native-opt` | `native-opt` | 8087 |
| Otimizada | `rust-axum-opt` | `rust-opt` | 8088 |
| Otimizada | `java-native-g1` | `native-g1` | 8089 |
| Otimizada | `java-jvm-zgc` | `jvm-zgc` | 8090 |
| Python | `py-fastapi` | `py-fastapi` | 8091 |
| Python | `py-aiohttp` | `py-aiohttp` | 8092 |
| Python | `py-flask-gevent` | `py-flask-gevent` | 8093 |
| Python | `py-flask-threads` | `py-flask-threads` | 8094 |
| Python | `py-fastapi-aiohttp` | `py-fastapi-aiohttp` | 8095 |

Todos os alvos têm o mesmo contrato:

- `GET /health` retorna `200 ok`, sem Actuator, para não pesar no startup;
- `GET /api/io` chama `UPSTREAM_URL` por HTTP/1.1 e devolve o JSON recebido, de 35 bytes. Falha ao chamar a API externa retorna 502.

## Ajustes da trilha padrão

Só foram retirados limites artificiais. Nenhum alvo padrão foi otimizado para melhorar o próprio resultado.

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

Os ajustes da trilha Python, como 2 workers por alvo e pools de conexão sem limite, estão em [`python/README.md`](python/README.md).

## Trilha otimizada

Mesmo contrato, mesma carga e mesmos limites. Os alvos padrão continuam intactos, e cada ajuste veio de uma medição. As rodadas de diagnóstico estão em `results/diagnostico-opt/`.

| Alvo | O que muda em relação ao padrão |
|---|---|
| `go-fiber-opt` | Buffers de leitura e escrita de 2 KiB no Fiber e no cliente fasthttp, em vez de 4 KiB por conexão; `GOMEMLIMIT=900MiB` |
| `rust-axum-opt` | `hyper` direto no lugar do `reqwest`, buffer de leitura fixo de 2 KiB, `mimalloc` com `MIMALLOC_PURGE_DELAY=0` e `MIMALLOC_ARENA_EAGER_COMMIT=0`, LTO `fat`, `codegen-units=1`, `panic=abort` |
| `java-jvm-opt` | Jetty no lugar do Tomcat, com os ajustes da próxima seção, Compact Object Headers, AOT Cache, heap de 70% e G1 |
| `java-jvm-zgc` | Igual a `java-jvm-opt`, com ZGC, heap de 60% e AOT Cache treinado com ZGC |
| `java-native-opt` | Mesmo código Jetty, GraalVM CE, Serial GC e `-Xmn400m` |
| `java-native-g1` | Mesmo código Jetty, Oracle GraalVM com `--gc=G1`, `distroless/cc` e heap de 70% |

## Java otimizado: do Tomcat ao Jetty

### Por que trocar o servidor

Com Tomcat, a JVM esgotava 1 GB com 10.000 VUs. Para saber onde a memória ia, o alvo padrão rodou com 4 GB e teve o heap inspecionado com `jmap -histo` (`results/diagnostico-opt/histo/`). Com 10.000 conexões, havia 329 MB em 40.247 arrays `char[]`, cerca de 32,9 KB por conexão, e 758 MB em `byte[]`, além de cerca de 300 mil objetos `ByteChunk`, `CharChunk` e `MessageBytes` de cada tipo. A geração old do G1 ocupava cerca de 1.330 MiB, mais que o heap inteiro disponível em 1 GB (768 MiB). Não há propriedade do Tomcat que reduza esses `char[]` por conexão.

### Como a configuração chegou ao resultado

Diagnósticos de 60 s com 10.000 VUs e uma repetição, fora das medianas. A memória é o pico do container na janela medida.

| Etapa | Diretório em `results/diagnostico-opt/` | Configuração | Limite | req/s (de 2.000) | Erros | Overhead p99 | Pico | O que mostrou |
|---|---|---|---|---|---|---|---|---|
| 1 | raiz | Tomcat, como no alvo padrão | 4 GB | 1.941,7 | 0% | 732,0 ms | 3.344 MiB | O heap vivo não cabe em 1 GB |
| 2 | `iter1` | Jetty com os padrões, sem `JettyConfig` | 1 GB | 0,0 | 100% | - | 610 MiB | Timeouts sem OOM: o `VirtualThreadPool` aceita 200 tarefas simultâneas, no máximo 40 req/s com 5 s de espera |
| 3 | `iter2-jvm` | + `VirtualThreadPool(20000)` | 1 GB | 0,0 | 100% | - | 1.023 MiB | OOM kill e `OutOfMemoryError` |
| 4 | `iter3-jetty-4g` | Mesma configuração, com 4 GB para medir | 4 GB | 1.993,0 | 0% | 415,5 ms | 3.290 MiB | 984 MB de `char[]` no cache de cabeçalhos, cerca de 98 KB por conexão |
| 5 | `iter4-jetty-1g` | + `headerCacheSize=0` | 1 GB | 1.987,4 | 0% | 85,0 ms | 1.004 MiB | Cabe e atende, a 20 MiB do limite, com heap de 75% |
| 6 | `iter5-jvm70` | + heap de 70% | 1 GB | 2.000,0 | 0% | 66,7 ms | 951 MiB | Configuração final do `java-jvm-opt` |

### Cada mudança, arquivo por arquivo

Os arquivos estão em `opt/java-spring/`.

| Arquivo | Mudança | Padrão | Usado | Motivo e efeito medido |
|---|---|---|---|---|
| `pom.xml` | Exclui `spring-boot-starter-tomcat` de `spring-boot-starter-web` e adiciona `spring-boot-starter-jetty` | Tomcat | Jetty | O Tomcat fixa cerca de 32 KB de `char[]` por conexão, sem ajuste |
| `JettyConfig.java` | `factory.setThreadPool(new VirtualThreadPool(20000))` | 200 tarefas simultâneas | 20.000 | Com 5 s de espera, 200 tarefas dão no máximo 40 req/s. Com 10.000 VUs, todas as requisições estouraram o timeout de 30 s do k6 |
| `JettyConfig.java` | `HttpConfiguration.setHeaderCacheSize(0)` em cada conector, via `addServerCustomizers` | cache por conexão | desligado | Com o cache, 984 MB de `char[]` com 10.000 conexões. Sem ele, o processo cabe em 1 GB |
| `application.properties` | `server.max-http-request-header-size=2KB` | 8 KB | 2 KB | Mesmo limite do Go otimizado, com menos buffer por conexão |
| `application.properties` | `server.jetty.max-http-response-header-size=2KB` | 8 KB | 2 KB | Idem, na resposta |
| `application.properties` | `server.jetty.connection-idle-timeout=60s` | 30 s (Jetty) | 60 s | Conexões ociosas duram o mesmo que o keep-alive de 60 s dos outros alvos |
| `application.properties` | Remove `server.tomcat.*` | - | - | `max-connections`, `accept-count`, `max-keep-alive-requests` e `keep-alive-timeout` não se aplicam ao Jetty |
| `HttpClientConfig.java` | `System.setProperty("jdk.httpclient.bufsize", "2048")` | 16 KiB por conexão | 2 KiB | O cliente HTTP do JDK guarda um buffer por conexão com a mock-api. Precisa ser definido antes do primeiro uso do `HttpClient`, que lê o valor uma vez |
| `HttpClientConfig.java` | `System.setProperty("jdk.httpclient.keepalive.timeout", "60")` | 30 s | 60 s | Mantém as conexões com a mock-api pelo mesmo tempo dos outros alvos |
| `Dockerfile.jvm` | `-XX:+UseCompactObjectHeaders` | desligado | ligado | Cabeçalho de objeto menor. O efeito isolado não foi medido |
| `Dockerfile.jvm` | AOT Cache: JAR extraído com `-Djarmode=tools extract`, treino no build com `-XX:AOTCacheOutput` e `-Dspring.context.exit=onRefresh`, execução com `-XX:AOTCache` | sem cache | `/opt/app/app.aot` | Startup de 2.319 para 1.156 ms, imagem de 512,6 para 638,9 MB. O treino precisa usar a mesma JVM e as mesmas flags da execução |
| `Dockerfile.jvm` | `-XX:MaxRAMPercentage=70` | 75% | 70% | Com 75%, o pico chegou a 1.004 MiB. Com 70%, sobra mais espaço fora do heap, e a cauda melhorou |
| `Dockerfile.zgc` | `-XX:+UseZGC`, `-XX:MaxRAMPercentage=60` e AOT Cache treinado com ZGC | G1, 75% | ZGC, 60% | Sem AOT Cache, o ZGC foi encerrado pelo kernel com 10.000 VUs, com heap de 70% e de 60% |
| `docker-compose.yml` | `command: ["-Xmn400m"]` em `java-native-opt` | geração jovem automática | 400 MB | Nos diagnósticos, melhorou throughput e cauda com 5.000 VUs. Com 10.000 VUs, nenhum tamanho levou o Serial a 95% do ideal |
| `Dockerfile.native-g1` | Oracle GraalVM, `NATIVE_IMAGE_OPTIONS=--gc=G1`, `distroless/cc`, `-XX:MaxRAMPercentage=70` | Serial, 80% | G1, 70% | Com o heap padrão do G1 (25%), `OutOfMemoryError` com 10.000 VUs. O binário precisa da `libgcc_s`, ausente no `distroless/base` |

O `JettyConfig` usa `@Order(Ordered.LOWEST_PRECEDENCE)` para ser aplicado depois da configuração automática do Spring Boot, que também define o pool quando `spring.threads.virtual.enabled=true`:

```java
@Bean
@Order(Ordered.LOWEST_PRECEDENCE)
WebServerFactoryCustomizer<JettyServletWebServerFactory> jettyLimits() {
    return factory -> {
        factory.setThreadPool(new VirtualThreadPool(20000));
        factory.addServerCustomizers(server -> {
            for (var connector : server.getConnectors()) {
                var http = connector.getConnectionFactory(HttpConnectionFactory.class);
                if (http != null) {
                    http.getHttpConfiguration().setHeaderCacheSize(0);
                }
            }
        });
    };
}
```

### O que estes ajustes custam

- **Cabeçalhos:** o limite de 2 KiB serve para este teste, mas pode rejeitar requisições reais com cookies ou tokens grandes. O mesmo vale para o Go otimizado.
- **Cache de cabeçalhos:** desligá-lo pode custar CPU na leitura dos cabeçalhos. Esse efeito não foi medido isoladamente.
- **Concorrência:** com `VirtualThreadPool(20000)`, o servidor aceita até 20.000 tarefas simultâneas. Se um limite for necessário em produção, ele precisa vir de outro lugar.
- **Respostas maiores:** o teste devolve 35 bytes. Buffers de 2 KiB podem custar mais com corpos grandes.
- **Comparabilidade:** o Java otimizado não é a mesma aplicação com outras flags, porque o servidor HTTP mudou. O Native com G1 também muda de distribuição, com licença própria.

## Metodologia

**Startup** (`scripts/startup.py`, 10 execuções por padrão). O container é recriado a cada execução, e o início é feito pela API do Docker, porque a CLI adicionaria centenas de ms.

- *Tempo até ficar pronto:* do start até o primeiro `/health` com 200, com poll a cada 5 ms a partir do host. Inclui o custo do Docker.
- *Autodeclarado:* lido dos logs. No Java é o `process running for`. No Go, no Rust e no Python, não inclui o início do runtime ou dos imports, então não é comparável.
- *1ª requisição:* duração da primeira chamada a `/api/io` menos os 5.000 ms.
- *Memória parada:* lida 5s depois da primeira requisição.

### Modos de carga: VUs e taxa

O script `loadtest/io.js` tem dois modos, escolhidos por `MODE`.

Na **carga por VUs** (`MODE=vus`, o padrão, executor `constant-vus`), cada usuário virtual chama `/api/io`, espera a resposta e chama de novo, sem pausa. Como a mock-api leva 5 s, o throughput ideal é VUs / 5: 1.000 VUs dão 200 req/s, 5.000 dão 1.000 e 10.000 dão 2.000, e o alvo sempre tem tantas chamadas paradas quanto VUs. É um modelo fechado: quando o alvo atrasa, cada VU demora mais para repetir e o throughput cai sozinho, sem formar fila. Foi o que aconteceu com o Native com 5.000 VUs na trilha padrão: pausas de GC levaram a mediana a 5,67 s, e 5.000 / 5,67 s dá cerca de 880 req/s, perto dos 866,6 medidos, com 0 erros. Cada VU começa com um atraso aleatório de até 5 s, para as chamadas não chegarem em ondas.

Na **carga por taxa** (`MODE=rate`, executor `constant-arrival-rate`), o nível é a taxa em req/s, mantida mesmo se o alvo ficar lento. É um modelo aberto, como o tráfego que chega de fora num serviço real: se o alvo atrasar, as chamadas se acumulam em vez de diminuir. Com **100 req/s** e 5 s de espera, ficam cerca de **500 chamadas em andamento** (100 × 5), metade das 1.000 do menor nível por VUs. O k6 pré-aloca 6 vezes a taxa em VUs (600) e pode chegar a 40 vezes (4.000). O que passar disso é contado em `dropped_iterations` e aparece no relatório como iterações descartadas. Nesse modo, o req/s ideal é a própria taxa, e o `STARTUP_RUNS=0` pula a medição de startup, que não depende do modo de carga.

A rodada de 100 req/s não mede capacidade, porque todos os alvos sobram. Ela mostra o custo em carga leve e estável, e se as otimizações feitas para 10.000 VUs pioram algo quando a carga é baixa.

### Latência e throughput

Com 30s de warm-up e 180s medidos, nos dois modos.

- Só contam requisições **iniciadas dentro da janela medida**.
- Status diferente de 200 conta como erro e não entra na latência. Falhas de transporte, como timeout de 30 s, são contadas à parte.
- `req/s real` conta só respostas 200. `req/s ideal` é VUs / 5 no modo por VUs e a própria taxa no modo por taxa.
- *Overhead p99* é o p99 menos 5.000 ms.
- `http_req_duration` não inclui o tempo de conexão, por isso `http_req_blocked` e `http_req_connecting` são registrados à parte. Esses dois abrangem o teste inteiro, inclusive o warm-up.

### Memória e CPU

`scripts/collect_stats.py` coleta uma amostra por segundo, pela API do Docker, recortada pela janela medida.

- *Memória:* `usage - inactive_file`.
- *CPU %:* `cpu_delta / system_delta * online_cpus * 100`. 100% equivale a 1 core, e o máximo do alvo é 200%.
- *CPU-segundos:* diferença do contador acumulado de CPU, que não depende da taxa de amostragem.
- *CPU-s por 1.000 requisições:* a medida de eficiência mais direta, porque desconta o throughput. Conta só respostas 200.
- *OOM:* `kill` quando o kernel encerra o processo (`.State.OOMKilled` ou, com vários workers, o `oom_kill` de `memory.events` do cgroup); `heap` quando o log tem `OutOfMemoryError` e o container continua de pé.

**Agregação.** O valor final de cada célula é a **mediana das repetições**. A ordem dos alvos gira a cada repetição.

**Integridade.** OOM ou queda de throughput dentro do limite de 1 GB é resultado, não erro a corrigir. Mock-api ou k6 saturados invalidam a rodada. Rodadas ruins não são apagadas nem substituídas.

## Pré-requisitos

- Docker com Compose v2, com socket `unix://`, e Python 3.
- Recomendado: 16 vCPU e 32 GB de RAM. Mínimo: 12 CPUs e 16 GB livres para o Docker.
- O build do Native Image atingiu 3,68 GiB de pico de RSS nesta máquina.

## Comandos

```bash
# Benchmark completo da trilha padrão (cerca de 2h30)
scripts/run-all.sh

# Validação rápida
REPS=1 LEVELS=1000 DURATION=60 STARTUP_RUNS=3 scripts/run-all.sh

# Teste de limite
REPS=1 LEVELS=10000 DURATION=60 STARTUP_RUNS=1 scripts/run-all.sh

# Só alguns alvos
TARGETS="go-fiber java-jvm" scripts/run-all.sh

# Trilha otimizada, carga por VUs
TARGETS="go-fiber-opt java-jvm-opt java-jvm-zgc java-native-opt java-native-g1 rust-axum-opt" scripts/run-all.sh

# Carga constante de 100 req/s nos 10 alvos Java, Go e Rust
MODE=rate LEVELS=100 STARTUP_RUNS=0 \
TARGETS="go-fiber java-jvm java-native rust-axum go-fiber-opt java-jvm-opt java-jvm-zgc java-native-opt java-native-g1 rust-axum-opt" \
scripts/run-all.sh

# Trilha Python, com Go como controle
TARGETS="go-fiber py-fastapi py-fastapi-aiohttp py-aiohttp py-flask-gevent py-flask-threads" scripts/run-all.sh

# Retomada de uma rodada interrompida, com os mesmos alvos e a mesma ordem
TARGETS="..." scripts/resume.sh results/<timestamp>

# Rodada isolada e relatório de um diretório existente
scripts/load.sh go-fiber 1000 1 results/teste
.venv/bin/python report/generate.py results/<timestamp>

# Relatório com rodadas de referência para os alvos ausentes
.venv/bin/python report/generate.py results/<timestamp> results/<referência> ...

# Página consolidada em docs/index.html
.venv/bin/python report/site.py
```

Variáveis de `run-all.sh`, com os padrões: `TARGETS="go-fiber java-jvm java-native rust-axum"`, `LEVELS="1000 5000 10000"`, `REPS=3`, `WARMUP=30`, `DURATION=180`, `STARTUP_RUNS=10`, `MODE=vus`. Com `MODE=rate`, `LEVELS` passa a ser a taxa em req/s.

## Arquivos gerados

Em `results/<timestamp>/`:

| Arquivo | Conteúdo |
|---|---|
| `report.html`, `report.md`, `charts/*.png` | Relatório e gráficos. O HTML traz as imagens embutidas |
| `analise.md` | Análise escrita à mão, incluída no relatório quando existe |
| `config.json`, `docker-info.json` | Parâmetros, inclusive `MODE`, e ambiente da execução |
| `startup-<alvo>.json` | Execuções de startup, mediana, p90, mínimo, máximo e tamanho da imagem |
| `k6-<alvo>-<nível>-<rep>.json` | Resumo de latência e throughput de cada rodada, com `mode` e `dropped_iterations` |
| `stats-<alvo>-<nível>-<rep>-<container>.csv` | Amostras de CPU e memória de alvo, mock-api e k6 |
| `oom-<alvo>-<nível>-<rep>.txt` | Valor de `.State.OOMKilled` do alvo. O OOM de heap, que não encerra o container, é detectado pelo log |
| `memevents-<alvo>-<nível>-<rep>.txt` | `memory.events` do cgroup, com o `oom_kill` de workers encerrados sem derrubar o container |
| `logs/` | Logs de build, alvos, mock-api e k6 |
| `docker-oom-events.log`, `host.csv` | Eventos de OOM do Docker; memória livre e conntrack do host a cada 5s |
| `failures.log` | Rodadas que falharam, quando houver |
| `interrompidas/`, `retomada.log` | Rodadas cortadas por interrupção e o registro da retomada, quando houver |

Em `docs/`:

| Arquivo | Conteúdo |
|---|---|
| `index.html` | Página consolidada, gerada por `report/site.py` a partir de `results/` |
| `resultados-<timestamp>.html` | Cópia do `report.html` de cada rodada completa |
| `analise-native-vs-jvm.md`, `analise-startup.md` | Análises da trilha padrão |
| `prompt-reexecucao.md` | Prompt para reaplicar o benchmark |

## Rodadas

Todas na mesma máquina: 16 vCPU x86_64, 30,8 GiB, Ubuntu 24.04.5 LTS, kernel 7.0.0-1014-aws, Docker 29.9.2.

| Rodada | O que mede | Alvos | Carga | Relatório |
|---|---|---|---|---|
| [`20261102-005118`](results/20261102-005118/report.md) | Trilha padrão, comparativos A e B | `go-fiber`, `java-jvm`, `java-native` | 1.000, 5.000 e 10.000 VUs | [`docs/resultados-20261102-005118.html`](docs/resultados-20261102-005118.html) |
| [`20261102-173102`](results/20261102-173102/report.md) | Rust, comparativo C | `go-fiber`, `rust-axum` | 1.000, 5.000 e 10.000 VUs | [`docs/resultados-20261102-173102.html`](docs/resultados-20261102-173102.html) |
| [`20261102-215054`](results/20261102-215054/report.md) | Trilha otimizada, comparativos D a L | 6 alvos otimizados | 1.000, 5.000 e 10.000 VUs | [`docs/resultados-20261102-215054.html`](docs/resultados-20261102-215054.html) |
| [`20261102-195930`](results/20261102-195930/report.md) | Carga constante | 10 alvos Java, Go e Rust | 100 req/s | [`docs/resultados-20261102-195930.html`](docs/resultados-20261102-195930.html) |
| [`20261103-175032`](results/20261103-175032/report.md) | Trilha Python, comparativo M | `go-fiber` e 5 pilhas Python | 1.000, 5.000 e 10.000 VUs | [`docs/resultados-20261103-175032.html`](docs/resultados-20261103-175032.html) |

Todas com 3 repetições, 30 s de warm-up e 180 s medidos. À parte, sem entrar nas medianas: validações e testes de limite em `20261102-003704`, `20261102-004409`, `20261102-172609`, `20261102-172853`, `20261102-195236` (100 req/s com 30 s medidos) e `20261103-162014` (interrompido), e diagnósticos em `results/diagnostico-gc`, `diagnostico-native-2g`, `diagnostico-opt` e `diagnostico-python`.

## Como ler os resultados

1. Comece pela seção **Sanidade do ambiente** do relatório da rodada. Mock-api ou k6 acima de 320% de CPU, erros, throughput abaixo de 95% do ideal e OOM são sinalizados ali.
2. Confira se o `req/s real` está perto do ideal. Uma latência baixa com throughput baixo não significa que o alvo aguentou a carga.
3. Compare o **overhead p99**, não o p99 bruto: os 5.000 ms são da API externa.
4. Compare **CPU-s por 1.000 requisições** para eficiência e **memória de pico** contra o limite de 1 GB.
5. A memória da JVM reflete também o tamanho que o heap pode ocupar: o G1 usa o espaço disponível antes de coletar, então ela não é uma medida do mínimo necessário.
6. No modo por taxa, confira também as **iterações descartadas**: acima de zero, o k6 não conseguiu manter a taxa pedida.

## Resultado

A análise completa, com tabelas e gráficos de todas as rodadas, está em [`docs/index.html`](docs/index.html). Em resumo, com 2 vCPU e 1 GB:

- **Trilha padrão:** só Go e Rust atenderam aos três níveis. Com 10.000 VUs, o Go fez 1.999,6 de 2.000 req/s com 407 MiB de pico. As duas variantes Java esgotaram a memória com 10.000 VUs, e o Native Image ficou abaixo do throughput ideal já com 5.000 VUs, por causa das pausas do Serial GC.
- **Rust:** atendeu aos três níveis com a mesma latência do Go, mas com cerca de 50% mais memória de pico e de 11% a 27% mais CPU por requisição. Esse resultado vale para esta stack, Axum com reqwest, não para a linguagem.
- **Trilha otimizada:** todos os alvos atenderam a 10.000 VUs em 1 GB, sem erros, inclusive o Java, depois da troca do Tomcat pelo Jetty. A JVM com G1 fez 1.992,5 req/s com 953 MiB de pico, ainda 2,8 vezes a memória e 5,4 vezes a CPU por requisição do Go otimizado. O Native com Serial ficou em 82,5% do ideal; com G1, em 99,8%.
- **100 req/s:** os 10 alvos atenderam sem erros e sem iterações descartadas. A memória de pico foi de 24,8 MiB (Go otimizado) a 430,9 MiB (JVM padrão), e a JVM com Jetty usou 38% menos memória que com Tomcat. Com essa carga leve, o Java otimizado gastou mais CPU por requisição que o padrão.
- **Python:** só o aiohttp puro acompanhou o Go com 10.000 VUs, com 3,2 vezes a CPU por requisição. FastAPI + httpx teve 100% de erros já com 5.000 VUs, por causa do pool de conexões do `httpcore`.
