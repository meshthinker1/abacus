import logging, os, uuid
from contextlib import asynccontextmanager
from typing import Annotated
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis
from redis.exceptions import RedisError

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("abacus")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
SUM_KEY = os.getenv("ABACUS_SUM_KEY", "abacus:sum")

class AddNumberRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    number: Annotated[int, Field(strict=True, description="Integer amount to add")]

class SumResponse(BaseModel):
    sum: int

@asynccontextmanager
async def lifespan(app: FastAPI):
    redis = Redis.from_url(REDIS_URL, decode_responses=True,
                           socket_connect_timeout=2.0, socket_timeout=2.0,
                           health_check_interval=30)
    app.state.redis = redis
    try:
        await redis.ping()
        logger.info("Connected to Redis")
    except RedisError:
        await redis.aclose()
        logger.exception("Redis unavailable during startup")
        raise
    yield
    await redis.aclose()

app = FastAPI(title="Abacus Consistent Sum Service", version="1.0.0", lifespan=lifespan)

@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response

@app.get("/health/live", include_in_schema=False)
async def live():
    return {"status": "ok"}

@app.get("/health/ready", include_in_schema=False)
async def ready(request: Request):
    try:
        await request.app.state.redis.ping()
        return {"status": "ready"}
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="Storage unavailable") from exc

@app.post("/abacus/number", response_model=SumResponse)
async def add_number(payload: AddNumberRequest, request: Request):
    try:
        # Redis INCRBY is atomic: concurrent updates cannot overwrite each other.
        value = await request.app.state.redis.incrby(SUM_KEY, payload.number)
        return SumResponse(sum=int(value))
    except RedisError as exc:
        logger.exception("Add failed request_id=%s", request.headers.get("x-request-id"))
        raise HTTPException(status_code=503, detail="Storage unavailable; operation outcome may be unknown") from exc

@app.get("/abacus/sum", response_model=SumResponse)
async def get_sum(request: Request):
    try:
        value = await request.app.state.redis.get(SUM_KEY)
        return SumResponse(sum=int(value) if value is not None else 0)
    except RedisError as exc:
        logger.exception("Read failed")
        raise HTTPException(status_code=503, detail="Storage unavailable") from exc

@app.delete("/abacus/sum", response_model=SumResponse)
async def reset_sum(request: Request):
    try:
        # SET is atomic. Concurrent reset/add operations are ordered by Redis.
        await request.app.state.redis.set(SUM_KEY, "0")
        return SumResponse(sum=0)
    except RedisError as exc:
        logger.exception("Reset failed")
        raise HTTPException(status_code=503, detail="Storage unavailable; operation outcome may be unknown") from exc
