from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # backend/.env, .env 어디서 실행해도 찾을 수 있도록
    model_config = SettingsConfigDict(
        env_file=[".env", "backend/.env"],
        extra="ignore",
    )

    app_env: str = "development"
    secret_key: str = "dev-secret-key"

    # PostgreSQL
    database_url: str = "postgresql://localbiz:localbiz@localhost:5432/localbiz"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # OpenSearch
    opensearch_host: str = "localhost"
    opensearch_port: int = 9200
    opensearch_user: str = "admin"
    opensearch_password: str = "admin"

    # LLM
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    gemini_llm_api_key: str = ""

    # Google
    google_places_api_key: str = ""
    google_calendar_mcp_credentials: str = ""

    # Naver
    naver_client_id: str = ""
    naver_client_secret: str = ""

    # Seoul Open Data
    seoul_api_key: str = ""

    # Monitoring
    slack_webhook_url: str = ""
    jaeger_host: str = "localhost"
    jaeger_port: int = 6831

    # Cache TTL (seconds)
    google_places_ttl: int = 86400  # 24h
    naver_blog_ttl: int = 21600  # 6h

    # OpenSearch index names
    places_index: str = "places_vector"
    reviews_index: str = "place_reviews"
    events_index: str = "events_vector"


@lru_cache
def get_settings() -> Settings:
    return Settings()
