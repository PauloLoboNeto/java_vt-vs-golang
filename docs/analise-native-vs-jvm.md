# Em que o Native Image é melhor que a JVM

O Native é melhor em **startup, tamanho da imagem e, com 1.000 VUs, consumo de memória e CPU**. Sob carga maior a vantagem acaba: com 5.000 VUs a JVM foi melhor, e com 10.000 as duas falharam. Os valores vêm da rodada completa `20261102-005118`, com 2 vCPU e 1 GB por alvo.

## Onde o Native foi melhor

| Critério | Native | JVM | Vantagem do Native |
|---|---|---|---|
| Tempo até ficar pronto | 164 ms | 2.319 ms | cerca de 14 vezes mais rápido |
| 1ª requisição, além dos 5s | 8,2 ms | 105,0 ms | cerca de 13 vezes menos |
| Memória parada | 21,0 MiB | 202,7 MiB | cerca de 10 vezes menos |
| Imagem | 131,2 MB | 512,6 MB | cerca de 4 vezes menor |
| Memória de pico, 1.000 VUs | 297,0 MiB | 449,9 MiB | 34% menos |
| CPU-s por 1.000 req, 1.000 VUs | 0,489 | 0,694 | 30% menos |

Isso favorece o Native em cenários com muitos reinícios ou escala rápida, ou com carga baixa e muitas instâncias pequenas.

## Onde o Native não foi melhor

| Critério | Native | JVM | Melhor |
|---|---|---|---|
| Overhead p99, 1.000 VUs | 76,0 ms | 8,2 ms | JVM |
| Throughput, 5.000 VUs | 866,6 req/s | 994,1 req/s | JVM |
| Overhead p99, 5.000 VUs | 2.506,7 ms | 278,5 ms | JVM |
| CPU-s por 1.000 req, 5.000 VUs | 0,736 | 0,495 | JVM |
| Memória de pico, 5.000 VUs | 960,8 MiB | 972,8 MiB | empate na prática |
| 10.000 VUs | 100% de erros | 100% de erros | nenhum |

O build também é mais caro. O Native levou 1m54 e chegou a 3,68 GiB de pico, contra cerca de 30s da JVM. Foi uma medição única, não parte do benchmark.

## O que não se pode concluir

- **Que a compilação nativa em si é pior sob carga:** o Native usou JDK 25 e Serial GC, e a JVM usou JDK 27 e G1. As pausas de GC explicam boa parte da queda com 5.000 VUs, mas os dados não separam o efeito do GC do efeito da versão do JDK ou da compilação nativa.
- **Que essa vantagem de memória vale em geral:** a JVM com G1 tende a ocupar o heap disponível antes de coletar, então os 449,9 MiB mostram o que ela usou, não o mínimo de que precisa. Com um heap menor, a diferença poderia mudar, mas isso não foi testado.
- **Que o resultado vale para outras configurações:** tudo foi medido com 2 vCPU, 1 GB, sem ajuste de heap e só com espera de I/O. Com mais memória ou outro tipo de trabalho, o resultado pode mudar. A única rodada de contraprova, com Native em 2 GB e 5.000 VUs, fez 912,8 req/s, ainda abaixo da JVM com 1 GB.
