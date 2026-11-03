#!/usr/bin/env python3
"""Gera a imagem geral de startup, CPU e memória: overview.py <saida.png> <rodadas...>.

A primeira rodada com dados de um alvo tem prioridade, como nas referências de generate.py.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generate as g
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

SURFACE, INK, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e6e2"
BLUE, AQUA, ORANGE, VIOLET = "#2a78d6", "#1baf7a", "#eb6834", "#6250d6"
LIMIT_MIB = 1024
MIN_THROUGHPUT = 0.95

# Alvo, rótulo, cor por plataforma e se é a configuração padrão (barra hachurada).
# A ordem separa azul e violeta, que o validador de paleta reprova quando vizinhos.
ROWS = [
    ("go-fiber", "Go · padrão", BLUE, True),
    ("go-fiber-opt", "Go · otimizado", BLUE, False),
    ("java-jvm", "JVM · padrão (Tomcat, G1)", ORANGE, True),
    ("java-jvm-opt", "JVM · otimizada (Jetty, G1)", ORANGE, False),
    ("java-jvm-zgc", "JVM · otimizada (Jetty, ZGC)", ORANGE, False),
    ("java-native", "Native · padrão (Tomcat, Serial)", AQUA, True),
    ("java-native-opt", "Native · otimizado (Jetty, Serial)", AQUA, False),
    ("java-native-g1", "Native · otimizado (Jetty, G1 Oracle)", AQUA, False),
    ("rust-axum", "Rust · padrão", VIOLET, True),
    ("rust-axum-opt", "Rust · otimizado", VIOLET, False),
]


def load(directories):
    agg, startup = {}, {}
    for directory in directories:
        loaded = g.aggregate(g.load_rounds(directory))
        present = {t for t, _ in agg}
        for key, value in loaded.items():
            if key[0] not in present:
                agg[key] = value
        for target, value in g.load_startup(directory).items():
            startup.setdefault(target, value)
    return agg, startup


def cell(agg, target, vus, key, scale):
    """Devolve valor e situação: só há valor quando o alvo entregou respostas 200."""
    a = agg.get((target, vus))
    if not a or not a["rps"] or a[key] is None:
        return None, False
    return a[key] * scale, a["rps"] < MIN_THROUGHPUT * a["ideal_rps"]


def panel(ax, title, unit, values, decimals, limit=None):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "bottom"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color("#c9c9c4")
    ax.tick_params(left=False, bottom=False, labelbottom=False)
    top = max([v for v, _ in values if v is not None] + ([limit] if limit else []))
    ax.set_xlim(0, top * 1.42)
    ax.set_ylim(len(ROWS) - 0.4, -0.6)
    for y, ((_, _, color, standard), (value, low)) in enumerate(zip(ROWS, values)):
        if value is None:
            ax.text(top * 0.02, y, "falhou: 100% de erros", color=MUTED, fontsize=8.5, va="center", style="italic")
            continue
        ax.barh(y, value, height=0.62, color=SURFACE if standard else color, edgecolor=color,
                hatch="////" if standard else None, linewidth=1)
        text = g.num(value, decimals) + (" *" if low else "")
        # O fundo evita que a linha do limite atravesse o número.
        ax.text(value + top * 0.02, y, text, color=INK, fontsize=9, va="center", zorder=5,
                bbox={"facecolor": SURFACE, "edgecolor": "none", "pad": 1.2})
    for boundary in (1.5, 4.5, 7.5):
        ax.axhline(boundary, color=GRID, linewidth=0.8)
    if limit:
        ax.axvline(limit, color=MUTED, linewidth=1, linestyle=(0, (4, 3)))
        ax.text(limit, -0.82, f"limite: {g.num(limit)}", color=MUTED, fontsize=8, ha="center", va="bottom")
    ax.set_title(f"{title}\n", loc="left", color=INK, fontsize=10.5, fontweight="bold", pad=10)
    ax.text(0, 1.015, unit, transform=ax.transAxes, color=MUTED, fontsize=8.5, va="bottom")


def main():
    out, directories = sys.argv[1], sys.argv[2:]
    agg, startup = load(directories)
    plt.rcParams.update({"hatch.linewidth": 0.8})
    fig, axes = plt.subplots(1, 5, figsize=(17, 7.2), facecolor=SURFACE, sharey=True,
                             gridspec_kw={"width_ratios": [1.15, 1, 1, 1.15, 1.15]})
    targets = [r[0] for r in ROWS]
    panel(axes[0], "Startup", "tempo até ficar pronto (ms)",
          [(startup[t]["time_to_ready_ms"]["median"], False) for t in targets], 0)
    panel(axes[1], "CPU com 5.000 VUs", "CPU-s por 1.000 req",
          [cell(agg, t, 5000, "cpu_per_1k", 1) for t in targets], 3)
    panel(axes[2], "CPU com 10.000 VUs", "CPU-s por 1.000 req",
          [cell(agg, t, 10000, "cpu_per_1k", 1) for t in targets], 3)
    panel(axes[3], "Memória com 5.000 VUs", "pico (MiB)",
          [cell(agg, t, 5000, "mem_peak", 1 / g.MIB) for t in targets], 0, LIMIT_MIB)
    panel(axes[4], "Memória com 10.000 VUs", "pico (MiB)",
          [cell(agg, t, 10000, "mem_peak", 1 / g.MIB) for t in targets], 0, LIMIT_MIB)
    axes[0].set_yticks(range(len(ROWS)), [r[1] for r in ROWS], color=INK, fontsize=9.5)

    fig.text(0.012, 0.965, "Otimizado, o Java passa a atender 10.000 VUs em 1 GB, mas Go e Rust seguem bem mais baratos",
             color=INK, fontsize=15, fontweight="bold", va="top")
    fig.text(0.012, 0.915, "Benchmark de I/O: cada requisição espera 5 s por uma API externa. Cada alvo tem 2 vCPU e 1 GB. "
                           "Valores são a mediana de 3 repetições (startup: 10 execuções). Menor é melhor.",
             color=MUTED, fontsize=10, va="top")
    handles = [Patch(facecolor=c, edgecolor=c, label=n) for n, c in
               (("Go", BLUE), ("JVM", ORANGE), ("Native Image", AQUA), ("Rust", VIOLET))]
    handles += [Patch(facecolor=SURFACE, edgecolor=MUTED, hatch="////", label="Padrão"),
                Patch(facecolor=MUTED, edgecolor=MUTED, label="Otimizado")]
    fig.legend(handles=handles, loc="lower left", bbox_to_anchor=(0.008, 0.045), ncol=6, frameon=False,
               fontsize=9.5, labelcolor=INK)
    fig.text(0.012, 0.022, "* Abaixo de 95% do throughput ideal. Os alvos padrão vêm de rodadas anteriores na mesma máquina. "
                           "Os ajustes foram feitos para este cenário, com respostas de 35 bytes, e não valem automaticamente para produção.",
             color=MUTED, fontsize=8.5, va="bottom")
    fig.subplots_adjust(left=0.175, right=0.99, top=0.77, bottom=0.14, wspace=0.08)
    fig.savefig(out, dpi=150, facecolor=SURFACE)
    print(out)


if __name__ == "__main__":
    main()
