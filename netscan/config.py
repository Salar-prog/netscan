from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration settings."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    APP_NAME: str = "NetScan"
    DEBUG: bool = False
    SECRET_KEY: str = ""

    # Database
    DATABASE_URL: str = "sqlite:///./netscan.db"

    # Scanner Defaults
    DEFAULT_SCAN_INTERVAL_MINUTES: int = 60
    DEFAULT_MISS_THRESHOLD: int = 3
    DEFAULT_QUARANTINE_HOURS: int = 48
    NMAP_TIMEOUT_SECONDS: int = 300
    NMAP_TIMING_TEMPLATE: str = "-T4"
    TOP_TCP_PORTS: str = "80,443,22,445,3389,8080,8443,53"
    MAX_SCAN_PREFIX_LENGTH: int = 24
    RATE_LIMIT_DEFAULT: str = "120/minute"

    # CORS
    ALLOWED_ORIGINS: str = ""

    # Trusted Proxies (comma-separated IPs for X-Forwarded-For)
    TRUSTED_PROXIES: str = ""

    # Webhook SSRF Protection (comma-separated CIDRs to block)
    WEBHOOK_BLOCKED_RANGES: str = (
        "127.0.0.0/8,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,169.254.169.254/32,::1/128,fd00::/8"
    )

    # Logging
    LOG_FORMAT: str = "text"  # "text" for dev, "json" for production
    LOG_LEVEL: str = "INFO"

    # Webhook Defaults
    WEBHOOK_TIMEOUT_SECONDS: int = 10
    WEBHOOK_MAX_RETRIES: int = 3

    # Dashboard session cookie (defaults to SECRET_KEY)
    SESSION_SECRET_KEY: str = ""

    # Bootstrap kill-switch: set to true to disable the HTTP bootstrap endpoint
    DISABLE_BOOTSTRAP: bool = False

    # LDAP / Active Directory
    LDAP_ENABLED: bool = False
    LDAP_SERVER_URI: str = ""
    LDAP_BIND_DN: str = ""
    LDAP_BIND_PASSWORD: str = ""
    LDAP_USER_SEARCH_BASE: str = ""
    LDAP_USER_SEARCH_FILTER: str = "(sAMAccountName={username})"
    LDAP_GROUP_SEARCH_BASE: str = ""
    LDAP_GROUP_SEARCH_FILTER: str = "(member={user_dn})"
    LDAP_START_TLS: bool = False
    LDAP_CA_CERT_FILE: str = ""

    def validate_for_production(self) -> None:
        if not self.DEBUG and not self.SECRET_KEY:
            raise ValueError(
                "SECRET_KEY must be set in production (DEBUG=False). Set it in your .env file or environment."
            )
        if not self.SESSION_SECRET_KEY:
            self.SESSION_SECRET_KEY = self.SECRET_KEY


settings = Settings()
