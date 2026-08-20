from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration settings."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    APP_NAME: str = "NetScan"
    DEBUG: bool = False
    SECRET_KEY: str = "netscan-insecure-secret-key-change-in-production"
    
    # Database
    DATABASE_URL: str = "sqlite:///./netscan.db"

    # Scanner Defaults
    DEFAULT_SCAN_INTERVAL_MINUTES: int = 60
    DEFAULT_MISS_THRESHOLD: int = 3
    DEFAULT_QUARANTINE_HOURS: int = 48
    NMAP_TIMEOUT_SECONDS: int = 300
    NMAP_TIMING_TEMPLATE: str = "-T4"
    TOP_TCP_PORTS: str = "80,443,22,445,3389,8080,8443,53"

    # Webhook Defaults
    WEBHOOK_TIMEOUT_SECONDS: int = 10
    WEBHOOK_MAX_RETRIES: int = 3


settings = Settings()
