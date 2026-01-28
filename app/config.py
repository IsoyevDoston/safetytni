"""Configuration management using Pydantic Settings."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Webhook Security
    webhook_secret: str
    
    # Telegram Bot Configuration
    telegram_bot_token: str
    telegram_chat_id: str
    
    # Server Configuration
    host: str = "0.0.0.0"
    port: int = 8000  # Railway sets PORT env var, which will override this
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )


# Global settings instance
settings = Settings()
