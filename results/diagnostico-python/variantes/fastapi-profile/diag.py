"""FastAPI + httpx com cProfile por 15 s, a partir de 40 s depois do início, em cada worker."""
import asyncio, cProfile, os
from contextlib import asynccontextmanager
import app as base

app = base.app
inner = app.router.lifespan_context

async def profile():
    await asyncio.sleep(40)
    pr = cProfile.Profile(); pr.enable()
    await asyncio.sleep(15)
    pr.disable(); pr.dump_stats(f"/out/fastapi-{os.getpid()}.prof")

@asynccontextmanager
async def lifespan(a):
    async with inner(a):
        t = asyncio.create_task(profile())
        yield
        t.cancel()

app.router.lifespan_context = lifespan
