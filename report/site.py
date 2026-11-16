#!/usr/bin/env python3
"""Gera docs/index.html, a página que reúne todas as trilhas: site.py [saida.html].

Os números das tabelas vêm de results/, pelas mesmas funções de generate.py. O texto é escrito à mão
e foi conferido contra os dados. Ao trocar uma rodada de referência, revise o texto junto.
"""
import base64
import html
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "report"))
import generate as g  # noqa: E402

RESULTS = os.path.join(ROOT, "results")
REPO = "https://github.com/PauloLoboNeto/java_vt-vs-golang"

# Rodadas completas usadas na página.
STD, RUST, OPT, RATE, PY = "20261102-005118", "20261102-173102", "20261102-215054", "20261102-195930", "20261103-175032"

# Rodada de onde vem cada alvo na carga por VUs.
SOURCE = {
    "go-fiber": STD, "java-jvm": STD, "java-native": STD, "rust-axum": RUST,
    "go-fiber-opt": OPT, "java-jvm-opt": OPT, "java-jvm-zgc": OPT, "java-native-opt": OPT,
    "java-native-g1": OPT, "rust-axum-opt": OPT,
    "py-fastapi": PY, "py-fastapi-aiohttp": PY, "py-aiohttp": PY, "py-flask-gevent": PY, "py-flask-threads": PY,
}
LABEL = {
    "go-fiber": "Go (Fiber)",
    "java-jvm": "Java JVM (Tomcat, G1)",
    "java-native": "Java Native (Tomcat, Serial)",
    "rust-axum": "Rust (Axum + reqwest)",
    "go-fiber-opt": "Go otimizado",
    "java-jvm-opt": "Java JVM otimizada (Jetty, G1)",
    "java-jvm-zgc": "Java JVM otimizada (Jetty, ZGC)",
    "java-native-opt": "Java Native otimizado (Jetty, Serial)",
    "java-native-g1": "Java Native otimizado (Jetty, G1 Oracle)",
    "rust-axum-opt": "Rust otimizado (Axum + hyper)",
    "py-fastapi": "Python: FastAPI + httpx",
    "py-fastapi-aiohttp": "Python: FastAPI + cliente aiohttp",
    "py-aiohttp": "Python: aiohttp",
    "py-flask-gevent": "Python: Flask + gevent",
    "py-flask-threads": "Python: Flask + threads",
}
ALL = list(LABEL)

_cache = {}


def run(directory):
    """Rodadas, agregado e startup de um diretório de results/."""
    if directory not in _cache:
        path = os.path.join(RESULTS, directory)
        rounds = g.load_rounds(path)
        _cache[directory] = (rounds, g.aggregate(rounds), g.load_startup(path))
    return _cache[directory]


def agg(target, level, directory=None):
    return run(directory or SOURCE[target])[1].get((target, level))


def startup(target):
    return run(SOURCE[target])[2].get(target)


def mib(value, decimals=1):
    return g.num(value / g.MIB, decimals) if value else "-"


# ---------------- blocos de HTML ----------------

def inline(text):
    text = html.escape(text, quote=False)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)


def h(level, text, anchor=None):
    attr = f' id="{anchor}"' if anchor else ""
    return f"<h{level}{attr}>{inline(text)}</h{level}>"


def p(text):
    return f"<p>{inline(text)}</p>"


def ul(items):
    return "<ul>" + "".join(f"<li>{inline(i)}</li>" for i in items) + "</ul>"


def pre(code, caption=None):
    cap = f'<div class="caption">{inline(caption)}</div>' if caption else ""
    return f'{cap}<pre><code>{html.escape(code.strip())}</code></pre>'


