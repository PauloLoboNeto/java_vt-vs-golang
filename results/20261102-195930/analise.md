### Conclusões

- **Os 10 alvos sustentaram 100 req/s, sem erros e sem iterações descartadas.** Com cerca de 500 chamadas simultâneas, a carga é menor que a do nível de 1.000 VUs, e a diferença está em memória, CPU e latência de cauda.
- **Go e Rust melhoraram sem custo aparente.** Memória de pico do Go: 28,9 para 24,8 MiB. Rust: 41,7 para 34,0 MiB, com CPU por 1.000 requisições de 0,200 para 0,161.
- **O coletor define a cauda do Native.** O overhead p99 foi de 26,1 ms com Serial, com ou sem `-Xmn400m`, e de 3,3 ms com G1.
- **O ZGC tem a menor latência máxima da JVM.** Foram 5.004,4 ms, contra 5.019,3 ms com G1, com 39% mais memória de pico. No p99, a diferença é mínima: 3,4 ms contra 3,7 ms.

### Limites destas conclusões

- **Com carga leve, o Java otimizado gastou mais CPU.** A JVM foi de 1,198 para 1,518 CPU-s por 1.000 requisições, e o Native com Serial, de 0,869 para 1,001. A causa não foi investigada. Os valores absolutos são baixos: até cerca de 16% de 1 core.
- **Esta rodada não mede capacidade.** Todos os alvos ficaram folgados. O modo por taxa só mostraria perda de capacidade com taxas maiores.
- **Não houve medição de startup,** porque ela não depende do modo de carga.

### Rodadas e anomalias

- **Rodada completa:** 30 rodadas, nenhuma repetida ou descartada. Mock-api e k6 ficaram muito abaixo de 320% de CPU: o maior pico foi de 16,1%, no k6. A memória disponível no host não ficou abaixo de 28,9 GiB.
