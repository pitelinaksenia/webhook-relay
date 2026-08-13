from enum import Enum

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    LOCAL = "local"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    database_url: SecretStr
    redis_url: SecretStr
    redis_max_connections: int = 100
    app_name: str = "Webhook Relay"
    debug: bool = True
    env: Environment = Environment.LOCAL
    secret_encryption_key: SecretStr
    http_connect_timeout: float = 5.0
    http_read_timeout: float = 10.0
    retry_max_attempts: int = 5
    retry_base_delay: float = 1.0
    retry_max_delay: float = 300.0
    retry_jitter: float = 1.0


settings = Settings()
