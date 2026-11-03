### Conclusões

- **Todos os alvos otimizados atenderam a 10.000 VUs em 1 GB, sem erros.** No padrão, as duas variantes Java tinham 100% de erros nesse nível. Agora a JVM com G1 faz 1.992,5 de 2.000 req/s, com overhead p99 de 88,2 ms, e o Native com G1 faz 1.996,0, com 101,4 ms.
- **Nem todos ficaram acima de 95% do ideal.** O Native com Serial fez 1.650,3 req/s (82,5%), com overhead p99 de 3.376,7 ms, nas 3 repetições. O ZGC fez 1.949,9 req/s na mediana, mas caiu a 1.749,3 req/s em uma repetição.
- **O maior ganho do Java veio da troca do servidor e de ajustes por conexão, não do coletor.** Com Tomcat, o heap vivo com 10.000 VUs era de 1,39 GB. Com Jetty, sem o cache de cabeçalhos por conexão e com o limite de concorrência removido, o processo coube em 953 MiB, com G1.
- **No Native, o coletor decide o resultado.** Com 5.000 VUs, o overhead p99 foi de 665,5 ms com Serial e de 81,0 ms com G1. Com 10.000 VUs, o throughput foi de 1.650,3 req/s com Serial e de 1.996,0 req/s com G1.
- **O ZGC só compensa até certa carga.** Com 5.000 VUs, teve overhead p99 de 5,0 ms, contra 57,2 ms do G1, com 49% mais CPU por requisição. Com 10.000 VUs, ficou pior em tudo: 848,9 ms contra 88,2 ms, 2,7 vezes a CPU e 1.016 MiB de pico, a 8 MiB do limite.
- **Rust e Go otimizados têm latência igual e custos invertidos.** Com 10.000 VUs, o Go usa menos memória (343 MiB contra 543 MiB), e o Rust, menos CPU (0,054 contra 0,059 CPU-s por 1.000 requisições). O Rust ganhou 28% de CPU e 14% de memória, e o Go ganhou 16% de memória, sem mudança de CPU.
- **Mesmo otimizado, o Java continua mais caro.** Com 10.000 VUs, a JVM com G1 usa 2,8 vezes a memória e 5,4 vezes a CPU do Go otimizado. O AOT Cache reduziu o tempo até ficar pronto de 2.319 ms para 1.156 ms, ainda longe dos 124 ms do Go, e aumentou a imagem de 512,6 MB para 638,9 MB.

### Limites destas conclusões

- **Os alvos padrão vêm de outras rodadas.** Go e Rust são da `20261102-173102`, e o Java, da `20261102-005118`, na mesma máquina. Diferenças pequenas não devem ser tratadas como efeito dos ajustes.
- **Os ajustes foram feitos para este cenário.** As respostas têm 35 bytes, os cabeçalhos ficam limitados a 2 KiB, e o cache de cabeçalhos está desligado. Requisições reais com cookies ou tokens grandes podem ser rejeitadas, e respostas maiores podem custar mais.
- **O Java otimizado não é só a mesma aplicação com outras flags.** O servidor HTTP mudou. O Native com G1 também muda de distribuição, para Oracle GraalVM, com licença própria.
- **Nem toda otimização melhorou tudo.** Com 1.000 VUs, a memória de pico da JVM subiu de 449,9 MiB para 502,9 MiB. Na rodada de 100 req/s, a CPU por requisição do Java otimizado foi maior que a do padrão, e a causa não foi investigada.
- **O ZGC divergiu dos diagnósticos.** Em rodadas de 60 s sem AOT Cache, ele foi encerrado pelo kernel com 10.000 VUs. Nesta rodada, com AOT Cache, não foi. A causa não foi investigada, e o pico de 1.016 MiB indica que a margem é muito pequena.
- **A memória da JVM não é o mínimo necessário.** O coletor ocupa o heap disponível, e o mesmo vale para o Native com G1.

### Rodadas e anomalias

- **Rodada completa:** 54 rodadas, sem erros e sem OOM. Mock-api e k6 ficaram abaixo de 320% de CPU: o maior pico foi de 245,2%, no k6. A memória disponível no host não ficou abaixo de 25,3 GiB.
- **Execução em duas partes:** a máquina desligou por volta das 00:00 UTC, e a rodada foi retomada às 01:00 UTC com `scripts/resume.sh`. Nenhuma rodada foi descartada. A rodada ZGC com 10.000 VUs, rep 2, foi cortada antes de gravar seus arquivos finais e repetida. A versão cortada, com 1.639,2 req/s, está em `interrompidas/` e não entra nas medianas. O log do k6 dela foi sobrescrito pela repetição.
- **Efeito da retomada:** não há mudança sistemática entre as repetições feitas antes e depois. A exceção é a memória de JVM e ZGC com 1.000 VUs na rep 3, cerca de 11% maior, sem efeito em latência ou CPU.
- **Abaixo de 95% do ideal:** Native com Serial com 10.000 VUs, nas 3 repetições, e ZGC com 10.000 VUs, rep 3. Os logs de GC não foram gravados nesta rodada, então a causa não foi medida aqui. Os diagnósticos em `results/diagnostico-opt/` mostram pausas de 150 a 200 ms no Serial.
