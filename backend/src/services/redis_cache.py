import json
from typing import Any

from fastapi.encoders import jsonable_encoder
from redis import Redis
from redis.exceptions import RedisError

from src.core.config import settings


_redis_client: Redis | None = None


def get_redis_client() -> Redis | None:
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    try:
        client = Redis.from_url(settings.redis_url, decode_responses=True)
        client.ping()
        _redis_client = client
        return _redis_client
    except RedisError:
        return None


def get_json(key: str) -> Any | None:
    client = get_redis_client()
    if client is None:
        return None

    try:
        raw = client.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except (RedisError, json.JSONDecodeError):
        return None


def set_json(key: str, value: Any, ttl_seconds: int) -> None:
    client = get_redis_client()
    if client is None:
        return

    try:
        payload = json.dumps(jsonable_encoder(value), ensure_ascii=False)
        client.setex(key, ttl_seconds, payload)
    except RedisError:
        return


def delete_key(key: str) -> None:
    client = get_redis_client()
    if client is None:
        return

    try:
        client.delete(key)
    except RedisError:
        return
