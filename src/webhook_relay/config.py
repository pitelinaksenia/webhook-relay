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
    app_name: str = "Webhook Relay"
    debug: bool = True
    env: Environment = Environment.LOCAL


settings = Settings()
