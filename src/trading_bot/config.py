"""Configuration management using pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from enum import Enum


class Environment(str, Enum):
    """Trading environment."""
    TESTNET = "testnet"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )
    
    # Binance API
    binance_api_key: str = Field(..., description="Binance API key")
    binance_secret_key: str = Field(..., description="Binance secret key")
    binance_env: Environment = Field(
        default=Environment.TESTNET,
        description="Trading environment (testnet/production)"
    )
    
    # Testnet URLs
    binance_base_url: str = Field(
        default="https://testnet.binance.vision",
        description="Binance REST API base URL"
    )
    binance_ws_url: str = Field(
        default="wss://testnet.binance.vision/ws",
        description="Binance WebSocket URL"
    )
    
    # OpenRouter AI
    openrouter_api_key: str = Field(
        default="",
        description="OpenRouter API key"
    )
    openrouter_model: str = Field(
        default="anthropic/claude-sonnet-4-20250514",
        description="Model to use via OpenRouter"
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        description="OpenRouter API base URL"
    )
    
    # AI Settings
    ai_temperature: float = Field(
        default=0.3,
        description="LLM temperature (0-1, lower = more deterministic)"
    )
    ai_max_tokens: int = Field(
        default=2048,
        description="Max tokens in AI response"
    )
    
    # Telegram Alerts
    telegram_bot_token: str = Field(
        default="",
        description="Telegram bot token from @BotFather"
    )
    telegram_chat_id: str = Field(
        default="",
        description="Telegram chat ID for alerts"
    )
    
    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    
    @property
    def is_testnet(self) -> bool:
        """Check if running in testnet mode."""
        return self.binance_env == Environment.TESTNET
    
    @property
    def exchange_config(self) -> dict:
        """Get CCXT exchange configuration."""
        config = {
            "apiKey": self.binance_api_key,
            "secret": self.binance_secret_key,
            "enableRateLimit": True,
            "options": {
                "defaultType": "spot",
            },
        }
        
        if self.is_testnet:
            config["sandbox"] = True
            config["urls"] = {
                "api": {
                    "public": self.binance_base_url,
                    "private": self.binance_base_url,
                }
            }
        
        return config


# Global settings instance
settings = Settings()
