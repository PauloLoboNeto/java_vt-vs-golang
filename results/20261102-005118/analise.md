### Conclusões

- **Só o Go atendeu aos três níveis dentro de 2 vCPU e 1 GB.** Com 10.000 VUs, fez 1.999,6 de 2.000 req/s, sem erros, com overhead p99 de 2,1 ms e 407 MiB de pico. As duas variantes Java tiveram 100% de erros nesse nível, nas 3 repetições.
- **Com 1.000 VUs, os três entregaram o throughput ideal, e a diferença está no custo.** Memória de pico: Go 46 MiB, Native 297 MiB, JVM 450 MiB. CPU-s por 1.000 requisições: Go 0,137, Native 0,489, JVM 0,694. Overhead p99: Go 2,0 ms, JVM 8,2 ms, Native 76,0 ms.
- **Com 5.000 VUs, a JVM superou o Native Image em throughput, latência e CPU, com memória de pico equivalente.** A JVM fez 994,1 req/s (99,4% do ideal), com overhead p99 de 278,5 ms. O Native fez 866,6 req/s (86,7%), com overhead p99 de 2.506,7 ms. O Go fez 999,8 req/s, com overhead p99 de 2,0 ms e 207 MiB de pico, contra cerca de 970 MiB das duas variantes Java.
- **O Native Image ganha da JVM no startup e na memória parada.** Ficou pronto em 164 ms, contra 2.319 ms da JVM e 122 ms do Go. Parado, usa 21,0 MiB, contra 202,7 MiB da JVM e 3,4 MiB do Go.

### O que explica os resultados

- **Native com 5.000 VUs, abaixo de 95% do ideal e com 0 erros.** Rodadas de diagnóstico com log de GC mostram 47,8% do tempo em pausa, com Full GCs de cerca de 600 ms em sequência no Serial GC. Na JVM, com G1, foram 8,7%, com mediana de 18 ms. Como os VUs esperam a resposta antes de repetir, a latência maior reduz o throughput: 5.000 VUs / 5,67 s dá cerca de 880 req/s, próximo do medido. O host não é a causa: mock-api e k6 ficaram folgados, e sobraram mais de 26 GB livres.
- **Mais memória ajuda, mas não resolve.** Com 2 GB, só como contraprova, o Native fez 912,8 req/s, ainda abaixo de 95%, com 26,1% do tempo em pausa e 1.523 MiB de pico. Essa rodada não faz parte dos resultados. Ela indica que o Serial GC pesa além do tamanho do heap, mas uma única rodada de 60s não separa os dois efeitos.
- **Java com 10.000 VUs.** A memória esgota nos primeiros segundos de subida dos VUs, antes do fim do warm-up. A JVM passa de 900 MiB em cerca de 4s e não cai: registra `OutOfMemoryError`, permanece em cerca de 197% de CPU e não responde mais. O Native é encerrado pelo kernel por volta de 5s, nas 3 repetições, sem `OutOfMemoryError` no log. No teste de limite, feito à parte, ele registrou esse erro antes de ser encerrado. Por isso as tabelas não têm latência nem memória do Native nesse nível, e o gráfico de série temporal mostra a queda.

### Limites destas conclusões

- **Os resultados valem para este limite e estas configurações.** O fracasso do Java com 10.000 VUs é um resultado com 1 GB e sem ajuste de heap ou de buffers, e não mostra que ele não suporte essa carga com mais memória. A memória exigida com 10.000 VUs não foi medida.
- **O comparativo B mistura duas diferenças.** O Native Image usa JDK 25 e Serial GC, e a JVM usa JDK 27 e G1. Os dados não separam o efeito da versão do JDK do efeito do GC. A GraalVM CE não oferece G1.
- **A memória da JVM não é o mínimo necessário.** O G1 ocupa o heap disponível antes de coletar, então os cerca de 970 MiB com 5.000 VUs mostram o que ela usou, não o que precisaria.
- **O cenário é só de espera de I/O.** Não há trabalho de CPU no handler, nem TLS, serialização ou acesso a banco.
- **O tempo autodeclarado do Go (0 ms) não é comparável.** Ele não inclui o início do runtime. Use o tempo até ficar pronto.

### Rodadas e anomalias

- **Rodada completa:** 27 rodadas, nenhuma repetida ou descartada. Na janela medida, mock-api e k6 ficaram abaixo de 320% de CPU, e a memória disponível no host nunca ficou abaixo de 26 GB. Fora da janela, o k6 teve uma única amostra de 370%, em Native com 10.000 VUs, rep 2, cerca de 1s depois de o alvo cair. Como o alvo já estava encerrado, isso não afeta o resultado.
- **OOMs:** 3 OOM kills no Native e 3 execuções com `OutOfMemoryError` de heap na JVM, todos com 10.000 VUs.
- **Rodadas à parte:** validação, teste de limite e diagnósticos estão em diretórios separados e não entram nas medianas. Os diagnósticos estão em `diagnosticos/`.
