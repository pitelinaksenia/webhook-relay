from arq import ArqRedis, create_pool
from arq.connections import RedisSettings

from webhook_relay.config import settings


async def get_arq_pool() -> ArqRedis:
    redis_settings = RedisSettings.from_dsn(settings.redis_url.get_secret_value())
    redis_settings.max_connections = settings.redis_max_connections
    return await create_pool(redis_settings)
