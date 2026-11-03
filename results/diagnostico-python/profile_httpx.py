"""Só o cliente: mantém N chamadas simultâneas à mock-api por 40 s e perfila o último trecho."""
import asyncio, cProfile, pstats, sys, time
import httpx, uvloop
N = int(sys.argv[1]); done = 0; late = []
async def worker(c, stop):
    global done
    await asyncio.sleep(__import__("random").random() * 5)
    while time.time() < stop:
        t = time.time(); r = await c.get("http://mock-api:8080/delay"); done += 1; late.append(time.time() - t)
async def main():
    stop = time.time() + 40
    lim = httpx.Limits(max_connections=None, max_keepalive_connections=None, keepalive_expiry=60)
    async with httpx.AsyncClient(limits=lim, timeout=30) as c:
        ts = [asyncio.create_task(worker(c, stop)) for _ in range(N)]
        await asyncio.sleep(10)
        pr = cProfile.Profile(); pr.enable(); await asyncio.sleep(20); pr.disable()
        await asyncio.gather(*ts, return_exceptions=True)
    print(f"N={N} concluídas={done} ideal≈{N*40//5} latência média={sum(late)/max(1,len(late)):.2f}s")
    pstats.Stats(pr).sort_stats("tottime").print_stats(10)
uvloop.run(main())
