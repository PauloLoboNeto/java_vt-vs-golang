#!/usr/bin/env python3
"""Gera report.md, report.html e charts/*.png: generate.py <dir> [referências...].

As referências são rodadas anteriores, usadas só para os alvos ausentes em <dir>. Elas entram nas
tabelas e gráficos dos comparativos, mas não nas seções de sanidade e de rodadas. Sem matplotlib, só tabelas.
"""
import base64
import csv
import glob
import html
import json
import os
import re
import statistics
import sys

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError:
    plt = None

TARGETS = {
    "go-fiber": {"label": "Go (Fiber)", "short": "Go", "color": "#2a78d6"},
    "java-jvm": {"label": "Java JVM (JDK 27)", "short": "JVM", "color": "#eb6834"},
    "java-native": {"label": "Java Native Image (JDK 25)", "short": "Native", "color": "#1baf7a"},
    "rust-axum": {"label": "Rust (Axum)", "short": "Rust", "color": "#8e5bd0"},
    "go-fiber-opt": {"label": "Go (Fiber) otimizado", "short": "Go opt", "color": "#0f3f86"},
    "java-jvm-opt": {"label": "Java JVM otimizado", "short": "JVM opt", "color": "#9c3c13"},
    "java-native-opt": {"label": "Java Native Image otimizado", "short": "Native opt", "color": "#0c6b49"},
    "rust-axum-opt": {"label": "Rust (Axum) otimizado", "short": "Rust opt", "color": "#552a8c"},
    "java-jvm-zgc": {"label": "Java JVM otimizado com ZGC", "short": "JVM ZGC", "color": "#d9a400"},
    "java-native-g1": {"label": "Java Native otimizado com G1 (Oracle)", "short": "Native G1", "color": "#39a0a8"},
}
COMPARISONS = [
    ("A", "Go vs Java na JVM", "go-fiber", "java-jvm"),
    ("B", "Go vs Java em Native Image", "go-fiber", "java-native"),
    ("C", "Go vs Rust", "go-fiber", "rust-axum"),
    ("D", "Go: padrão vs otimizado", "go-fiber", "go-fiber-opt"),
    ("E", "JVM: padrão vs otimizado", "java-jvm", "java-jvm-opt"),
    ("F", "Native: padrão vs otimizado", "java-native", "java-native-opt"),
    ("G", "Rust: padrão vs otimizado", "rust-axum", "rust-axum-opt"),
    ("H", "Otimizados: Go vs JVM", "go-fiber-opt", "java-jvm-opt"),
    ("I", "Otimizados: Go vs Native", "go-fiber-opt", "java-native-opt"),
    ("J", "Otimizados: Go vs Rust", "go-fiber-opt", "rust-axum-opt"),
    ("K", "JVM otimizada: G1 vs ZGC", "java-jvm-opt", "java-jvm-zgc"),
    ("L", "Native otimizado: Serial (CE) vs G1 (Oracle)", "java-native-opt", "java-native-g1"),
]
# Nome do nível de carga: VUs ou req/s, conforme o modo da rodada.
LEVEL = {"name": "VUs", "axis": "VUs simultâneos"}
BG, INK, MUTED, GRID = "#fcfcfb", "#1f1f1e", "#6b6b68", "#e6e6e2"
LINE_PT = 1.5  # 2px em 96 dpi
SATURATION_PCT = 320  # 80% dos 4 vCPU de mock-api e k6
MIN_THROUGHPUT = 0.95
MIB = 2 ** 20


# ---------------- formatação pt-BR ----------------

def num(value, decimals=0):
    if value is None:
        return "-"
    text = f"{value:,.{decimals}f}"
    return text.replace(",", "\0").replace(".", ",").replace("\0", ".")


def pct(fraction, decimals=2):
    return "-" if fraction is None else num(fraction * 100, decimals) + "%"


# ---------------- leitura e agregação ----------------

