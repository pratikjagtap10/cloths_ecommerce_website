from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All settings come from environment variables (names are case-insensitive),
    e.g. SHOP_DB_URL, JWT_SECRET, CORE_SERVICE_URL."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # This service's own database (database-per-service)
    shop_db_url: str = "postgresql+psycopg://shop:shop@shop_db:5432/shop_db"

    # Must be the SAME secret Django uses to sign JWTs
    jwt_secret: str = "change-me-dev-only"
    jwt_algorithm: str = "HS256"

    # Synchronous REST calls to the core (Django) service
    core_service_url: str = "http://core-service:8000"  # hyphen: see docker-compose.yml
    internal_api_key: str = "change-me-internal"
    core_timeout_seconds: float = 3.0
    core_max_retries: int = 2

    # Asynchronous events
    redis_url: str = "redis://redis:6379/0"
    events_channel: str = "events"
    enable_event_listener: bool = True

    cors_origins: str = "http://localhost,http://localhost:3000,http://localhost:3001"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
