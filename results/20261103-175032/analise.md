### Conclusões

- **Python atende 10.000 VUs em 2 vCPU e 1 GB, mas a escolha da pilha decide o resultado.** O aiohttp fez 1.999,4 de 2.000 req/s, sem erros e com overhead p99 de 2,7 ms. Com a mesma carga, FastAPI + httpx não entregou nenhuma resposta 200.
- **O aiohttp empatou com o Go em throughput e latência, e paga em CPU.** Com 10.000 VUs, o Go fez 1.999,5 req/s com overhead de 2,1 ms. O aiohttp gastou 3,2 vezes a CPU por requisição (0,185 contra 0,057 CPU-s por 1.000) e 13% menos memória de pico (353 contra 408 MiB). Com 1.000 VUs, a relação de memória se inverte: 85 MiB contra 46 MiB.
- **O colapso do FastAPI + httpx vem do cliente, não do FastAPI.** Com 5.000 e 10.000 VUs, ele teve 100% de erros nas 6 rodadas, com CPU em 200% e sem OOM. No diagnóstico de 60 s com 10.000 VUs, FastAPI com o cliente do aiohttp fez 1.980,5 req/s sem erros, e aiohttp como servidor com httpx fez 17,7 req/s. O perfil do cliente isolado concentra o tempo em `httpcore`, no `is_idle` chamado por `_assign_requests_to_connections`: cerca de 95 milhões de chamadas em 20 s, com 500 chamadas simultâneas. O código refaz uma lista de todas as conexões para cada conexão ociosa, um custo quadrático.
- **O httpx já custa caro antes de colapsar.** Com 1.000 VUs, FastAPI + httpx ainda atende, mas gasta 1,966 CPU-s por 1.000 requisições, 4,1 vezes o FastAPI com cliente aiohttp (0,485), e tem overhead p99 de 98,0 ms contra 2,5 ms. O ponto exato do colapso, entre 1.000 e 5.000 VUs, não foi medido.
- **FastAPI com cliente aiohttp é viável até 5.000 VUs sem custo de latência.** Com 5.000 VUs, teve overhead p99 de 2,7 ms. Com 10.000 VUs, ficou em 1.950,5 req/s (97,5% do ideal), com overhead de 897,6 ms e 537 MiB, contra 2,7 ms e 353 MiB do aiohttp puro.
- **gevent mantém o código síncrono, mas não aguenta 10.000 VUs em 1 GB.** Com 5.000 VUs, fez 980,9 req/s, com overhead de 573,3 ms. Com 10.000 VUs, fez 1.649,2 req/s (82,5%), com overhead de 3.187,4 ms, e o kernel encerrou de 2 a 4 workers em cada rodada.
- **Threads do sistema ainda funcionam até 5.000 VUs, com o maior consumo.** Com 5.000 VUs, fizeram 994,5 req/s, com overhead de 204,7 ms, 723 MiB e 1,403 CPU-s por 1.000. Com 10.000 VUs, ficaram em 808,4 req/s (40,4%), 3,98% de erros e de 35 a 39 workers encerrados pelo kernel por rodada.
- **Startup e memória parada ficam atrás do Go, sem chegar ao custo da JVM padrão.** O tempo até ficar pronto foi de 315 a 638 ms, contra 121 ms do Go. A memória parada foi de 47,7 a 113,3 MiB, contra 3,4 MiB, e as imagens têm de 239 a 268 MB, contra 20,3 MB.

### Limites destas conclusões

- **Cada alvo usa 2 workers.** Esse número acompanha os 2 vCPU. Outras contagens não foram testadas.
- **Os alvos só receberam ajustes de limites artificiais.** Pools, backlog, timeouts e keep-alive foram configurados para não criar gargalo. Nenhuma pilha Python foi otimizada como na trilha `opt/`, e não testamos stack menor nas threads, outros alocadores ou outras versões do httpx.
- **O perfil do httpx foi feito só no cliente, com `cProfile`, que deixa o programa mais lento.** Ele serve para atribuir onde o tempo vai, não para medir a velocidade. Os números de carga vêm dos alvos sem perfilador. O py-spy 0.4.3 não reconheceu o Python 3.15.
- **O teste usa uma resposta de 35 bytes, sem trabalho de CPU, sem banco e sem validação.** Em Python, o trabalho de CPU real disputa o mesmo event loop, e este teste não mede isso.
- **A comparação com Java e Rust é indireta.** Só o Go foi medido nesta rodada, e seus números repetem os da rodada `20261102-173102`: com 10.000 VUs, 1.999,5 req/s nas duas, overhead p99 de 2,1 e 2,2 ms e pico de 408 e 408 MiB.
- **Duas quedas não têm causa identificada.** No FastAPI com cliente aiohttp com 10.000 VUs e no gevent com 5.000 VUs, o overhead cresce sem CPU média saturada e sem desbalanceamento: as amostras por processo mostram os workers com CPU e descritores parecidos. Essas amostras cobrem só 10 s, então não descartam picos curtos.
- **Os números do gevent com 5.000 VUs variam.** O overhead p99 foi de 429,6 a 878,6 ms entre repetições de 180 s, e de cerca de 195 ms no diagnóstico de 30 s medidos.
- **Os OOM são contados no cgroup e incluem warm-up e fim da rodada.** O contador `oom_kill` soma 109 no Flask com threads e 8 no gevent. O `docker events` registrou 109 e 6, e o `State.OOMKilled` não os mostra, porque o container continua de pé. O contador é mais confiável que os eventos.
- **O autodeclarado não é comparável entre alvos.** No aiohttp, ele sai em cerca de 1 ms porque o gunicorn já importou a biblioteca antes do início da contagem. Use o tempo até ficar pronto.

### Rodadas e anomalias

- **Rodada completa:** 54 rodadas, todas concluídas, sem entradas em `failures.log`. A memória disponível no host não ficou abaixo de 25,2 GiB.
- **Pico de CPU do k6:** nas 3 rodadas de FastAPI + httpx com 10.000 VUs, o k6 teve picos de 355,4% a 403,3%, com média de 17,5% a 18,5%. Pela média, o k6 não ficou saturado, e o mesmo alvo já falha com 5.000 VUs, sem esse pico. Por isso, as rodadas foram mantidas. A mock-api não passou de 36,7%.
- **FastAPI + httpx na memória:** os 373 MiB com 10.000 VUs não indicam eficiência, porque ele não entregou respostas. As requisições esgotam os 30 s de timeout do k6.
- **Teste de limite interrompido:** a rodada `20261103-162014` foi cortada por um limite de tempo da minha sessão, no Flask com threads. Ela não tem relatório, foi mantida e não entra nas medianas.
- **Diagnósticos:** estão em `results/diagnostico-python/`, com scripts e variantes. Não entram nas medianas. O primeiro perfil com `cProfile`, no alvo sob carga, não gerou arquivo, e a causa não foi investigada: ele foi substituído pelo perfil do cliente isolado.
