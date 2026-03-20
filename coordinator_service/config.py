from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "fraud_detection"

    behavioral_agent_url: str = "http://127.0.0.1:8001"
    geo_agent_url: str = "http://127.0.0.1:8002"
    merchant_agent_url: str = "http://127.0.0.1:8003"
    history_agent_url: str = "http://127.0.0.1:8004"
    agent_request_timeout_seconds: float = 10.0


settings = Settings()
