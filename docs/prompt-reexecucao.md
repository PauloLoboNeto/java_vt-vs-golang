# Prompt para reaplicar o benchmark

Cole o bloco abaixo numa nova sessão do Claude Code. Ajuste só a linha `Versões`, se quiser testar versões mais novas. O código já está no repositório, então o prompt reexecuta o teste em vez de recriar o projeto.

Para comparar com a rodada `20261102-005118`, use uma máquina equivalente: 16 vCPU e cerca de 32 GB, x86_64. Em outra máquina, os números absolutos não são diretamente comparáveis.

````markdown
Reaplique o benchmark de I/O do repositório PauloLoboNeto/java_vt-vs-golang (privado). Clone-o em projetos/benchmarks/java_vt-vs-golang, leia o README.md e execute o teste. Escreva tudo em português.

Versões: mantenha as fixadas no repositório, para o resultado ser comparável. Liste na mensagem final as versões estáveis mais novas disponíveis, sem aplicá-las.

## Máquina
Verifique antes de começar:
- Docker com Compose v2 e Python 3, com socket `unix://`. Se o Docker faltar e houver sudo, instale o Docker CE pelo repositório oficial, com `acl`, `procps` e `python3-venv`, e dê acesso ao socket para o usuário atual.
- Recomendado: 16 vCPU e 32 GB de RAM. Mínimo: 12 CPUs e 16 GB livres para o Docker. **Abaixo do mínimo, pare e me avise.**
- Disco: cerca de 15 GB livres para imagens e resultados.
- Registre os digests das imagens com `docker images --digests`, porque `eclipse-temurin:27-jre` e as imagens distroless não têm versão exata na tag.

## Execução
Só avance quando a etapa anterior passar. Rode o que for longo em `tmux`. Não rode nada pesado na máquina enquanto uma rodada estiver medindo.

1. Rode `go vet` nos módulos Go e builde as imagens.
2. Smoke test: `curl` em `/api/io` de cada alvo deve responder em cerca de 5s.
3. Validação: `REPS=1 LEVELS=1000 DURATION=60 STARTUP_RUNS=3 scripts/run-all.sh`. Espere cerca de 200 req/s e 0% de erros nos três alvos.
4. Teste de limite: `REPS=1 LEVELS=10000 DURATION=60 STARTUP_RUNS=1 scripts/run-all.sh`. Confira `nf_conntrack_max`, `fs.file-max` e a memória do k6, e corrija gargalos de ambiente.
5. Rodada completa: `scripts/run-all.sh` (cerca de 1h50).

## Regras de integridade dos dados
- **Não mude só um alvo para melhorar o resultado dele.** Ajuste apenas limites artificiais, trate os alvos de forma equivalente e documente. Não altere os limites de 2 vCPU / 1 GB.
- **OOM ou queda de throughput no limite de 1 GB é resultado.** Reporte como resultado, não como erro a corrigir.
- **Investigue todo throughput abaixo de 95% do ideal, mesmo com 0% de erros.** Rodadas de diagnóstico ficam em diretório separado e não entram nas medianas. Os arquivos usados na rodada anterior estão em `results-20261102-005118.tgz`, na pasta `diagnosticos/`: overrides do Compose para log de GC e cálculo do tempo em pausa.
- **Não apague nem substitua rodadas ruins.** Se repetir uma, mantenha as duas e explique.
- **Mock-api ou k6 saturados invalidam a rodada.** Dê mais recursos a eles e repita.
- **Confira cada afirmação da análise contra os dados** antes de escrevê-la, inclusive se um OOM é do kernel ou de heap, em cada rodada.

## Referência da rodada anterior
Serve só para detectar erros grosseiros. Não misture com os novos resultados. Rodada `20261102-005118`, 16 vCPU e 30,8 GiB:

| Medida | Go | JVM | Native |
|---|---|---|---|
| Pronto, mediana | 122 ms | 2.319 ms | 164 ms |
| 1.000 VUs: req/s, memória de pico | 200,0, 46 MiB | 199,9, 450 MiB | 199,9, 297 MiB |
| 5.000 VUs: req/s, overhead p99 | 999,8, 2,0 ms | 994,1, 278,5 ms | 866,6, 2.506,7 ms |
| 10.000 VUs: req/s, erros | 1.999,6, 0% | 0, 100% (OOM de heap) | 0, 100% (OOM kill) |

## Entrega
1. Escreva `results/<timestamp>/analise.md` e regenere o relatório com `.venv/bin/python report/generate.py results/<timestamp>`.
2. Compacte o diretório em `results-<timestamp>.tgz`, na raiz do projeto.
3. Copie o relatório para `docs/resultados-<timestamp>.html`. **Não sobrescreva `docs/index.html` nem o pacote da rodada anterior.**
4. Antes de publicar, procure credenciais nos arquivos e no pacote.
5. Faça commit em uma branch nova, faça push e abra um pull request para `main`. Não faça merge. Se o SSH falhar por chave de host desconhecida, use HTTPS com `gh auth git-credential`, configurado só neste repositório.
6. Envie a mensagem final com:
   - ambiente: CPU, arquitetura, RAM, sistema operacional e versão do Docker;
   - versões finais de cada componente e digests das imagens;
   - tabelas dos comparativos A e B, com startup, latência, throughput, erros, memória (parada, média e pico) e CPU (média e CPU-s por 1.000 requisições), por nível de VUs;
   - comparação com a rodada anterior, separando diferenças relevantes de variação normal;
   - conclusões sustentadas pelos dados, deixando claro que o Native Image usa JDK 25, se ainda for o caso;
   - diferenças em relação a este prompt, rodadas repetidas, OOMs e anomalias.

Pare e me pergunte somente se a máquina estiver abaixo do mínimo ou se precisar de algo que não consiga obter sozinho.
````