def read_samples(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [{k: float(v) for k, v in row.items()} for row in csv.DictReader(f)]


def window_stats(samples, start, end):
    """Resume as amostras dentro da janela medida."""
    rows = [s for s in samples if start <= s["ts_ms"] < end]
    if not rows:
        return {"samples": 0, "mem_avg": None, "mem_peak": None, "cpu_avg": None,
                "cpu_peak": None, "cpu_seconds": None}
    return {
        "samples": len(rows),
        "mem_avg": statistics.fmean(r["mem_bytes"] for r in rows),
        "mem_peak": max(r["mem_bytes"] for r in rows),
        "cpu_avg": statistics.fmean(r["cpu_pct"] for r in rows),
        "cpu_peak": max(r["cpu_pct"] for r in rows),
        # Diferença do contador acumulado: não depende da taxa de amostragem.
        "cpu_seconds": max(0, rows[-1]["cpu_total_ns"] - rows[0]["cpu_total_ns"]) / 1e9,
    }


def load_rounds(directory):
    rounds = []
    for path in sorted(glob.glob(os.path.join(directory, "k6-*.json"))):
        m = re.search(r"k6-(.+)-(\d+)-(\d+)\.json$", path)
        if not m:
            continue
        target, vus, rep = m.group(1), int(m.group(2)), int(m.group(3))
        with open(path) as f:
            k6 = json.load(f)
        tag = f"{target}-{vus}-{rep}"
        start, end = k6["window_start_ms"], k6["window_end_ms"]
        series = {c: read_samples(os.path.join(directory, f"stats-{tag}-{c}.csv"))
                  for c in (target, "mock-api", "k6")}
        oom_path = os.path.join(directory, f"oom-{tag}.txt")
        oom = open(oom_path).read().strip() == "true" if os.path.exists(oom_path) else None
        # OOM de heap não encerra o container: só aparece no log do alvo.
        log_path = os.path.join(directory, "logs", f"{tag}.log")
        heap_oom = False
        if os.path.exists(log_path):
            with open(log_path, errors="replace") as f:
                heap_oom = "OutOfMemoryError" in f.read()
        stats = window_stats(series[target], start, end)
        cpu_per_1k = None
        ok_requests = k6["requests"] - k6["errors"]
        # Só respostas 200: CPU gasta sem entregar nada não vira eficiência aparente.
        if stats["cpu_seconds"] is not None and ok_requests > 0:
            cpu_per_1k = stats["cpu_seconds"] / ok_requests * 1000
        rounds.append({
            "target": target, "vus": vus, "rep": rep, "k6": k6, "stats": stats, "oom": oom, "heap_oom": heap_oom,
            "cpu_per_1k": cpu_per_1k, "series": series,
            "mock": window_stats(series["mock-api"], start, end),
            "k6_stats": window_stats(series["k6"], start, end),
        })
    return rounds


def median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def aggregate(rounds):
    """Mediana das repetições por alvo e nível de VUs."""
    groups = {}
    for r in rounds:
        groups.setdefault((r["target"], r["vus"]), []).append(r)
    result = {}
    for key, rs in groups.items():
        lat = lambda k: median([r["k6"]["latency_ms"].get(k) for r in rs])
        p99 = lat("p99")
        result[key] = {
            "reps": len(rs),
            "rps": median([r["k6"]["rps"] for r in rs]),
            "ideal_rps": rs[0]["k6"]["ideal_rps"],
            "errors": median([r["k6"]["errors"] for r in rs]),
            "error_rate": median([r["k6"]["error_rate"] for r in rs]),
            "p50": lat("p50"), "p90": lat("p90"), "p99": p99, "max": lat("max"),
            "overhead_p99": None if p99 is None else p99 - 5000,
            "mem_avg": median([r["stats"]["mem_avg"] for r in rs]),
            "mem_peak": median([r["stats"]["mem_peak"] for r in rs]),
            "cpu_avg": median([r["stats"]["cpu_avg"] for r in rs]),
            "cpu_peak": median([r["stats"]["cpu_peak"] for r in rs]),
            "cpu_per_1k": median([r["cpu_per_1k"] for r in rs]),
            "ooms": sum(1 for r in rs if r["oom"]),
            "heap_ooms": sum(1 for r in rs if r["heap_oom"]),
        }
    return result


def load_startup(directory):
    data = {}
    for target in TARGETS:
        path = os.path.join(directory, f"startup-{target}.json")
        if os.path.exists(path):
            with open(path) as f:
                data[target] = json.load(f)
    return data


def sanity_flags(rounds):
    flags = []
    for r in rounds:
        k6, where = r["k6"], f"{TARGETS[r['target']]['short']} {num(r['vus'])} {LEVEL['name']}, rep {r['rep']}"
        for name, st in (("mock-api", r["mock"]), ("k6", r["k6_stats"])):
            if st["cpu_avg"] is not None and st["cpu_avg"] > SATURATION_PCT:
                flags.append((where, f"{name} saturado: CPU média de {num(st['cpu_avg'], 1)}%; a rodada é inválida"))
            elif st["cpu_peak"] is not None and st["cpu_peak"] > SATURATION_PCT:
                flags.append((where, f"{name} com pico de CPU de {num(st['cpu_peak'], 1)}% (média de {num(st['cpu_avg'], 1)}%)"))
        if k6.get("dropped_iterations"):
            flags.append((where, f"{num(k6['dropped_iterations'])} iterações descartadas pelo k6"))
        if k6["errors"] > 0:
            flags.append((where, f"{num(k6['errors'])} erros ({pct(k6['error_rate'])}), "
                                 f"{num(k6.get('errors_transport', 0))} de transporte"))
        if k6["rps"] < MIN_THROUGHPUT * k6["ideal_rps"]:
            flags.append((where, f"throughput de {num(k6['rps'], 1)} req/s, abaixo de 95% do ideal ({num(k6['ideal_rps'])})"))
        if r["oom"]:
            flags.append((where, "alvo encerrado pelo kernel por falta de memória (OOM kill)"))
        if r["heap_oom"]:
            flags.append((where, "`OutOfMemoryError` no log do alvo (heap esgotado)"))
        if r["stats"]["samples"] < 0.5 * k6["duration_s"]:
            flags.append((where, f"coleta incompleta: {r['stats']['samples']} amostras em {k6['duration_s']}s"))
    return flags


# ---------------- gráficos ----------------

def style_axes(ax):
    ax.set_facecolor(BG)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.75)
    ax.set_axisbelow(True)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: num(v, 0 if abs(v) >= 10 or v == int(v) else 2)))


