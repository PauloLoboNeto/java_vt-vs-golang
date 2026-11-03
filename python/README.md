# Trilha Python

Mesmo contrato, mesma carga e mesmos limites de **2 vCPU e 1 GB** dos demais alvos, com Go como controle. As dependências estão fixadas em `requirements.txt`, geradas a partir de `requirements.in`.

| Alvo | Pilha | Modelo de concorrência |
|---|---|---|
| `py-fastapi` | FastAPI + uvicorn + httpx | asyncio |
| `py-fastapi-aiohttp` | FastAPI + uvicorn + cliente do aiohttp | asyncio |
| `py-aiohttp` | aiohttp como servidor e cliente, com gunicorn | asyncio |
| `py-flask-gevent` | Flask + gunicorn + requests | greenlets |
| `py-flask-threads` | Flask + gunicorn + requests | threads do sistema |

## Versões

Verificadas em 03/11/2026 no PyPI e no Docker Hub.

| Componente | Versão |
|---|---|
| Python | 3.15.2, `python:3.15.2-slim-bookworm` (`sha256:4e03260adeeebafccd084f3584e6b84823aba5651cfb53ef8a078ed441ddf9cd`) |
| FastAPI, uvicorn | 0.162.0, 0.54.0 |
| uvloop, httptools | 0.23.0, 0.9.0 |
| httpx, httpcore | 0.28.1, 1.0.9 |
| aiohttp | 3.14.5 |
| Flask, requests | 3.1.3, 2.34.2 |
| gunicorn, gevent | 26.2.0, 26.9.0 |

## Ajustes

Só foram retirados limites artificiais. Nenhum alvo foi otimizado para melhorar o próprio resultado.

| Ajuste | Onde | Motivo |
|---|---|---|
| 2 workers | Todos | O GIL impede um processo só de usar os 2 vCPU |
| Sem limite de conexões no cliente | httpx, aiohttp | Os padrões são de 100 conexões |
| `pool_maxsize=20000` | requests | O padrão é de 10 conexões no pool |
| Timeout de 10 s no cliente | httpx, aiohttp, requests | Igual ao Go. O padrão do httpx é de 5 s, a mesma latência da API externa |
| Backlog de 65535 e keep-alive de 60 s | Servidores | Não criam gargalo na subida dos VUs e mantêm as conexões durante a espera |
| `--worker-connections 20000` | gunicorn com Flask | O padrão é de 1.000 |
| `--threads 10000` | `py-flask-threads` | Cobre os 10.000 VUs. As threads são criadas sob demanda |
| Sem log de acesso | Servidores | O Go também não registra acessos |

## Como executar

```bash
TARGETS="go-fiber py-fastapi py-fastapi-aiohttp py-aiohttp py-flask-gevent py-flask-threads" scripts/run-all.sh
```

## Resultado

A análise está em [`results/20261103-175032`](../results/20261103-175032/report.md). Com 10.000 VUs, só o aiohttp puro ficou no nível do Go em latência e throughput, com 3,2 vezes a CPU por requisição. FastAPI + httpx teve 100% de erros já com 5.000 VUs, por causa do pool de conexões do `httpcore`. Trocar só o cliente pelo do aiohttp resolve os erros.
