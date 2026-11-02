# Análise do startup

O **Go foi o mais rápido, com o Native logo atrás, e a JVM ficou bem mais lenta**. Os valores vêm das 10 execuções por alvo da rodada completa `20261102-005118`.

| Alvo | Tempo até ficar pronto, mediana (ms) | Pronto, p90 (ms) | 1ª requisição, além dos 5s (ms) | Memória parada (MiB) | Imagem (MB) |
|---|---|---|---|---|---|
| Go | 122 | 126 | 6,0 | 3,4 | 20,3 |
| Native (JDK 25) | 164 | 167 | 8,2 | 21,0 | 131,2 |
| JVM (JDK 27) | 2.319 | 2.374 | 105,0 | 202,7 | 512,6 |

- **Tempo até ficar pronto:** a JVM levou cerca de 19 vezes o tempo do Go e 14 vezes o do Native. Entre Go e Native a diferença é de só 42 ms.
- **Estabilidade:** o p90 ficou muito perto da mediana nos três alvos, então a medição variou pouco entre execuções.
- **Primeira requisição:** a JVM gasta cerca de 105 ms além dos 5s da API externa, contra 6 a 8 ms dos outros dois. É provável que seja aquecimento da JVM, como carregamento de classes e código ainda não compilado, mas isso não foi medido separadamente.
- **Memória parada:** é lida 5s depois da primeira requisição. A JVM usa cerca de 60 vezes a memória do Go, e o Native usa cerca de 6 vezes.

## Como ler os números

- **O que o tempo inclui:** vai do start do container até o primeiro `/health` com 200, medido do host a cada 5 ms. Inclui o custo do próprio Docker, então parte dos 122 ms do Go provavelmente é Docker, não a aplicação.
- **Tempo autodeclarado:** a JVM informou 2.137 ms e o Native, 43 ms, o que reforça que boa parte do tempo do Native (164 ms) está fora da aplicação. O Go informou 0 ms, mas esse valor não inclui o início do runtime e não é comparável ao do Java.
- **Limite de CPU:** tudo foi medido com 2 vCPU. A JVM provavelmente se beneficiaria de mais CPU na subida, mas isso não foi testado.
