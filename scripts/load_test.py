import argparse, asyncio, time
import httpx

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-urls", default="http://localhost:8001,http://localhost:8002")
    parser.add_argument("--requests", type=int, default=1000)
    parser.add_argument("--concurrency", type=int, default=50)
    parser.add_argument("--increment", type=int, default=1)
    args = parser.parse_args()
    urls = [u.strip().rstrip("/") for u in args.base_urls.split(",") if u.strip()]
    sem = asyncio.Semaphore(args.concurrency)
    successes, failures = 0, 0
    start = time.perf_counter()
    async with httpx.AsyncClient(timeout=10.0) as client:
        async def send(i):
            nonlocal successes, failures
            async with sem:
                try:
                    r = await client.post(urls[i % len(urls)] + "/abacus/number", json={"number": args.increment})
                    if r.status_code == 200: successes += 1
                    else: failures += 1; print("Failed:", r.status_code, r.text)
                except httpx.HTTPError as exc:
                    failures += 1; print("Request error:", exc)
        await asyncio.gather(*(send(i) for i in range(args.requests)))
        elapsed = time.perf_counter() - start
        read = await client.get(urls[0] + "/abacus/sum")
        print(f"nodes={len(urls)} requests={args.requests} concurrency={args.concurrency}")
        print(f"successes={successes} failures={failures} seconds={elapsed:.3f} throughput_rps={successes/elapsed:.1f}")
        print("sum read from node 1:", read.json() if read.status_code == 200 else read.text)

if __name__ == "__main__":
    asyncio.run(main())
