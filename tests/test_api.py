import asyncio, os
import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from app.main import app, SUM_KEY

@pytest.fixture
async def client():
    redis = Redis.from_url(os.getenv("TEST_REDIS_URL", "redis://localhost:6379/1"), decode_responses=True)
    try:
        await redis.ping()
    except Exception as exc:
        await redis.aclose()
        pytest.skip(f"Redis required for integration tests: {exc}")
    await redis.delete(SUM_KEY)
    app.state.redis = redis
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    await redis.delete(SUM_KEY)
    await redis.aclose()

@pytest.mark.asyncio
async def test_initial_sum_is_zero(client):
    assert (await client.get("/abacus/sum")).json() == {"sum": 0}

@pytest.mark.asyncio
async def test_add_read_reset(client):
    assert (await client.post("/abacus/number", json={"number": 7})).json() == {"sum": 7}
    assert (await client.post("/abacus/number", json={"number": -2})).json() == {"sum": 5}
    assert (await client.get("/abacus/sum")).json() == {"sum": 5}
    assert (await client.delete("/abacus/sum")).json() == {"sum": 0}
    assert (await client.get("/abacus/sum")).json() == {"sum": 0}

@pytest.mark.asyncio
async def test_rejects_invalid_payload(client):
    assert (await client.post("/abacus/number", json={"number": 1.5})).status_code == 422
    assert (await client.post("/abacus/number", json={"number": "3"})).status_code == 422
    assert (await client.post("/abacus/number", json={"number": 3, "extra": 4})).status_code == 422

@pytest.mark.asyncio
async def test_concurrent_adds(client):
    responses = await asyncio.gather(*(client.post("/abacus/number", json={"number": 1}) for _ in range(100)))
    assert all(r.status_code == 200 for r in responses)
    assert (await client.get("/abacus/sum")).json() == {"sum": 100}
