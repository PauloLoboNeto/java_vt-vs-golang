#!/usr/bin/env python3
"""Grava as amostras de um container em CSV: collect_stats.py <container> <saida.csv>."""
import os
import signal
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dockerapi


def main():
    container, path = sys.argv[1], sys.argv[2]
    # SIGTERM encerra pelo fluxo normal, fechando o arquivo.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    # buffering=1: flush por linha, para não perder dados se o processo morrer.
    with open(path, "w", buffering=1) as out:
        out.write("ts_ms,cpu_total_ns,cpu_pct,mem_bytes,mem_limit_bytes\n")
        seen = False
        while True:
            # O k6 sobe depois do coletor: espera o container existir.
            if not dockerapi.exists(container):
                if seen:
                    return
                time.sleep(0.2)
                continue
            seen = True
            try:
                for s in dockerapi.stats_stream(container):
                    # Container sem amostra ainda traz read em 0001-01-01.
                    if s["read"].startswith("0001-") or "usage" not in s.get("memory_stats", {}):
                        continue
                    out.write("%d,%d,%.3f,%d,%d\n" % (
                        dockerapi.read_to_ms(s["read"]),
                        s["cpu_stats"]["cpu_usage"]["total_usage"],
                        dockerapi.cpu_pct(s),
                        dockerapi.mem_bytes(s),
                        s["memory_stats"].get("limit", 0),
                    ))
            except (dockerapi.DockerError, OSError, ValueError, KeyError):
                pass
            # O stream fecha quando o container para. Só continua se ainda estiver subindo.
            try:
                state = dockerapi.inspect(container)["State"]
            except dockerapi.DockerError:
                return
            if state["Status"] in ("exited", "dead"):
                return
            time.sleep(0.2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
