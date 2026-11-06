# Abacus — consistent sum microservice

Python 3.12+, FastAPI, Redis. The Compose setup starts **two independent API containers** sharing one Redis datastore.

## Architecture

```text
Client -> FastAPI node 1 :8001 --+
                                 +--> Redis primary, key abacus:sum
Client -> FastAPI node 2 :8002 --+
```

All nodes use the same authoritative key. POST uses Redis `INCRBY`, a single atomic command, so concurrent increments are not lost. GET reads the primary directly without local caching or replica reads. DELETE uses atomic `SET key 0`. Concurrent operations are serialized by Redis; if reset races with additions, the final value follows the order Redis executes the commands.

## Run two nodes locally

Requires Docker Engine and Docker Compose v2.

```bash
docker compose up --build -d
docker compose ps
curl http://localhost:8001/health/ready
curl http://localhost:8002/health/ready
sh scripts/demo.sh
```

The demo resets the sum, adds 10 through node 1 and 7 through node 2, then reads through both nodes. Both reads should show `{"sum":17}`.

## Manual API calls

```bash
curl -X DELETE http://localhost:8001/abacus/sum
curl -X POST http://localhost:8001/abacus/number -H 'Content-Type: application/json' -d '{"number":25}'
curl -X POST http://localhost:8002/abacus/number -H 'Content-Type: application/json' -d '{"number":-3}'
curl http://localhost:8002/abacus/sum
```

Endpoints:
- `POST /abacus/number`, body `{"number": N}`; only integer JSON values accepted.
- `GET /abacus/sum`; returns `{"sum": N}`, zero if no key exists.
- `DELETE /abacus/sum`; atomically resets to zero.
- `/health/live` and `/health/ready` for liveness/readiness.

## Load demonstration

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
python scripts/load_test.py --base-urls http://localhost:8001,http://localhost:8002 --requests 1000 --concurrency 50
```

Reset before the run if you want a known starting value. If all 1,000 `+1` requests succeed, the expected sum from a zero start is 1,000.

## Tests

The integration tests require Redis at `localhost:6379`; they use Redis DB 1 by default. The Compose Redis is not exposed on the host, so either run a local Redis on port 6379 or temporarily add `ports: ["6379:6379"]` to the Redis service in `compose.yaml`.

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

## Consistency and production notes

- **Horizontal scale:** add more API containers; all must use the same Redis endpoint and key. Do not store the sum in Python globals or per-container memory.
- **Consistency:** with one Redis primary and reads directed to that primary, each successful command has a single execution order. Do not use replica reads if maximum read consistency is required.
- **Durability caveat:** this Compose setup enables AOF with `appendfsync everysec`, appropriate for a local demo but potentially losing recent writes after a severe host failure. Standard asynchronous Redis failover can lose acknowledged writes. Atomic commands alone do not provide consensus-backed linearizable failover. If strict no-acknowledged-write-loss across failover is required, choose a datastore/topology with documented strong-consistency guarantees, such as a transactional SQL database, and update with `UPDATE ... SET sum = sum + :delta RETURNING sum` inside a transaction.
- **Retries:** if a client times out after POST was committed, retrying can apply the increment twice. Exactly-once retry semantics require an idempotency key recorded atomically with the mutation.
- **Security:** protect DELETE with authorization, use TLS and an authenticated gateway, rate-limit callers, and store secrets outside source control.
- **Operations:** monitor request rates, 4xx/5xx, p50/p95/p99 latency, Redis latency/connections, and readiness failures. Load test before choosing workers, connection limits, or capacity.
- **Limits:** Redis integer operations are signed 64-bit. Define overflow/business constraints if applicable.
- **HA:** the local Compose file uses one Redis service. Production should use managed/HA storage with an explicit durability and consistency contract.

```bash
docker compose logs -f redis
docker compose logs -f abacus-1 abacus-2
docker compose down
# Destructive: also removes persisted demo data
docker compose down -v
```
