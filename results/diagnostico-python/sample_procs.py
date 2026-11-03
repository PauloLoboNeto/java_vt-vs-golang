"""Roda dentro do alvo: CPU em 10 s, memória e descritores por processo."""
import glob, os, time
def snap():
    o = {}
    for p in glob.glob("/proc/[0-9]*"):
        try:
            pid = int(p.split("/")[-1])
            if pid == os.getpid(): continue
            f = open(p + "/stat").read().rsplit(")", 1)[1].split()
            rss = int(f[21]) * 4096 / 2**20
            o[pid] = (int(f[11]) + int(f[12]), rss, len(os.listdir(p + "/fd")), int(f[17]))
        except OSError: pass
    return o
a = snap(); time.sleep(10); b = snap()
for pid in sorted(b):
    if pid in a:
        print(f"pid={pid} cpu={(b[pid][0]-a[pid][0])/10:.0f}% rss={b[pid][1]:.0f}MiB fds={b[pid][2]} threads={b[pid][3]}")
