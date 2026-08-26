from arq import ArqRedis, create_pool
from arq.connections import RedisSettings
from redis.exceptions import ConnectionError as RedisConnectionError

from webhook_relay.config import settings


def get_redis_settings() -> RedisSettings:
    redis_settings = RedisSettings.from_dsn(settings.redis_url.get_secret_value())
    redis_settings.max_connections = settings.redis_max_connections
    redis_settings.retry_on_timeout = True
    redis_settings.retry_on_error = [RedisConnectionError]
    return redis_settings


async def get_arq_pool() -> ArqRedis:
    return await create_pool(get_redis_settings())
