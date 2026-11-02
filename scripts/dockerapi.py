"""Cliente mínimo da Docker Engine API via unix socket (só biblioteca padrão).

Usa a API porque a CLI adiciona centenas de ms por chamada, o que distorceria o
startup, e porque o `docker stats` não expõe o contador acumulado de CPU.
"""
import calendar
import http.client
import json
import os
import socket
import subprocess
import time
import urllib.parse


class DockerError(Exception):
    def __init__(self, status, message):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status


def socket_path():
    """Obtém o socket de DOCKER_HOST ou do contexto atual do Docker."""
    host = os.environ.get("DOCKER_HOST")
    if not host:
        host = subprocess.run(
            ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
    if not host.startswith("unix://"):
        raise SystemExit(f"o socket do Docker precisa ser unix://, encontrado: {host}")
    return host[len("unix://"):]


class _UnixConnection(http.client.HTTPConnection):
    def __init__(self, path, timeout):
        super().__init__("localhost", timeout=timeout)
        self._path = path

    def connect(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self._path)
        self.sock = sock


_SOCKET = None


def _open(method, path, timeout):
    global _SOCKET
    if _SOCKET is None:
        _SOCKET = socket_path()
    conn = _UnixConnection(_SOCKET, timeout)
    conn.request(method, path)
    resp = conn.getresponse()
    if resp.status >= 400:
        body = resp.read().decode("utf-8", "replace")
        conn.close()
        raise DockerError(resp.status, body)
    return conn, resp


def _request(method, path, timeout=60):
    conn, resp = _open(method, path, timeout)
    try:
        return resp.read()
    finally:
        conn.close()


def start(name):
    _request("POST", f"/containers/{urllib.parse.quote(name)}/start")


def inspect(name):
    return json.loads(_request("GET", f"/containers/{urllib.parse.quote(name)}/json"))


def exists(name):
    try:
        inspect(name)
        return True
    except DockerError as e:
        if e.status == 404:
            return False
        raise


def stats_once(name):
    """Amostra única, sem a espera de 1s para calcular precpu."""
    path = f"/containers/{urllib.parse.quote(name)}/stats?stream=false&one-shot=true"
    return json.loads(_request("GET", path))


def stats_stream(name):
    """Gera uma amostra por segundo até o container parar ou sumir."""
    path = f"/containers/{urllib.parse.quote(name)}/stats?stream=true"
    conn, resp = _open("GET", path, None)
    try:
        for line in resp:
            line = line.strip()
            if line:
                yield json.loads(line)
    finally:
        conn.close()


def logs(name):
    """Lê stdout e stderr, separando o stream multiplexado (header de 8 bytes)."""
    raw = _request("GET", f"/containers/{urllib.parse.quote(name)}/logs?stdout=1&stderr=1")
    out = bytearray()
    i = 0
    while i + 8 <= len(raw):
        size = int.from_bytes(raw[i + 4:i + 8], "big")
        out += raw[i + 8:i + 8 + size]
        i += 8 + size
    return out.decode("utf-8", "replace")


def image_size(name):
    """Tamanho da imagem em bytes, como reportado pelo daemon."""
    return json.loads(_request("GET", f"/images/{urllib.parse.quote(name, safe='')}/json"))["Size"]


def info():
    return json.loads(_request("GET", "/info"))


def version():
    return json.loads(_request("GET", "/version"))


def read_to_ms(read):
    """Converte `read` para ms. Tem nanossegundos, que fromisoformat não aceita.

    Vem do mesmo relógio do host que o Date.now() do k6, o que permite recortar
    as amostras pela janela medida.
    """
    base, _, frac = read.rstrip("Z").partition(".")
    seconds = calendar.timegm(time.strptime(base, "%Y-%m-%dT%H:%M:%S"))
    return seconds * 1000 + int((frac + "000")[:3])


def mem_bytes(sample):
    """Memória de trabalho: usage sem o cache de arquivos inativo."""
    mem = sample["memory_stats"]
    return mem["usage"] - mem.get("stats", {}).get("inactive_file", 0)


def cpu_pct(sample):
    """CPU em % de 1 core: com limite de 2 vCPU, o máximo é 200%."""
    cpu, pre = sample["cpu_stats"], sample.get("precpu_stats", {})
    cpu_delta = cpu["cpu_usage"]["total_usage"] - pre.get("cpu_usage", {}).get("total_usage", 0)
    system_delta = cpu.get("system_cpu_usage", 0) - pre.get("system_cpu_usage", 0)
    if not pre.get("system_cpu_usage") or system_delta <= 0 or cpu_delta < 0:
        return 0.0
    return cpu_delta / system_delta * cpu.get("online_cpus", 1) * 100