def table(head, rows, wrap=()):
    text = [g.is_text_column(rows, i) or i in wrap for i in range(len(head))]

    def cls(i):
        names = (["text"] if text[i] else []) + (["wrap"] if i in wrap else [])
        return f' class="{" ".join(names)}"' if names else ""

    out = ['<div class="table"><table><thead><tr>' +
           "".join(f"<th{cls(i)}>{html.escape(c)}</th>" for i, c in enumerate(head)) + "</tr></thead><tbody>"]
    for r in rows:
        out.append("<tr>" + "".join(f"<td{cls(i)}>{inline(str(c))}</td>" for i, c in enumerate(r)) + "</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


def img(path, alt):
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode()
    return f'<img src="data:image/png;base64,{data}" alt="{html.escape(alt)}">'


def errors(a):
    if a is None:
        return "-"
    return f"{g.num(a['errors'])} ({g.pct(a['error_rate'])})"


# ---------------- tabelas a partir dos dados ----------------

def load_table(targets, levels, directory=None, with_ideal=True):
    """Tabela compacta: throughput, erros, latência de cauda, memória e CPU."""
    head = ["Nível", "Alvo", "req/s real"] + (["req/s ideal"] if with_ideal else []) + [
        "Erros", "Overhead p99 (ms)", "max (ms)", "Memória pico (MiB)", "CPU média (%)", "CPU-s por 1.000 req", "OOM"]
    rows = []
    for level in levels:
        for t in targets:
            a = agg(t, level, directory)
            if not a:
                continue
            oom = "kill" if a["ooms"] else ("heap" if a["heap_ooms"] else "não")
            if a["ooms"] or a["heap_ooms"]:
                oom += f" ({a['ooms'] or a['heap_ooms']} de {a['reps']})"
            rows.append([g.num(level), LABEL[t], g.num(a["rps"], 1)] + ([g.num(a["ideal_rps"])] if with_ideal else []) + [
                errors(a), g.num(a["overhead_p99"], 1), g.num(a["max"], 1), mib(a["mem_peak"]),
                g.num(a["cpu_avg"], 1), g.num(a["cpu_per_1k"], 3), oom])
    return table(head, rows)


def summary_table(level):
    head = ["Alvo", "Rodada", "req/s real", "Erros", "Overhead p99 (ms)", "Memória pico (MiB)", "CPU-s por 1.000 req",
            "Pronto em (ms)", "Memória parada (MiB)"]
    rows = []
    for t in ALL:
        a, s = agg(t, level), startup(t)
        rows.append([LABEL[t], f"`{SOURCE[t]}`", g.num(a["rps"], 1), errors(a), g.num(a["overhead_p99"], 1),
                     mib(a["mem_peak"]), g.num(a["cpu_per_1k"], 3),
                     g.num(s["time_to_ready_ms"]["median"]), mib(s["idle_mem_bytes"]["median"])])
    return table(head, rows)


def startup_table():
    head = ["Alvo", "Pronto, mediana (ms)", "Pronto, p90 (ms)", "1ª requisição (ms além dos 5 s)", "Memória parada (MiB)",
            "Imagem (MB)", "Execuções"]
    rows = []
    for t in ALL:
        s = startup(t)
        rows.append([LABEL[t], g.num(s["time_to_ready_ms"]["median"]), g.num(s["time_to_ready_ms"]["p90"]),
                     g.num(s["first_io_ms"]["median"], 1), mib(s["idle_mem_bytes"]["median"]),
                     g.num(s["image_size_bytes"] / 1e6, 1), g.num(len(s["runs"]))])
    return table(head, rows)


def rate_table():
    rounds, aggregated, _ = run(RATE)
    dropped = {}
    for r in rounds:
        dropped.setdefault(r["target"], []).append(r["k6"].get("dropped_iterations", 0))
    order = ["go-fiber", "go-fiber-opt", "rust-axum", "rust-axum-opt", "java-jvm", "java-jvm-opt", "java-jvm-zgc",
             "java-native", "java-native-opt", "java-native-g1"]
    head = ["Alvo", "req/s real", "Iterações descartadas", "Erros", "Overhead p99 (ms)", "max (ms)", "Memória média (MiB)",
            "Memória pico (MiB)", "CPU média (%)", "CPU-s por 1.000 req"]
    rows = []
    for t in order:
        a = aggregated[(t, 100)]
        rows.append([LABEL[t], g.num(a["rps"], 1), g.num(sum(dropped[t])), errors(a), g.num(a["overhead_p99"], 1),
                     g.num(a["max"], 1), mib(a["mem_avg"]), mib(a["mem_peak"]), g.num(a["cpu_avg"], 1),
                     g.num(a["cpu_per_1k"], 3)])
    return table(head, rows)


# Diagnósticos de 60 s, uma repetição, em results/diagnostico-opt. Fora das medianas.
JETTY_STEPS = [
    ("", "java-jvm", 10000, "4 GB", "Tomcat, como no alvo padrão",
     "Atende, mas só com 4 GB: a geração old do G1 fica com cerca de 1.330 MiB. É o heap vivo que não cabe em 1 GB."),
    ("iter1", "java-jvm-opt", 10000, "1 GB", "Jetty com os padrões, sem `JettyConfig`",
     "100% de timeouts, sem OOM: o `VirtualThreadPool` aceita 200 tarefas simultâneas, o que dá no máximo 40 req/s com 5 s de espera."),
    ("iter2-jvm", "java-jvm-opt", 10000, "1 GB", "+ `VirtualThreadPool(20000)`",
     "O limite some e a memória acaba: OOM kill e `OutOfMemoryError`."),
    ("iter3-jetty-4g", "java-jvm-opt", 10000, "4 GB", "Mesma configuração, com 4 GB para medir",
     "Atende. O histograma mostra 984 MB de `char[]`, cerca de 98 KB por conexão, no cache de cabeçalhos."),
    ("iter4-jetty-1g", "java-jvm-opt", 10000, "1 GB", "+ `headerCacheSize=0`",
     "Cabe em 1 GB e atende, mas o pico chega a 1.004 MiB, a 20 MiB do limite, com heap de 75%."),
    ("iter5-jvm70", "java-jvm-opt", 10000, "1 GB", "+ heap de 70%",
     "Configuração final do `java-jvm-opt`: mais folga fora do heap e cauda menor."),
]
GC_STEPS = [
    ("iter7-g1", "java-jvm-opt", "JVM, G1, heap de 70%", ""),
    ("iter6-zgc", "java-jvm-opt", "JVM, ZGC, heap de 70%, sem AOT Cache nem Compact Object Headers", ""),
    ("iter7-zgc60", "java-jvm-opt", "JVM, ZGC, heap de 60%, sem AOT Cache", ""),
    ("iter5-native-padrao", "java-native-opt", "Native CE, Serial, geração jovem no padrão", ""),
    ("iter5-native-xmn256", "java-native-opt", "Native CE, Serial, `-Xmn256m`", ""),
    ("iter5-native-xmn400", "java-native-opt", "Native CE, Serial, `-Xmn400m`", ""),
    ("iter8-native-g1", "java-native-opt", "Native Oracle, G1, heap no padrão (25%)", ""),
    ("iter9-native-g1-70", "java-native-opt", "Native Oracle, G1, heap de 70%", ""),
]


def diag(directory, target, level):
    path = os.path.join(RESULTS, "diagnostico-opt", directory)
    for r in g.load_rounds(path):
        if r["target"] == target and r["vus"] == level:
            return r
    return None


def diag_cells(r):
    k6 = r["k6"]
    p99 = k6["latency_ms"]["p99"]
    oom = "kill" if r["oom"] else ("heap" if r["heap_oom"] else "não")
    return [g.num(k6["rps"], 1), g.pct(k6["error_rate"], 1), g.num(None if p99 is None else p99 - 5000, 1),
            mib(r["stats"]["mem_peak"], 0), oom]


def jetty_steps_table():
    head = ["Etapa", "Configuração", "Limite", "req/s (de 2.000)", "Erros", "Overhead p99 (ms)", "Memória pico (MiB)", "OOM", "O que mostrou"]
    rows = []
    for i, (directory, target, level, limit, config, finding) in enumerate(JETTY_STEPS, 1):
        r = diag(directory, target, level)
        name = f"`diagnostico-opt/{directory}`" if directory else "`diagnostico-opt`"
        rows.append([f"{i}. {name}", config, limit] + diag_cells(r) + [finding])
    return table(head, rows, wrap=(0, 1, 8))


def gc_steps_table():
    head = ["Diagnóstico", "Configuração", "VUs", "req/s real", "Erros", "Overhead p99 (ms)", "Memória pico (MiB)", "OOM"]
    rows = []
    for directory, target, config, _ in GC_STEPS:
        for level in (5000, 10000):
            r = diag(directory, target, level)
            if r:
                rows.append([f"`{directory}`", config, g.num(level)] + diag_cells(r))
    return table(head, rows, wrap=(1,))


# ---------------- conteúdo ----------------

CSS = g.CSS + """
h4{font-size:15px;margin:22px 0 6px}
a{color:#1f5fae}
nav ol{columns:2;max-width:80ch;padding-left:20px;margin:8px 0 0}
nav li{margin:2px 0}
pre{background:#f1f1ed;padding:12px 14px;border-radius:6px;overflow-x:auto;font-size:13px;line-height:1.45;max-width:100%}
pre code{background:none;padding:0;font-size:inherit}
.caption{font-size:13px;color:#6b6b68;margin:16px 0 4px}
.lead{font-size:17px;max-width:80ch}
td.wrap{min-width:150px}
td.wrap code{overflow-wrap:anywhere}
@media (max-width:700px){nav ol{columns:1}}
"""

SECTIONS = [
    ("resumo", "Resumo"),
    ("numeros", "Todos os alvos com 10.000 VUs"),
    ("metodo", "Como o teste funciona"),
    ("taxa-explicada", "Dois modos de carga: VUs e 100 req/s"),
    ("rodadas", "Rodadas e relatórios completos"),
    ("versoes", "Ambiente e versões"),
    ("startup", "Startup"),
    ("padrao", "Trilha padrão: Java vs Go"),
    ("rust", "Rust vs Go"),
    ("otimizada", "Trilha otimizada"),
    ("jetty", "Java: do Tomcat ao Jetty"),
    ("taxa", "Carga constante de 100 req/s"),
    ("python", "Trilha Python"),
    ("limites", "Limites destas conclusões"),
]


def build():
    out = []
    add = out.append

    add(h(1, "Benchmark de I/O: Java, Go, Rust e Python esperando uma API lenta"))
    add(f'<p class="lead">{inline("Cada requisição recebida chama uma API externa que demora **5 s** e devolve a resposta, sem trabalho de CPU no handler. Cada alvo roda sozinho em um container com **2 vCPU e 1 GB**. A pergunta é quanto cada plataforma gasta em memória, CPU e latência para manter milhares de chamadas paradas ao mesmo tempo.")}</p>')
    add(p("Esta página reúne as cinco rodadas completas: a trilha padrão (Java na JVM, Java em Native Image e Go), o Rust, "
          "a trilha otimizada, com o Java migrado de Tomcat para Jetty, a carga constante de 100 req/s e a trilha Python. "
          "Os valores são a **mediana de 3 repetições**, com 30 s de warm-up e 180 s medidos. O código e os dados brutos estão em "
          f"[{REPO.split('/', 3)[3]}]({REPO})."))
    add('<nav><strong>Conteúdo</strong><ol>' + "".join(f'<li><a href="#{a}">{html.escape(t)}</a></li>' for a, t in SECTIONS) + "</ol></nav>")

    # ---- Resumo
    add(h(2, "Resumo", "resumo"))
    add(ul([
        "**Na configuração padrão, só Go e Rust atenderam aos três níveis.** Com 10.000 VUs, o Go fez 1.999,6 de 2.000 req/s com 407 MiB "
        "de pico e o Rust 1.999,4 com 629 MiB. Java na JVM (Tomcat) e em Native Image tiveram 100% de erros por falta de memória.",
        "**Otimizado, todo alvo Java atendeu a 10.000 VUs em 1 GB, sem erros.** O que mais pesou foi trocar o Tomcat pelo Jetty e "
        "remover dois limites do Jetty: o pool de 200 tarefas e o cache de cabeçalhos de cerca de 100 KB por conexão. A JVM com G1 fez "
        "1.992,5 req/s com 953 MiB de pico, ainda 2,8 vezes a memória e 5,4 vezes a CPU por requisição do Go otimizado.",
        "**No Native Image, o coletor decide.** Com Serial (GraalVM CE), ficou em 1.650,3 req/s (82,5% do ideal) com 10.000 VUs. "
        "Com G1 (Oracle GraalVM), fez 1.996,0 req/s.",
        "**Com 100 req/s constantes, os 10 alvos atenderam sem erros e sem iterações descartadas.** A diferença foi só custo: memória "
        "de pico de 24,8 MiB (Go otimizado) a 430,9 MiB (JVM padrão) e CPU de 0,161 a 1,576 CPU-s por 1.000 requisições.",
        "**Em Python, a pilha decide.** Só o aiohttp puro acompanhou o Go com 10.000 VUs, com 3,2 vezes a CPU por requisição. "
        "FastAPI + httpx teve 100% de erros desde 5.000 VUs, por um custo quadrático no pool de conexões do `httpcore`.",
        "**Startup:** Go, Rust e Native ficam prontos em 120 a 164 ms. A JVM leva 2.319 ms, ou 1.156 ms com AOT Cache. "
        "Python fica entre 315 e 638 ms.",
    ]))
    add(img(os.path.join(RESULTS, OPT, "charts", "visao-geral.png"),
            "Visão geral: startup, CPU por requisição e memória de pico com 5.000 e 10.000 VUs, padrão e otimizado"))

    # ---- Números
    add(h(2, "Todos os alvos com 10.000 VUs", "numeros"))
    add(p("O nível mais pesado da carga por VUs, com 2.000 req/s ideais. Cada linha vem da rodada completa em que o alvo foi medido. "
          "O Go se repetiu como controle nas rodadas de Rust e Python e ficou dentro de 0,1 req/s, 0,1 ms de overhead e 1 MiB de pico "
          "em relação à trilha padrão. O traço indica que o alvo não entregou respostas 200 ou já tinha sido encerrado. Em quem "
          "falhou, a memória só mostra que o limite foi atingido: no FastAPI + httpx, ela não indica eficiência, porque nada foi entregue."))
    add(summary_table(10000))

    # ---- Método
    add(h(2, "Como o teste funciona", "metodo"))
    add(pre("""
k6 (4 vCPU) ──> alvo (2 vCPU / 1 GB) ──> mock-api (4 vCPU / 2 GB, responde em 5 s)
                um alvo por vez: Go, Java JVM, Java Native, Rust ou Python, padrão ou otimizado
"""))
    add(p("Todos os alvos têm o mesmo contrato: `GET /health` responde `200 ok`, e `GET /api/io` chama a mock-api por HTTP/1.1 e devolve "
          "o JSON de 35 bytes que recebeu, ou 502 se a chamada falhar. Os containers ficam na mesma rede do Docker Compose, um alvo de "
          "cada vez, com `nofile`, `somaxconn` e faixa de portas ampliados em todos. Mock-api e k6 têm o dobro de CPU do alvo e são "
          "monitorados: picos acima de 320% de CPU são sinalizados, e saturação invalida a rodada."))
    add(h(3, "O que é medido"))
    add(ul([
        "**req/s real:** só respostas 200, iniciadas dentro da janela de 180 s. Erros rápidos não inflam o número.",
        "**Overhead p99:** o p99 da latência menos os 5.000 ms da mock-api. É o que o alvo acrescenta.",
        "**Memória:** `usage - inactive_file` do container, uma amostra por segundo pela API do Docker. O pico é comparado com o limite de 1.024 MiB.",
        "**CPU-s por 1.000 requisições:** CPU consumida na janela dividida pelas respostas 200. É a medida de eficiência que desconta o throughput.",
        "**Startup:** do start do container até o primeiro `/health` com 200, em 10 execuções, medido de fora e incluindo o custo do Docker.",
        "**OOM:** `kill` quando o kernel encerra o processo; `heap` quando o log tem `OutOfMemoryError` e o container continua de pé.",
    ]))

    add(h(2, "Dois modos de carga: VUs e 100 req/s", "taxa-explicada"))
    add(p("Na **carga por VUs** (`MODE=vus`, executor `constant-vus` do k6), cada usuário virtual chama `/api/io`, espera a resposta e "
          "chama de novo, sem pausa. Como a mock-api leva 5 s, o throughput ideal é o número de VUs dividido por 5: 1.000 VUs dão 200 req/s, "
          "5.000 dão 1.000 e 10.000 dão 2.000, e o alvo sempre tem tantas chamadas paradas quanto VUs. É um modelo fechado: quando o "
          "alvo atrasa, cada VU demora mais para repetir e o throughput cai sozinho. Foi o que aconteceu com o Native com 5.000 VUs na "
          "trilha padrão, que fez 866,6 req/s com 0 erros. Pausas de GC levaram a latência mediana para 5,67 s, e 5.000 / 5,67 s dá cerca "
          "de 880 req/s. Por isso a lentidão aparece aqui como req/s abaixo do ideal, e não como fila. Cada VU começa com um atraso "
          "aleatório de até 5 s, para as chamadas não chegarem em ondas."))
    add(p("Na **carga por taxa** (`MODE=rate`, executor `constant-arrival-rate`), o k6 inicia exatamente 100 requisições por segundo, "
          "responda o alvo rápido ou devagar. É um modelo aberto, como o tráfego que chega de fora num serviço real: se o alvo ficar "
          "lento, as chamadas se acumulam em vez de diminuir. Com 100 req/s e 5 s de espera, ficam cerca de **500 chamadas em andamento** "
          "(100 × 5), metade das 1.000 do menor nível por VUs. O k6 pré-aloca 600 VUs (6 vezes a taxa) e pode chegar a 4.000 (40 vezes). "
          "Se precisasse de mais, a iteração seria descartada e contada em `dropped_iterations`. Nas 30 rodadas, nenhuma foi descartada."))
    add(p("A rodada de 100 req/s não mede capacidade, porque todos os alvos sobram. Ela mostra o **custo em carga leve e estável**: quanta "
          "memória e CPU cada plataforma consome para atender a mesma demanda moderada, e se as otimizações feitas para 10.000 VUs "
          "pioram algo quando a carga é baixa. Nesse modo, o req/s ideal é a própria taxa. A janela, o warm-up e as 3 repetições são os "
          "mesmos da carga por VUs, e o startup não é medido de novo, porque não depende do modo de carga."))
    add(pre("""
# Carga por VUs (padrão): 1.000, 5.000 e 10.000 VUs, 3 repetições
TARGETS="go-fiber java-jvm java-native rust-axum" scripts/run-all.sh

# Carga constante de 100 req/s nos 10 alvos, sem medir startup
MODE=rate LEVELS=100 STARTUP_RUNS=0 \\
TARGETS="go-fiber java-jvm java-native rust-axum go-fiber-opt java-jvm-opt java-jvm-zgc java-native-opt java-native-g1 rust-axum-opt" \\
scripts/run-all.sh
""", "Comandos das duas cargas"))

    # ---- Rodadas
    add(h(2, "Rodadas e relatórios completos", "rodadas"))
    add(p("Cada rodada completa tem um relatório próprio, com todas as tabelas, gráficos, sanidade do ambiente e cada repetição. "
          "Rodadas de validação, testes de limite e diagnósticos ficam em diretórios separados e não entram nas medianas."))
    add(table(["Rodada", "O que mede", "Alvos", "Carga", "Relatório"], [
        [f"`{STD}`", "Trilha padrão: comparativos A e B", "Go, Java JVM, Java Native", "1.000, 5.000 e 10.000 VUs",
         f"[resultados-{STD}.html](resultados-{STD}.html)"],
        [f"`{RUST}`", "Rust, com Go como controle: comparativo C", "Go, Rust", "1.000, 5.000 e 10.000 VUs",
         f"[resultados-{RUST}.html](resultados-{RUST}.html)"],
        [f"`{OPT}`", "Trilha otimizada: comparativos D a L", "6 alvos otimizados", "1.000, 5.000 e 10.000 VUs",
         f"[resultados-{OPT}.html](resultados-{OPT}.html)"],
        [f"`{RATE}`", "Carga constante", "10 alvos, padrão e otimizados", "100 req/s",
         f"[resultados-{RATE}.html](resultados-{RATE}.html)"],
        [f"`{PY}`", "Trilha Python: comparativo M", "Go e 5 pilhas Python", "1.000, 5.000 e 10.000 VUs",
         f"[resultados-{PY}.html](resultados-{PY}.html)"],
    ]))
    add(p("À parte: validações e testes de limite em `20261102-003704`, `20261102-004409`, `20261102-172609`, `20261102-172853`, "
          "`20261102-195236` (100 req/s com 30 s medidos) e `20261103-162014` (interrompido). Diagnósticos em `diagnostico-gc`, "
          "`diagnostico-native-2g`, `diagnostico-opt` e `diagnostico-python`, todos em "
          f"[results/]({REPO}/tree/main/results)."))

    # ---- Versões
    add(h(2, "Ambiente e versões", "versoes"))
    add(p("Todas as rodadas usaram a mesma máquina e o mesmo Docker. Versões verificadas em 02/11/2026 (Java, Go, Rust) e 03/11/2026 (Python)."))
    add(table(["Componente", "Versão"], [
        ["Host", "16 vCPU x86_64, 30,8 GiB, Ubuntu 24.04.5 LTS, kernel 7.0.0-1014-aws, Docker 29.9.2"],
        ["Go, Fiber, fasthttp", "1.27.3, v3.6.1, v1.77.0"],
        ["Spring Boot", "4.1.2, com Tomcat 11.0.27 (padrão) ou Jetty 12.1.14 (otimizado)"],
        ["JVM", "Temurin 27+35 (`eclipse-temurin:27-jre`)"],
        ["Native Image", "GraalVM CE 25.4.4.1.1, JDK 25.0.4.1. Na variante G1: Oracle GraalVM `native-image:25-ol9`, licença GFTC"],
        ["Rust, Axum, hyper, reqwest, Tokio", "1.99.1, 0.8.9, 1.12.0, 0.13.5, 1.54.1. No otimizado: mimalloc 0.1.52"],
        ["Python", "3.15.2 (`python:3.15.2-slim-bookworm`)"],
        ["FastAPI, uvicorn, uvloop, httptools", "0.162.0, 0.54.0, 0.23.0, 0.9.0"],
        ["httpx, httpcore, aiohttp", "0.28.1, 1.0.9, 3.14.5"],
        ["Flask, requests, gunicorn, gevent", "3.1.3, 2.34.2, 26.2.0, 26.9.0"],
        ["k6", "2.3.0"],
    ]))
    add(p("**Não existe GraalVM para o JDK 27.** O código Java é compilado com `java.version=25`: a variante JVM roda no JDK 27 e o Native "
          "Image é gerado com o JDK 25. Comparar JVM com Native mistura, portanto, compilação nativa, coletor e versão do JDK."))

    # ---- Startup
    add(h(2, "Startup", "startup"))
    add(startup_table())
    add(p("O tempo até ficar pronto inclui o custo do Docker. A JVM otimizada usa AOT Cache, que caiu de 2.319 para 1.156 ms e aumentou a "
          "imagem de 512,6 para 638,9 MB. A primeira requisição da JVM gasta cerca de 105 ms além dos 5 s, contra 6 a 8 ms de Go, Rust e "
          "Native, provavelmente por carregamento de classes e código ainda interpretado. O Native com G1 tem imagem maior (199,9 MB, contra "
          "126,8 MB com Serial), e o Rust usa `distroless/cc` (39 a 40 MB, contra 20,3 MB do Go)."))

    # ---- Padrão
    add(h(2, "Trilha padrão: Java vs Go", "padrao"))
    add(p("Java com Spring Boot 4.1.2, Tomcat e virtual threads, na JVM (G1, heap de 75%) e em Native Image (Serial GC, heap de 80%), "
          "contra Go com Fiber. Só foram removidos limites artificiais: conexões máximas, fila de aceitação e keep-alive do Tomcat, "
          "conexões por host do cliente do Go."))
    add(load_table(["go-fiber", "java-jvm", "java-native"], [1000, 5000, 10000]))
    add(ul([
        "**Com 1.000 VUs, todos entregam o ideal, e a diferença está no custo:** 46 MiB no Go, 297 MiB no Native e 450 MiB na JVM; "
        "0,137, 0,489 e 0,694 CPU-s por 1.000 requisições.",
        "**Native com 5.000 VUs:** com log de GC, 47,8% do tempo em pausa, com Full GCs de cerca de 600 ms em sequência no Serial. "
        "A JVM com G1 ficou em 8,7%, com mediana de 18 ms. Com 2 GB, só como contraprova, o Native fez 912,8 req/s, ainda abaixo de 95%.",
        "**Java com 10.000 VUs:** a memória acaba nos primeiros segundos da subida dos VUs. A JVM registra `OutOfMemoryError`, fica em "
        "cerca de 197% de CPU e para de responder. O Native é encerrado pelo kernel por volta de 5 s.",
    ]))

    # ---- Rust
    add(h(2, "Rust vs Go", "rust"))
    add(p("Rust com Axum, hyper e reqwest, só HTTP/1.1, sem LTO e com o alocador da glibc. O Go foi repetido na mesma rodada como controle."))
    add(load_table(["go-fiber", "rust-axum"], [1000, 5000, 10000], directory=RUST))
    add(p("Latência igual nos três níveis, com diferença de até 0,1 ms no overhead p99. O Rust usou cerca de 50% mais memória de pico "
          "e de 11% a 27% mais CPU por requisição. Parado, usa menos memória que o Go (1,8 contra 3,4 MiB). O resultado compara pilhas, "
          "não linguagens: o fasthttp do Go reaproveita buffers, e o Rust padrão não tinha ajuste de buffer nem de alocador. "
          "A trilha otimizada mostra o efeito desses ajustes."))

    # ---- Otimizada
    add(h(2, "Trilha otimizada", "otimizada"))
    add(p("Mesmo contrato, mesma carga e os mesmos 2 vCPU e 1 GB. Os alvos padrão continuam intactos. Cada ajuste veio de uma medição, "
          "e as rodadas de diagnóstico estão em `results/diagnostico-opt/`."))
    add(table(["Alvo", "O que muda em relação ao padrão", "Por quê"], [
        ["`go-fiber-opt`", "Buffers de leitura e escrita de 2 KiB no Fiber e no cliente fasthttp; `GOMEMLIMIT=900MiB`",
         "O padrão é de 4 KiB por conexão. Os cabeçalhos ficam limitados a 2 KiB"],
        ["`rust-axum-opt`", "`hyper` direto no lugar do `reqwest`; buffer de leitura fixo de 2 KiB; `mimalloc` com `MIMALLOC_PURGE_DELAY=0`; "
         "LTO `fat`, `codegen-units=1`, `panic=abort`",
         "O `hyper` direto trouxe a maior parte do ganho. Com os padrões, o `mimalloc` usou mais memória que a glibc"],
        ["`java-jvm-opt`", "Jetty no lugar do Tomcat, com `VirtualThreadPool(20000)` e `headerCacheSize=0`; cabeçalhos de 2 KiB; "
         "`jdk.httpclient.bufsize=2048`; Compact Object Headers; AOT Cache; heap de 70%; G1",
         "O Tomcat fixa cerca de 32 KB de `char[]` por conexão, sem ajuste. Detalhes na próxima seção"],
        ["`java-jvm-zgc`", "Igual ao `java-jvm-opt`, com ZGC e heap de 60%", "Compara o coletor"],
        ["`java-native-opt`", "Mesmo código Jetty, GraalVM CE, Serial GC, `-Xmn400m`", "A CE só oferece Serial e Epsilon"],
        ["`java-native-g1`", "Mesmo código Jetty, Oracle GraalVM com `--gc=G1`, heap de 70%", "Outra distribuição, com licença GFTC"],
    ], wrap=(1, 2)))
    add(load_table(["go-fiber-opt", "rust-axum-opt", "java-jvm-opt", "java-jvm-zgc", "java-native-opt", "java-native-g1"],
                   [1000, 5000, 10000]))
    add(ul([
        "**O maior ganho do Java veio da troca do servidor e dos ajustes por conexão, não do coletor.**",
        "**ZGC só compensa até certa carga.** Com 5.000 VUs, teve overhead p99 de 5,0 ms contra 57,2 ms do G1, com 49% mais CPU por "
        "requisição. Com 10.000 VUs, ficou pior em tudo: 848,9 ms contra 88,2 ms, 2,7 vezes a CPU e 1.016 MiB de pico, a 8 MiB do limite.",
        "**Native com Serial ficou abaixo de 95% do ideal com 10.000 VUs nas 3 repetições.** Os diagnósticos mostram pausas de 150 a 200 ms.",
        "**Rust e Go otimizados têm latência igual e custos invertidos.** Com 10.000 VUs, o Go usa menos memória (343 contra 543 MiB) "
        "e o Rust, menos CPU (0,054 contra 0,059 CPU-s por 1.000 requisições).",
        "**Nem toda otimização melhorou tudo.** Com 1.000 VUs, a memória de pico da JVM subiu de 449,9 para 502,9 MiB.",
    ]))

    # ---- Jetty
    add(h(2, "Java: do Tomcat ao Jetty", "jetty"))
    add(p("Com Tomcat, a JVM esgotava 1 GB com 10.000 VUs. Para saber onde a memória ia, o alvo padrão rodou com 4 GB e teve o heap "
          "inspecionado com `jmap -histo`. Com 10.000 conexões, havia 329 MB em 40.247 arrays `char[]`, cerca de 32,9 KB por conexão, e "
          "758 MB em `byte[]`, além de cerca de 300 mil objetos `ByteChunk`, `CharChunk` e `MessageBytes` do Tomcat. A geração old do G1 "
          "ocupava cerca de 1.330 MiB, mais que o heap inteiro disponível em 1 GB (768 MiB). Não há propriedade do Tomcat que reduza "
          "esses `char[]` por conexão, então o servidor foi trocado."))
    add(p("A troca para o Jetty não funcionou de primeira: com os padrões, ele travou num limite de concorrência e, depois, o cache de "
          "cabeçalhos ocupou quase 1 GB sozinho. A sequência abaixo mostra cada etapa, com 10.000 VUs e 60 s medidos, uma repetição."))
    add(jetty_steps_table())
    add(h(3, "Cada mudança, arquivo por arquivo"))
    add(table(["Arquivo", "Mudança", "Padrão", "Usado", "Motivo e efeito medido"], [
        ["`pom.xml`", "Exclui `spring-boot-starter-tomcat` de `spring-boot-starter-web` e adiciona `spring-boot-starter-jetty`",
         "Tomcat 11.0.27", "Jetty 12.1.14", "O Tomcat fixa cerca de 32 KB de `char[]` por conexão, sem ajuste"],
        ["`JettyConfig.java`", "`factory.setThreadPool(new VirtualThreadPool(20000))`", "200 tarefas simultâneas", "20.000",
         "Com 5 s de espera, 200 tarefas dão no máximo 40 req/s. Com 10.000 VUs, 100% das requisições estouraram o timeout de 30 s do k6"],
        ["`JettyConfig.java`", "`HttpConfiguration.setHeaderCacheSize(0)` em cada conector", "cache ligado, por conexão", "desligado",
         "Com o cache, 984 MB de `char[]` com 10.000 conexões, cerca de 98 KB cada. Sem ele, o processo cabe em 1 GB"],
        ["`application.properties`", "`server.max-http-request-header-size=2KB`", "8 KB", "2 KB",
         "Mesmo limite do Go otimizado. Menos buffer por conexão"],
        ["`application.properties`", "`server.jetty.max-http-response-header-size=2KB`", "8 KB", "2 KB", "Idem, na resposta"],
        ["`application.properties`", "`server.jetty.connection-idle-timeout=60s`", "30 s (Jetty)", "60 s",
         "Conexões ociosas duram o mesmo que o keep-alive de 60 s dos outros alvos"],
        ["`application.properties`", "Remove `server.tomcat.*`", "-", "-",
         "`max-connections`, `accept-count`, `max-keep-alive-requests` e `keep-alive-timeout` não se aplicam ao Jetty"],
        ["`HttpClientConfig.java`", "`System.setProperty(\"jdk.httpclient.bufsize\", \"2048\")`", "16 KiB por conexão", "2 KiB",
         "O cliente HTTP do JDK guarda um buffer por conexão com a mock-api. Precisa ser definido antes do primeiro uso do `HttpClient`"],
        ["`HttpClientConfig.java`", "`System.setProperty(\"jdk.httpclient.keepalive.timeout\", \"60\")`", "30 s", "60 s",
         "Mantém as conexões com a mock-api pelo mesmo tempo dos outros alvos"],
        ["`Dockerfile.jvm`", "`-XX:+UseCompactObjectHeaders`", "desligado", "ligado",
         "Cabeçalho de objeto menor, com milhões de objetos pequenos no heap. O efeito isolado não foi medido"],
        ["`Dockerfile.jvm`", "AOT Cache: treino no build com `-XX:AOTCacheOutput` e `-Dspring.context.exit=onRefresh`; execução com `-XX:AOTCache`",
         "sem cache", "`/opt/app/app.aot`",
         "Startup de 2.319 para 1.156 ms. Exige o JAR extraído (`-Djarmode=tools extract`) e as mesmas flags de JVM e coletor no treino e na execução"],
        ["`Dockerfile.jvm`", "`-XX:MaxRAMPercentage=70`", "75%", "70%",
         "Com 75%, o pico chegou a 1.004 MiB, a 20 MiB do limite. Com 70%, sobra mais espaço fora do heap, e a cauda melhorou"],
        ["`Dockerfile.zgc`", "`-XX:+UseZGC` e `-XX:MaxRAMPercentage=60`, com o AOT Cache treinado também com ZGC", "G1, 75%", "ZGC, 60%",
         "Sem AOT Cache, o ZGC foi encerrado pelo kernel com 10.000 VUs, com heap de 70% e de 60%"],
        ["`docker-compose.yml`", "`command: [\"-Xmn400m\"]` no `java-native-opt`", "geração jovem automática", "400 MB",
         "Nos diagnósticos, melhorou throughput e cauda com 5.000 VUs. Com 10.000 VUs, piorou o throughput (1.623,1 contra 1.759,8 req/s), e nenhum tamanho levou o Serial a 95% do ideal"],
        ["`Dockerfile.native-g1`", "Oracle GraalVM, `NATIVE_IMAGE_OPTIONS=--gc=G1`, `distroless/cc`, `-XX:MaxRAMPercentage=70`",
         "Serial, 80%", "G1, 70%",
         "Com o heap padrão do G1 (25%), `OutOfMemoryError` com 10.000 VUs. A imagem precisa da `libgcc_s`, ausente no `distroless/base`"],
    ], wrap=(0, 1, 2, 3, 4)))
    add(h(3, "O código"))
    add(pre("""
@Configuration
public class JettyConfig {

    // O VirtualThreadPool limita a 200 tarefas simultâneas por padrão: só 40 req/s com 5s de espera.
    private static final int MAX_CONCURRENT = 20000;

    @Bean
    @Order(Ordered.LOWEST_PRECEDENCE)
    WebServerFactoryCustomizer<JettyServletWebServerFactory> jettyLimits() {
        return factory -> {
            factory.setThreadPool(new VirtualThreadPool(MAX_CONCURRENT));
            // Cada conexão mantém o próprio cache de cabeçalhos, cerca de 100 KB por conexão.
            factory.addServerCustomizers(server -> {
                for (var connector : server.getConnectors()) {
                    var http = connector.getConnectionFactory(HttpConnectionFactory.class);
                    if (http != null) {
                        http.getHttpConfiguration().setHeaderCacheSize(0);
                    }
                }
            });
        };
    }
}
""", "`opt/java-spring/src/main/java/bench/JettyConfig.java`"))
    add(p("O customizador roda com a menor precedência para ser aplicado depois da configuração automática do Spring Boot, que também "
          "define o pool quando `spring.threads.virtual.enabled=true`. O cache de cabeçalhos é desligado nos conectores já criados, "
          "por isso o ajuste usa `addServerCustomizers`."))
    add(pre("""
spring.threads.virtual.enabled=true
# Mesmo limite de 2 KiB de cabeçalhos do Go otimizado.
server.max-http-request-header-size=2KB
server.jetty.max-http-response-header-size=2KB
server.jetty.connection-idle-timeout=60s
""", "`opt/java-spring/src/main/resources/application.properties`"))
    add(pre("""
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-web</artifactId>
  <exclusions>
    <exclusion>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-tomcat</artifactId>
    </exclusion>
  </exclusions>
</dependency>
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-jetty</artifactId>
</dependency>
""", "`opt/java-spring/pom.xml`"))
    add(pre("""
RUN java -Djarmode=tools -jar /tmp/app.jar extract --destination /opt/app && rm /tmp/app.jar
# O cache AOT precisa ser gerado com a mesma JVM e as mesmas flags de execução.
RUN java -XX:+UseCompactObjectHeaders -XX:AOTCacheOutput=/opt/app/app.aot -Dspring.context.exit=onRefresh -jar /opt/app/app.jar
ENTRYPOINT ["java","-XX:MaxRAMPercentage=70","-XX:+UseCompactObjectHeaders","-XX:AOTCache=/opt/app/app.aot","-jar","/opt/app/app.jar"]
""", "`opt/java-spring/Dockerfile.jvm` (trecho)"))
    add(h(3, "Coletores: diagnósticos de JVM e Native"))
    add(p("Mesmo código Jetty, 60 s medidos, uma repetição. Mostram por que a JVM ficou com G1 e 70%, o ZGC com 60% e AOT Cache, e o "
          "Native com G1 com 70%."))
    add(gc_steps_table())
    add(h(3, "O que estes ajustes custam"))
    add(ul([
        "**Cabeçalhos:** o limite de 2 KiB serve para este teste, mas pode rejeitar requisições reais com cookies ou tokens grandes. "
        "O mesmo vale para o Go otimizado.",
        "**Cache de cabeçalhos:** desligá-lo pode custar CPU na leitura dos cabeçalhos de cada requisição. Esse efeito não foi medido isoladamente.",
        "**Concorrência quase sem limite:** com `VirtualThreadPool(20000)`, o servidor aceita até 20.000 tarefas simultâneas. Se um "
        "limite for necessário em produção, ele precisa vir de outro lugar, como um limitador de requisições.",
        "**Respostas maiores:** o teste devolve 35 bytes. Buffers de 2 KiB podem custar mais com corpos grandes.",
        "**Comparabilidade:** o Java otimizado não é a mesma aplicação com outras flags, porque o servidor HTTP mudou. "
        "O Native com G1 também muda de distribuição.",
    ]))

    # ---- Taxa
    add(h(2, "Carga constante de 100 req/s", "taxa"))
    add(p(f"Rodada `{RATE}`: os 10 alvos Java, Go e Rust, padrão e otimizados, com 100 req/s constantes, cerca de 500 chamadas em "
          "andamento, 3 repetições de 180 s. Python não foi medido neste modo."))
    add(rate_table())
    add(ul([
        "**Todos sustentaram 100 req/s, sem erros e sem iterações descartadas.** O que muda é o custo e a cauda.",
        "**Memória:** de 24,8 MiB (Go otimizado) a 430,9 MiB (JVM padrão). A JVM com Jetty caiu para 266,6 MiB, 38% a menos que com Tomcat.",
        "**Go e Rust melhoraram sem custo aparente:** o Go foi de 28,9 para 24,8 MiB de pico, e o Rust de 41,7 para 34,0 MiB, com CPU por "
        "1.000 requisições de 0,200 para 0,161.",
        "**O coletor define a cauda do Native:** overhead p99 de 26,1 ms com Serial, com ou sem `-Xmn400m`, e de 3,3 ms com G1.",
        "**O ZGC tem a menor latência máxima da JVM:** 5.004,4 ms, contra 5.019,3 ms com G1, com 39% mais memória de pico.",
        "**Com carga leve, o Java otimizado gastou mais CPU:** a JVM foi de 1,198 para 1,518 CPU-s por 1.000 requisições, e o Native com "
        "Serial, de 0,869 para 1,001. A causa não foi investigada, e os valores absolutos são baixos, até cerca de 16% de 1 core.",
    ]))

    # ---- Python
    add(h(2, "Trilha Python", "python"))
    add(p("Cinco pilhas, com o Go como controle na mesma rodada. Cada alvo usa 2 workers, um por vCPU, porque o GIL impede um processo de "
          "usar os dois. Só foram removidos limites artificiais: pools de conexão sem limite (o padrão do httpx e do aiohttp é 100, e o do "
          "requests, 10), timeout de 10 s no cliente como no Go (o padrão do httpx é 5 s, a mesma latência da mock-api), backlog de "
          "65535, keep-alive de 60 s, `--worker-connections 20000` no gevent e `--threads 10000` nas threads. Nenhuma pilha foi "
          "otimizada como na trilha `opt/`."))
    add(table(["Alvo", "Pilha", "Modelo de concorrência"], [
        ["`py-fastapi`", "FastAPI + uvicorn + httpx", "asyncio"],
        ["`py-fastapi-aiohttp`", "FastAPI + uvicorn + cliente do aiohttp", "asyncio"],
        ["`py-aiohttp`", "aiohttp como servidor e cliente, com gunicorn", "asyncio"],
        ["`py-flask-gevent`", "Flask + gunicorn + requests", "greenlets"],
        ["`py-flask-threads`", "Flask + gunicorn + requests", "threads do sistema"],
    ]))
    add(load_table(["go-fiber", "py-aiohttp", "py-fastapi-aiohttp", "py-fastapi", "py-flask-gevent", "py-flask-threads"],
                   [1000, 5000, 10000], directory=PY))
    add(ul([
        "**aiohttp empatou com o Go em throughput e latência, e paga em CPU:** 0,185 contra 0,057 CPU-s por 1.000 requisições com "
        "10.000 VUs, e 13% menos memória de pico (353 contra 408 MiB). Com 1.000 VUs, a memória se inverte: 85 contra 46 MiB.",
        "**O colapso do FastAPI + httpx vem do cliente.** Com 5.000 e 10.000 VUs, 100% de erros nas 6 rodadas, com CPU em 200% e sem OOM. "
        "Trocando só o cliente pelo do aiohttp, o FastAPI atende. O perfil do cliente isolado concentra o tempo em `httpcore`, no "
        "`is_idle` chamado por `_assign_requests_to_connections`: cerca de 95 milhões de chamadas em 20 s com 500 chamadas simultâneas. "
        "O código percorre todas as conexões para cada conexão ociosa, um custo quadrático.",
        "**O httpx já custa caro antes de colapsar:** com 1.000 VUs, 1,966 CPU-s por 1.000 requisições, 4,1 vezes o FastAPI com cliente "
        "aiohttp, e overhead p99 de 98,0 ms contra 2,5 ms.",
        "**FastAPI com cliente aiohttp vai até 5.000 VUs sem custo de latência.** Com 10.000 VUs, ficou em 97,5% do ideal, com overhead "
        "p99 de 897,6 ms.",
        "**gevent e threads não aguentam 10.000 VUs em 1 GB.** O kernel encerrou workers em todas as rodadas desse nível: de 2 a 4 no "
        "gevent e de 35 a 39 nas threads. O OOM é de worker, contado no cgroup, e o container continua de pé.",
    ]))
    add(img(os.path.join(RESULTS, PY, "charts", "memoria_pico.png"), "Python: memória de pico por VUs"))
    add(img(os.path.join(RESULTS, PY, "charts", "cpu_por_1000.png"), "Python: CPU-s por 1.000 requisições por VUs"))

    # ---- Limites
    add(h(2, "Limites destas conclusões", "limites"))
    add(ul([
        "**O cenário é só espera de I/O:** sem trabalho de CPU no handler, TLS, serialização relevante ou banco. Em Python, CPU real "
        "disputaria o mesmo event loop.",
        "**Os resultados valem para 2 vCPU e 1 GB.** O fracasso do Java padrão com 10.000 VUs não mostra que ele não aguente essa carga "
        "com mais memória.",
        "**A memória da JVM não é o mínimo necessário.** O coletor ocupa o heap disponível antes de coletar, e o mesmo vale para o Native com G1.",
        "**Comparações entre rodadas são indiretas.** Go, Rust, Java e Python foram medidos em rodadas diferentes na mesma máquina. "
        "O Go repetido como controle variou muito pouco, mas diferenças pequenas não devem ser lidas como efeito.",
        "**Os ajustes otimizados foram feitos para este teste** e não valem automaticamente para produção.",
        "**Os tempos autodeclarados de Go, Rust e Python não são comparáveis.** Use o tempo até ficar pronto.",
    ]))
    add(p(f"Metodologia completa, ajustes e comandos no [README]({REPO}#readme). Prompt para reexecutar: "
          f"[docs/prompt-reexecucao.md]({REPO}/blob/main/docs/prompt-reexecucao.md)."))

    title = "Benchmark de I/O: Java, Go, Rust e Python"
    return ('<!doctype html>\n<html lang="pt-BR"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{title}</title><style>{CSS}</style></head><body><main>\n" + "\n".join(out) + "\n</main></body></html>\n")


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "docs", "index.html")
    with open(target, "w", encoding="utf-8") as f:
        f.write(build())
    print(target)


if __name__ == "__main__":
    main()
