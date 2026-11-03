#!/usr/bin/env python3
"""Mede o startup de um alvo: startup.py <alvo> <runs> <saida.json>."""
import http.client
import json
import os
import re
import statistics
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dockerapi

TARGETS = {
    "go-fiber": ("go", 8081),
    "java-jvm": ("jvm", 8082),
    "java-native": ("native", 8083),
    "rust-axum": ("rust", 8084),
    "go-fiber-opt": ("go-opt", 8085),
    "java-jvm-opt": ("jvm-opt", 8086),
    "java-native-opt": ("native-opt", 8087),
    "rust-axum-opt": ("rust-opt", 8088),
    "java-native-g1": ("native-g1", 8089),
    "java-jvm-zgc": ("jvm-zgc", 8090),
}
READY_TIMEOUT_S = 60


def compose(profile, *args):
    subprocess.run(["docker", "compose", "--profile", profile, *args],
                   check=True, capture_output=True)


def get(port, path, timeout):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        resp.read()
        return resp.status
    finally:
        conn.close()


def delay_ms():
    """Latência da mock-api, descontada da primeira requisição."""
    m = re.fullmatch(r"(\d+)(ms|s)", os.environ.get("MOCK_DELAY", "5s"))
    return int(m.group(1)) * (1 if m.group(2) == "ms" else 1000)


def self_reported_ms(logs):
    m = re.search(r"process running for ([\d.]+)", logs) or re.search(r"started in ([\d.]+) seconds", logs)
    return float(m.group(1)) * 1000 if m else None


def one_run(target, profile, port):
    container = f"bench-{target}"
    compose(profile, "rm", "-sf", target)
    compose(profile, "create", "--no-recreate", target)

    t0 = time.perf_counter()
    dockerapi.start(container)
    while True:
        try:
            if get(port, "/health", 0.5) == 200:
                break
        except OSError:
            pass
        except http.client.HTTPException:
            pass
        elapsed = time.perf_counter() - t0
        if elapsed > READY_TIMEOUT_S:
            raise SystemExit(f"{target} não ficou pronto em {READY_TIMEOUT_S}s")
        time.sleep(0.005)
    ready_ms = (time.perf_counter() - t0) * 1000

    t1 = time.perf_counter()
    status = get(port, "/api/io", 30)
    first_io_ms = (time.perf_counter() - t1) * 1000 - delay_ms()
    if status != 200:
        raise SystemExit(f"{target}: primeira chamada a /api/io retornou {status}")

    # Deixa a memória assentar depois da primeira requisição.
    time.sleep(5)
    idle = dockerapi.mem_bytes(dockerapi.stats_once(container))
    reported = self_reported_ms(dockerapi.logs(container))
    compose(profile, "rm", "-sf", target)
    return {
        "time_to_ready_ms": ready_ms,
        "first_io_ms": first_io_ms,
        "idle_mem_bytes": idle,
        "self_reported_ms": reported,
    }


def percentile(values, p):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(p / 100 * (len(ordered) - 1)))]


def summarize(values):
    values = [v for v in values if v is not None]
    if not values:
        return None
    return {"median": statistics.median(values), "p90": percentile(values, 90),
            "min": min(values), "max": max(values)}


def main():
    target, runs, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    profile, port = TARGETS[target]
    subprocess.run(["docker", "compose", "up", "-d", "mock-api"], check=True, capture_output=True)

    results = []
    for i in range(runs):
        r = one_run(target, profile, port)
        results.append(r)
        print(f"  {target} {i + 1}/{runs}: pronto em {r['time_to_ready_ms']:.0f} ms, "
              f"1a req +{r['first_io_ms']:.1f} ms, memória {r['idle_mem_bytes'] / 2**20:.1f} MiB", flush=True)

    data = {
        "target": target,
        "runs": results,
        "image_size_bytes": dockerapi.image_size(f"bench/{target}"),
    }
    for key in ("time_to_ready_ms", "first_io_ms", "idle_mem_bytes", "self_reported_ms"):
        data[key] = summarize([r[key] for r in results])
    with open(out, "w") as f:
        json.dump(data, f, indent=2)


if __name__ == "__main__":
    main()
