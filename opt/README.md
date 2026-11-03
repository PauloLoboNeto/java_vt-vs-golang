# Trilha otimizada

Mesmo contrato, mesma carga e mesmos limites de **2 vCPU e 1 GB** dos alvos padrão, que continuam intactos. Cada ajuste veio de uma medição, e as rodadas de diagnóstico estão em `results/diagnostico-opt/`.

| Alvo | Ajustes | Por quê |
|---|---|---|
| `go-fiber-opt` | Buffers de 2 KiB no Fiber e no fasthttp, `GOMEMLIMIT=900MiB` | O padrão é 4 KiB por conexão. Cabeçalhos ficam limitados a 2 KiB |
| `rust-axum-opt` | `hyper` no lugar do `reqwest`, buffer de leitura de 2 KiB, `mimalloc` ajustado, LTO, `codegen-units=1`, `panic=abort` | O `hyper` direto trouxe a maior parte do ganho. O `mimalloc` nos padrões usou mais memória que a glibc |
| `java-jvm-opt` | Jetty no lugar do Tomcat, `jdk.httpclient.bufsize=2048`, Compact Object Headers, AOT Cache, heap de 70%, G1 | O Tomcat fixa cerca de 32 KB de `char[]` por conexão, sem ajuste |
| `java-jvm-zgc` | Igual a `java-jvm-opt`, com ZGC e heap de 60% | Compara o coletor. Em diagnósticos sem AOT Cache, foi encerrado pelo kernel com 10.000 VUs. Na rodada completa, não, mas chegou a 1.016 MiB |
| `java-native-opt` | Mesmo código Java, com GraalVM CE, Serial GC e `-Xmn400m` | A CE só oferece Serial e Epsilon |
| `java-native-g1` | Mesmo código Java, com Oracle GraalVM, G1 e heap de 70% | Outra distribuição, com licença GFTC |

## Ajustes obrigatórios ao usar Jetty

Os dois vieram de rodadas com 10.000 VUs e valem para qualquer projeto com muitas conexões simultâneas:

- **Limite do `VirtualThreadPool`:** o padrão é de 200 tarefas simultâneas. Com 5 s de espera, isso dá só 40 req/s.
- **`headerCacheSize`:** o cache de cabeçalhos é por conexão e consome cerca de 100 KB em cada uma. Aqui está desligado.

## O que estes ajustes custam

- **Cabeçalhos:** os limites de 2 KiB são adequados a este teste, mas podem rejeitar requisições reais com cookies ou tokens grandes.
- **Corpo das respostas:** o teste usa só 35 bytes. Buffers pequenos podem custar mais com respostas maiores.
- **Comparabilidade:** o Java passou a usar outro servidor HTTP, então o ganho não é só de configuração da JVM.

## Resultado

Com 10.000 VUs, todos os alvos atenderam sem erros em 1 GB, mas o Native com Serial ficou em 82,5% do ideal. A análise está em [`results/20261102-215054`](../results/20261102-215054/report.md), e a carga de 100 req/s, em [`results/20261102-195930`](../results/20261102-195930/report.md).

## Como executar

```bash
# Carga por VUs
TARGETS="go-fiber-opt java-jvm-opt java-jvm-zgc java-native-opt java-native-g1 rust-axum-opt" scripts/run-all.sh

# Carga constante de 100 req/s
MODE=rate LEVELS=100 STARTUP_RUNS=0 scripts/run-all.sh

# Relatório com rodadas de referência para os alvos padrão
.venv/bin/python report/generate.py results/<timestamp> results/<referência> ...

# Retomada de uma rodada interrompida, com os mesmos alvos e a mesma ordem
TARGETS="..." scripts/resume.sh results/<timestamp>
```