def separate(values, min_gap):
    """Afasta rótulos muito próximos no eixo y, preservando a ordem."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    placed = list(values)
    for a, b in zip(order, order[1:]):
        if placed[b] - placed[a] < min_gap:
            placed[b] = placed[a] + min_gap
    return placed


def direct_labels(ax, points, decimals):
    """Rótulo direto no último ponto. O texto fica na cor de tinta; a linha traz a cor."""
    if not points:
        return
    low, high = ax.get_ylim()
    placed = separate([p[1] for p in points], (high - low) * 0.075)
    for (x, y, name), ypos in zip(points, placed):
        ax.annotate(f"{name}  {num(y, decimals)}", xy=(x, y), xytext=(x, ypos), textcoords="data",
                    xycoords="data", fontsize=9, color=INK, va="center", ha="left",
                    annotation_clip=False)


def comparisons_with_data(agg):
    targets = {t for t, _ in agg}
    return [c for c in COMPARISONS if c[2] in targets and c[3] in targets]


def panel_grid(count):
    """Grade de até 2 colunas, para os gráficos continuarem legíveis com muitos comparativos."""
    cols = min(2, count)
    rows = (count + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(6.2 * cols, 4.2 * rows), facecolor=BG, squeeze=False)
    flat = [ax for row in axes for ax in row]
    for ax in flat[count:]:
        ax.set_visible(False)
    return fig, flat


def metric_chart(agg, key, title, unit, filename, charts_dir, scale=1.0, decimals=0):
    comps = comparisons_with_data(agg)
    if not comps:
        return None
    fig, panels = panel_grid(len(comps))
    for ax, (cid, cname, *targets) in zip(panels, comps):
        style_axes(ax)
        levels = sorted({v for t, v in agg if t in targets})
        xs = list(range(len(levels)))
        labels, missing = [], []
        for t in targets:
            pairs = [(i, agg[(t, v)][key]) for i, v in enumerate(levels)
                     if (t, v) in agg and agg[(t, v)][key] is not None]
            if not pairs:
                continue
            px, py = zip(*pairs)
            py = [v * scale for v in py]
            ax.plot(px, py, color=TARGETS[t]["color"], linewidth=LINE_PT, marker="o", markersize=6,
                    markeredgecolor=BG, markeredgewidth=1.5, label=TARGETS[t]["label"])
            labels.append((px[-1] + 0.08, py[-1], TARGETS[t]["short"]))
            if px[-1] < max(xs):
                missing.append(f"{TARGETS[t]['short']}: sem dado em {num(levels[-1])} VUs")
        ax.set_xticks(xs, [num(v) for v in levels])
        ax.set_xlim(-0.2, max(xs) + 0.75)
        ax.set_ylim(bottom=0)
        ax.set_ylim(0, ax.get_ylim()[1] * 1.08)
        ax.set_xlabel(LEVEL["axis"], color=MUTED, fontsize=9)
        ax.set_ylabel(unit, color=MUTED, fontsize=9)
        ax.set_title(f"Comparativo {cid}: {cname}", color=INK, fontsize=10, loc="left")
        ax.legend(frameon=False, fontsize=8.5, loc="upper center", bbox_to_anchor=(0.5, -0.17), ncol=2, labelcolor=INK)
        direct_labels(ax, labels, decimals)
        if missing:
            # Explica a linha interrompida: a falta do ponto é parte do resultado.
            ax.annotate("; ".join(missing), xy=(1, 1), xycoords="axes fraction", xytext=(0, 2),
                        textcoords="offset points", fontsize=8, color=MUTED, ha="right", va="bottom")
    fig.suptitle(title, color=INK, fontsize=12, x=0.01, ha="left", fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(os.path.join(charts_dir, filename), dpi=150, facecolor=BG)
    plt.close(fig)
    return filename


def median_round(rounds, target, vus, metric="mem_peak"):
    """Escolhe a repetição mais representativa: a de pico de memória mediano."""
    # Mantém rodadas sem amostra na janela: o alvo pode ter caído ainda no warm-up.
    rs = [r for r in rounds if r["target"] == target and r["vus"] == vus]
    if not rs:
        return None
    rs.sort(key=lambda r: r["stats"][metric] if r["stats"][metric] is not None else -1)
    return rs[len(rs) // 2]


def timeseries_chart(rounds, agg, field, title, unit, filename, charts_dir, scale=1.0, decimals=0):
    # As séries só existem na rodada atual: referências não têm painel próprio.
    current = {r["target"] for r in rounds}
    comps = [c for c in comparisons_with_data(agg) if current & set(c[2:])]
    if not comps:
        return None
    top = max(v for _, v in agg)
    fig, panels = panel_grid(len(comps))
    drew = False
    for ax, (cid, cname, *targets) in zip(panels, comps):
        style_axes(ax)
        labels = []
        warmup, last_x = None, 1
        for t in targets:
            r = median_round(rounds, t, top)
            if not r or not r["series"][t]:
                continue
            warmup = r["k6"]["warmup_s"]
            t0 = r["k6"]["window_start_ms"] - warmup * 1000
            end = r["k6"]["window_end_ms"]
            rows = [s for s in r["series"][t] if t0 <= s["ts_ms"] <= end]
            if not rows:
                continue
            xs = [(s["ts_ms"] - t0) / 1000 for s in rows]
            ys = [s[field] * scale for s in rows]
            ax.plot(xs, ys, color=TARGETS[t]["color"], linewidth=LINE_PT, label=TARGETS[t]["label"])
            labels.append((xs[-1] + (xs[-1] * 0.012), ys[-1], TARGETS[t]["short"]))
            last_x = max(last_x, xs[-1])
            drew = True
        ax.set_ylim(bottom=0)
        ax.set_ylim(0, ax.get_ylim()[1] * 1.12)
        ax.set_xlim(0, last_x * 1.2)
        if warmup is not None:
            ax.axvline(warmup, color=MUTED, linewidth=1, linestyle=(0, (4, 3)))
            ax.annotate("fim do warm-up", xy=(warmup, ax.get_ylim()[1] * 0.985), xytext=(4, 0),
                        textcoords="offset points", fontsize=8, color=MUTED, va="top")
        ax.set_xlabel(f"Segundos desde o início da carga, {num(top)} {LEVEL['name']}", color=MUTED, fontsize=9)
        ax.set_ylabel(unit, color=MUTED, fontsize=9)
        ax.set_title(f"Comparativo {cid}: {cname}", color=INK, fontsize=10, loc="left")
        ax.legend(frameon=False, fontsize=8.5, loc="upper center", bbox_to_anchor=(0.5, -0.17), ncol=2, labelcolor=INK)
        direct_labels(ax, labels, decimals)
    fig.suptitle(title, color=INK, fontsize=12, x=0.01, ha="left", fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    if drew:
        fig.savefig(os.path.join(charts_dir, filename), dpi=150, facecolor=BG)
    plt.close(fig)
    return filename if drew else None


def startup_chart(startup, charts_dir):
    if not startup:
        return None
    order = [t for t in TARGETS if t in startup][::-1]
    panels = [("time_to_ready_ms", "Tempo até ficar pronto (ms)", 1.0, 0),
              ("idle_mem_bytes", "Memória parada (MiB)", 1 / MIB, 1)]
    fig, axes = plt.subplots(1, 2, figsize=(11, 1.6 + 0.65 * len(order)), facecolor=BG)
    for ax, (key, title, scale, decimals) in zip(axes, panels):
        style_axes(ax)
        ax.grid(axis="y", visible=False)
        ax.grid(axis="x", color=GRID, linewidth=0.75)
        ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: num(v, 0 if v == int(v) else 1)))
        values = [startup[t][key]["median"] * scale for t in order]
        positions = list(range(len(order)))
        bars = ax.barh(positions, values, height=0.55, color=[TARGETS[t]["color"] for t in order])
        ax.yaxis.set_major_formatter(matplotlib.ticker.ScalarFormatter())
        ax.set_yticks(positions, [TARGETS[t]["short"] for t in order])
        for bar, value in zip(bars, values):
            ax.annotate(num(value, decimals), xy=(value, bar.get_y() + bar.get_height() / 2), xytext=(5, 0),
                        textcoords="offset points", fontsize=9, color=INK, va="center")
        ax.set_xlim(0, max(values) * 1.16 if max(values) else 1)
        ax.set_title(f"{title}, mediana", color=INK, fontsize=10, loc="left")
    handles = [plt.Rectangle((0, 0), 1, 1, color=TARGETS[t]["color"]) for t in order[::-1]]
    fig.legend(handles, [TARGETS[t]["label"] for t in order[::-1]], frameon=False, fontsize=8.5,
               loc="lower center", ncol=min(4, len(order)), labelcolor=INK)
    fig.tight_layout(rect=(0, 0.16 if len(order) > 4 else 0.1, 1, 1))
    fig.savefig(os.path.join(charts_dir, "startup.png"), dpi=150, facecolor=BG)
    plt.close(fig)
    return "startup.png"


def make_charts(rounds, agg, startup, charts_dir):
    if plt is None:
        return {}
    global matplotlib
    import matplotlib.ticker  # noqa: F401
    os.makedirs(charts_dir, exist_ok=True)
    return {
        "startup": startup_chart(startup, charts_dir),
        "overhead": metric_chart(agg, "overhead_p99", "Overhead de latência no p99 (p99 menos os 5.000 ms da API externa)",
                                 "ms", "overhead_p99.png", charts_dir, decimals=1),
        "mem_peak": metric_chart(agg, "mem_peak", "Memória de pico (limite de 1.024 MiB)", "MiB",
                                 "memoria_pico.png", charts_dir, scale=1 / MIB),
        "cpu_avg": metric_chart(agg, "cpu_avg", "CPU média (100% = 1 core, máximo de 200%)", "% de 1 core",
                                "cpu_media.png", charts_dir, decimals=1),
        "cpu_per_1k": metric_chart(agg, "cpu_per_1k", "CPU-segundos por 1.000 requisições", "CPU-s",
                                   "cpu_por_1000.png", charts_dir, decimals=2),
        "ts_mem": timeseries_chart(rounds, agg, "mem_bytes", "Memória ao longo do teste, no maior nível", "MiB",
                                   "serie_memoria.png", charts_dir, scale=1 / MIB),
        "ts_cpu": timeseries_chart(rounds, agg, "cpu_pct", "CPU ao longo do teste, no maior nível", "% de 1 core",
                                   "serie_cpu.png", charts_dir),
    }


# ---------------- montagem do relatório ----------------

def latency_rows(agg, targets):
    rows = []
    for vus in sorted({v for t, v in agg if t in targets}):
        for t in targets:
            a = agg.get((t, vus))
            if a:
                rows.append([num(vus), TARGETS[t]["label"], num(a["rps"], 1), num(a["ideal_rps"]),
                             f"{num(a['errors'])} ({pct(a['error_rate'])})",
                             num(a["p50"], 1), num(a["p90"], 1), num(a["p99"], 1), num(a["max"], 1),
                             num(a["overhead_p99"], 1)])
    return rows


def resource_rows(agg, startup, targets):
    rows = []
    for vus in sorted({v for t, v in agg if t in targets}):
        for t in targets:
            a = agg.get((t, vus))
            if a:
                idle = startup.get(t, {}).get("idle_mem_bytes", {}) or {}
                rows.append([num(vus), TARGETS[t]["label"],
                             num(idle["median"] / MIB, 1) if idle else "-",
                             num(a["mem_avg"] / MIB, 1) if a["mem_avg"] else "-",
                             num(a["mem_peak"] / MIB, 1) if a["mem_peak"] else "-",
                             num(a["cpu_avg"], 1), num(a["cpu_peak"], 1), num(a["cpu_per_1k"], 3),
                             num(a["ooms"]), num(a["heap_ooms"])])
    return rows


LAT_HEAD = ["Nível", "Alvo", "req/s real", "req/s ideal", "Erros", "p50 (ms)", "p90 (ms)", "p99 (ms)", "max (ms)", "Overhead p99 (ms)"]
RES_HEAD = ["Nível", "Alvo", "Memória parada (MiB)", "Memória média (MiB)", "Memória pico (MiB)", "CPU média (%)", "CPU pico (%)", "CPU-s por 1.000 req", "OOM kill", "OOM de heap"]


def build_blocks(directory, rounds, agg, startup, charts):
    b = [("h1", "Benchmark de I/O: Java com virtual threads, Go com Fiber e Rust com Axum")]
    if LEVEL["name"] != "VUs":
        b.append(("p", "**Carga por taxa:** o nível é a taxa em req/s, constante mesmo se o alvo ficar lento (k6 `constant-arrival-rate`)."))
    else:
        b.append(("p", "**Carga por VUs:** o nível é o número de usuários virtuais simultâneos."))
    b.append(("p", "Cada requisição chama uma API externa com 5s de latência fixa e devolve a resposta, sem trabalho de CPU "
                   "no handler. Os valores são a **mediana das repetições**, restritos à janela medida (sem warm-up). "
                   "CPU em % de 1 core, com máximo de 200%. CPU-s por 1.000 requisições conta só respostas 200. "
                   "O traço indica ausência de dado: nenhuma resposta 200 ou alvo já encerrado na janela. "
                   "O Native Image usa JDK 25, e a variante JVM usa JDK 27, quando presentes nesta rodada."))

    env = environment_rows(directory)
    if env:
        b.append(("h2", "Ambiente"))
        b.append(("table", ["Item", "Valor"], env))

    analysis = os.path.join(directory, "analise.md")
    if os.path.exists(analysis):
        b.append(("h2", "Análise"))
        with open(analysis, encoding="utf-8") as f:
            b.extend(parse_analysis(f.read()))

    if startup:
        b.append(("h2", "Startup"))
        rows = []
        for t in TARGETS:
            s = startup.get(t)
            if s:
                sr = s.get("self_reported_ms") or {}
                rows.append([TARGETS[t]["label"], num(s["time_to_ready_ms"]["median"]), num(s["time_to_ready_ms"]["p90"]),
                             num(sr.get("median")), num(s["first_io_ms"]["median"], 1),
                             num(s["idle_mem_bytes"]["median"] / MIB, 1), num(s["image_size_bytes"] / 1e6, 1),
                             num(len(s["runs"]))])
        b.append(("table", ["Alvo", "Pronto, mediana (ms)", "Pronto, p90 (ms)", "Autodeclarado (ms)", "1ª requisição (ms além dos 5s)",
                            "Memória parada (MiB)", "Imagem (MB)", "Execuções"], rows))
        b.append(("p", "O tempo até ficar pronto é medido de fora, do start do container até o primeiro `/health` com 200, e "
                       "inclui o custo do Docker. Os tempos autodeclarados do Go e do Rust partem do código do programa e não "
                       "incluem o início do runtime, por isso não são comparáveis ao do Java."))
        if charts.get("startup"):
            b.append(("img", charts["startup"], "Barras de startup: tempo até ficar pronto e memória parada por alvo"))

    for cid, cname, *targets in comparisons_with_data(agg):
        b.append(("h2", f"Comparativo {cid}: {cname}"))
        b.append(("h3", "Latência e throughput"))
        b.append(("table", LAT_HEAD, latency_rows(agg, targets)))
        b.append(("h3", "Memória e CPU"))
        b.append(("table", RES_HEAD, resource_rows(agg, startup, targets)))

    if agg:
        b.append(("h2", "Gráficos"))
        titles = [("overhead", "Overhead p99 por VUs"), ("mem_peak", "Memória de pico por VUs"), ("cpu_avg", "CPU média por VUs"),
                  ("cpu_per_1k", "CPU-s por 1.000 requisições por VUs"), ("ts_mem", "Série temporal de memória"), ("ts_cpu", "Série temporal de CPU")]
        for key, alt in titles:
            if charts.get(key):
                b.append(("img", charts[key], alt))

    if len(sys.argv) > 2:
        b.append(("p", "Os alvos ausentes nesta rodada vêm das rodadas de referência: "
                       + ", ".join(f"`{os.path.basename(p.rstrip('/'))}`" for p in sys.argv[2:])
                       + ". As seções abaixo cobrem só a rodada atual."))
    b.append(("h2", "Sanidade do ambiente"))
    flags = sanity_flags(rounds)
    failures = os.path.join(directory, "failures.log")
    if os.path.exists(failures):
        with open(failures) as f:
            flags += [("Execução", line.strip()) for line in f if line.strip()]
    if flags:
        b.append(("p", f"{num(len(flags))} ocorrências:"))
        b.append(("table", ["Rodada", "Ocorrência"], [list(f) for f in flags]))
    else:
        b.append(("p", "Sem ocorrências: nenhuma saturação de mock-api ou k6, nenhum erro, nenhum OOM e throughput sempre acima de 95% do ideal."))
    rows = [[num(r["vus"]), TARGETS[r["target"]]["short"], num(r["rep"]),
             num(r["mock"]["cpu_avg"], 1), num(r["mock"]["cpu_peak"], 1),
             num(r["k6_stats"]["cpu_avg"], 1), num(r["k6_stats"]["cpu_peak"], 1),
             num(r["k6_stats"]["mem_peak"] / MIB) if r["k6_stats"]["mem_peak"] else "-"]
            for r in sorted(rounds, key=lambda r: (r["vus"], r["target"], r["rep"]))]
    if rows:
        b.append(("h3", "Consumo de mock-api e k6 por rodada"))
        b.append(("table", ["Nível", "Alvo", "Rep", "mock-api CPU média (%)", "mock-api CPU pico (%)", "k6 CPU média (%)", "k6 CPU pico (%)", "k6 memória pico (MiB)"], rows))

    rows = [[num(r["vus"]), TARGETS[r["target"]]["short"], num(r["rep"]), num(r["k6"]["requests"]), num(r["k6"]["rps"], 1),
             num(r["k6"]["errors"]), num(r["k6"]["latency_ms"]["p50"], 1), num(r["k6"]["latency_ms"]["p99"], 1), num(r["k6"]["latency_ms"]["max"], 1),
             num(r["stats"]["mem_avg"] / MIB, 1) if r["stats"]["mem_avg"] else "-", num(r["stats"]["mem_peak"] / MIB, 1) if r["stats"]["mem_peak"] else "-",
             num(r["stats"]["cpu_avg"], 1), num(r["cpu_per_1k"], 3),
             num(r["k6"]["http_req_blocked_ms"]["p99"], 1), num(r["k6"]["http_req_blocked_ms"]["max"], 1), "kill" if r["oom"] else ("heap" if r["heap_oom"] else "não")]
            for r in sorted(rounds, key=lambda r: (r["vus"], r["target"], r["rep"]))]
    if rows:
        b.append(("h2", "Todas as rodadas"))
        b.append(("table", ["Nível", "Alvo", "Rep", "Requisições", "req/s", "Erros", "p50 (ms)", "p99 (ms)", "max (ms)", "Mem. média (MiB)", "Mem. pico (MiB)",
                            "CPU média (%)", "CPU-s/1.000", "Blocked p99 (ms)", "Blocked max (ms)", "OOM"], rows))
    return b


def environment_rows(directory):
    rows = []
    path = os.path.join(directory, "docker-info.json")
    if os.path.exists(path):
        with open(path) as f:
            d = json.load(f)
        info, ver = d["info"], d["version"]
        rows += [["CPU", f"{info.get('NCPU')} vCPU, {info.get('Architecture')}"],
                 ["Memória", f"{num(info.get('MemTotal', 0) / 2**30, 1)} GiB"],
                 ["Sistema operacional", f"{info.get('OperatingSystem')}, kernel {info.get('KernelVersion')}"],
                 ["Docker", str(ver.get("Version"))]]
    path = os.path.join(directory, "config.json")
    if os.path.exists(path):
        with open(path) as f:
            c = json.load(f)
        rows += [["Níveis de VUs", c.get("LEVELS", "")], ["Repetições", c.get("REPS", "")],
                 ["Warm-up e janela medida", f"{c.get('WARMUP')}s e {c.get('DURATION')}s"],
                 ["Execuções de startup", c.get("STARTUP_RUNS", "")]]
    return rows


def parse_analysis(text):
    blocks, bullets = [], []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("- "):
            bullets.append(line[2:])
            continue
        if bullets:
            blocks.append(("ul", bullets))
            bullets = []
        if line.startswith("### "):
            blocks.append(("h3", line[4:]))
        elif line:
            blocks.append(("p", line))
    if bullets:
        blocks.append(("ul", bullets))
    return blocks


# ---------------- saída em Markdown e HTML ----------------

def to_markdown(blocks):
    out = []
    for block in blocks:
        kind = block[0]
        if kind in ("h1", "h2", "h3"):
            out.append("#" * int(kind[1]) + " " + block[1])
        elif kind == "p":
            out.append(block[1])
        elif kind == "ul":
            out.append("\n".join(f"- {i}" for i in block[1]))
        elif kind == "table":
            head, rows = block[1], block[2]
            lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
            lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
            out.append("\n".join(lines))
        elif kind == "img":
            out.append(f"![{block[2]}](charts/{block[1]})")
    return "\n\n".join(out) + "\n"


def inline_html(text):
    text = html.escape(text, quote=False)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    return re.sub(r"`(.+?)`", r"<code>\1</code>", text)


CSS = """
:root{color-scheme:light}
body{margin:0;background:#fcfcfb;color:#1f1f1e;font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1180px;margin:0 auto;padding:40px 24px 80px}
h1{font-size:30px;line-height:1.2;margin:0 0 16px}
h2{font-size:22px;margin:48px 0 12px;padding-top:16px;border-top:1px solid #e6e6e2}
h3{font-size:16px;margin:28px 0 8px}
p,ul{max-width:80ch}
code{background:#f1f1ed;padding:1px 4px;border-radius:3px;font-size:.9em}
.table{overflow-x:auto;margin:12px 0 20px}
table{border-collapse:collapse;font-size:13.5px;width:100%;font-variant-numeric:tabular-nums}
th{font-weight:600;color:#6b6b68;text-align:right;vertical-align:bottom;padding:6px 10px;border-bottom:1px solid #c9c9c4}
td{text-align:right;padding:5px 10px;border-bottom:1px solid #eeeeea;white-space:nowrap}
th.text,td.text{text-align:left}
td.wrap{white-space:normal}
img{max-width:100%;height:auto;display:block;margin:16px 0}
"""


def is_text_column(rows, index):
    return any(not re.fullmatch(r"[-\d.,%() ]*", str(r[index])) for r in rows)


def to_html(blocks, charts_dir):
    title = next(b[1] for b in blocks if b[0] == "h1")
    out = [f'<!doctype html>\n<html lang="pt-BR"><head><meta charset="utf-8">'
           f'<meta name="viewport" content="width=device-width,initial-scale=1">'
           f"<title>{html.escape(title)}</title><style>{CSS}</style></head><body><main>"]
    for block in blocks:
        kind = block[0]
        if kind in ("h1", "h2", "h3"):
            out.append(f"<{kind}>{inline_html(block[1])}</{kind}>")
        elif kind == "p":
            out.append(f"<p>{inline_html(block[1])}</p>")
        elif kind == "ul":
            out.append("<ul>" + "".join(f"<li>{inline_html(i)}</li>" for i in block[1]) + "</ul>")
        elif kind == "table":
            head, rows = block[1], block[2]
            text = [is_text_column(rows, i) for i in range(len(head))]
            cls = lambda i: ' class="text"' if text[i] else ""
            out.append('<div class="table"><table><thead><tr>' +
                       "".join(f"<th{cls(i)}>{html.escape(h)}</th>" for i, h in enumerate(head)) + "</tr></thead><tbody>")
            for r in rows:
                out.append("<tr>" + "".join(f"<td{cls(i)}>{html.escape(str(c))}</td>" for i, c in enumerate(r)) + "</tr>")
            out.append("</tbody></table></div>")
        elif kind == "img":
            # A imagem fica embutida para o HTML funcionar como arquivo único.
            with open(os.path.join(charts_dir, block[1]), "rb") as f:
                data = base64.b64encode(f.read()).decode()
            out.append(f'<img src="data:image/png;base64,{data}" alt="{html.escape(block[2])}">')
    out.append("</main></body></html>\n")
    return "\n".join(out)


def main():
    directory = sys.argv[1]
    rounds = load_rounds(directory)
    if any(r["k6"].get("mode") == "rate" for r in rounds):
        LEVEL.update(name="req/s", axis="Taxa de chegada (req/s)")
    agg = aggregate(rounds)
    startup = load_startup(directory)
    # Sem sobrescrever a rodada atual: referências só preenchem alvos ausentes.
    for reference in sys.argv[2:]:
        for key, value in aggregate(load_rounds(reference)).items():
            if key[0] not in {t for t, _ in aggregate(rounds)}:
                agg.setdefault(key, value)
        for target, value in load_startup(reference).items():
            startup.setdefault(target, value)
    charts_dir = os.path.join(directory, "charts")
    charts = make_charts(rounds, agg, startup, charts_dir)
    blocks = build_blocks(directory, rounds, agg, startup, charts)
    with open(os.path.join(directory, "report.md"), "w", encoding="utf-8") as f:
        f.write(to_markdown(blocks))
    with open(os.path.join(directory, "report.html"), "w", encoding="utf-8") as f:
        f.write(to_html(blocks, charts_dir))
    print(f"relatório: {directory}/report.md e report.html" + ("" if plt else " (sem gráficos: matplotlib ausente)"))


if __name__ == "__main__":
    main()
