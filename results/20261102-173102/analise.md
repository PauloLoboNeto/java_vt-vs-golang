### Conclusões

- **Rust e Go atenderam aos três níveis dentro de 2 vCPU e 1 GB, com latência equivalente.** Com 10.000 VUs, o Rust fez 1.999,4 de 2.000 req/s e o Go 1.999,5, sem erros, com overhead p99 de 2,3 ms e 2,2 ms. Nos três níveis, a diferença de overhead p99 ficou em até 0,1 ms.
- **O Go gastou menos memória sob carga.** Pico com 1.000, 5.000 e 10.000 VUs: Go 46,5, 207,0 e 407,6 MiB; Rust 69,9, 321,0 e 629,4 MiB, cerca de 50% a mais.
- **O Go também gastou menos CPU.** CPU-s por 1.000 requisições com 1.000, 5.000 e 10.000 VUs: Go 0,136, 0,076 e 0,059; Rust 0,151, 0,093 e 0,075, de 11% a 27% a mais. Em valores absolutos a CPU é baixa: 15,2% de 1 core para o Rust com 10.000 VUs, contra 11,9% do Go.
- **O Rust usa menos memória parado, mas a imagem é maior.** Parado: 1,8 MiB, contra 3,4 MiB do Go. Imagem: 40,4 MB, contra 20,3 MB, porque usa `distroless/cc`, e o Go, `distroless/static`. O tempo até ficar pronto empatou: 125 ms e 124 ms.

### Limites destas conclusões

- **O resultado compara stacks, não linguagens.** O Go usa fasthttp nos dois lados, biblioteca voltada a reaproveitar buffers. O Rust usa Axum, hyper e reqwest, com o alocador padrão da glibc e sem ajuste de buffers, de alocador ou de LTO. A causa da diferença de memória e CPU não foi investigada. Outro cliente HTTP ou outro alocador pode mudar esses números.
- **O cenário é só de espera de I/O.** Não há trabalho de CPU no handler, nem TLS, serialização ou acesso a banco.
- **Os tempos autodeclarados do Go e do Rust (0 ms) não são comparáveis.** Use o tempo até ficar pronto.
- **O Java não foi executado nesta rodada.** A comparação com ele usa a rodada `20261102-005118`, na mesma máquina. O Go, repetido como controle, ficou próximo daquela rodada: 124 ms e 122 ms até ficar pronto, 407,6 MiB e 407,3 MiB de pico com 10.000 VUs, 2,2 ms e 2,1 ms de overhead p99.

### Rodadas e anomalias

- **Rodada completa:** 18 rodadas, nenhuma repetida ou descartada, sem erros e sem OOM. Mock-api e k6 ficaram abaixo de 320% de CPU: o maior pico foi de 206,5%, no k6. A memória disponível no host não ficou abaixo de 25,7 GiB.
- **Rodadas à parte:** a validação `20261102-172609` e o teste de limite `20261102-172853` não entram nas medianas. Um reinício do ambiente interrompeu a validação depois da carga, por isso ela não tem relatório.
