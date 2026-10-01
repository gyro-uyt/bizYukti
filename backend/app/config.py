from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_SECRET = "dev-only-secret-change-me-0123456789abcdef"


class Settings(BaseSettings):
    """All runtime configuration. Every value can be set through an environment variable
    of the same name (case-insensitive), e.g. DATABASE_URL, SECRET_KEY, OTP_DEV_ECHO."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: str = "development"  # development | test | production
    app_name: str = "BizYukti"
    public_web_url: str = "http://localhost:3000"
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://bizyukti:bizyukti@localhost:5432/bizyukti"
    redis_url: str = ""

    secret_key: str = _DEFAULT_SECRET
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    cookie_secure: bool = False
    cors_origins: str = "http://localhost:3000"
    ip_hash_salt: str = "rotate-this-salt"

    # One-time passcodes
    otp_ttl_minutes: int = 10
    otp_max_attempts: int = 5
    otp_dev_echo: bool = False  # returns the code in the API response; forced off in production
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "BizYukti <no-reply@bizyukti.local>"
    sms_webhook_url: str = ""  # POST {"to","message"} with Bearer token (MSG91/Twilio/Gupshup adapter)
    sms_webhook_token: str = ""
    admin_emails: str = ""  # comma separated; these accounts receive the admin role on sign-in
    admin_phones: str = ""

    # Media storage
    storage_backend: str = "local"  # local | s3
    media_root: str = "./media"
    media_public_base_url: str = "/media"
    s3_bucket: str = ""
    s3_endpoint_url: str = ""
    s3_region: str = "ap-south-1"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    max_upload_mb: int = 10

    # Background work: eager runs jobs in-process (dev/tests); otherwise RQ on Redis
    tasks_eager: bool = True

    # Geography
    default_city: str = "Gwalior"
    default_lat: float = 26.2183
    default_lng: float = 78.1828
    geocoder: str = "areas"  # areas | nominatim
    nominatim_url: str = "https://nominatim.openstreetmap.org"

    # Trust, matching and incentives
    local_radius_km: float = 5.0
    match_radius_km: float = 3.0
    demand_verify_min_supporters: int = 3
    growing_threshold: int = 10
    support_hourly_limit: int = 30

    # Optional intelligence providers (the product works fully without them)
    anthropic_api_key: str = ""
    llm_model: str = "claude-haiku-4-5-20251001"
    embeddings_url: str = ""  # OpenAI-compatible /v1/embeddings endpoint (OpenAI, Voyage, self-hosted)
    embeddings_api_key: str = ""
    embeddings_model: str = ""

    @model_validator(mode="after")
    def _blank_means_default(self):
        # `.env.example` ships keys like `MEDIA_PUBLIC_BASE_URL=` with no value; an empty string must not
        # override the default (it made every photo URL lose its /media prefix).
        if not self.media_public_base_url.strip():
            self.media_public_base_url = "/media"
        return self

    @model_validator(mode="after")
    def _production_guards(self):
        if self.env == "production":
            if self.secret_key == _DEFAULT_SECRET or len(self.secret_key) < 32:
                raise ValueError("SECRET_KEY must be set to a random value of 32+ characters in production")
            self.otp_dev_echo = False
            self.cookie_secure = True
        return self

    @staticmethod
    def _split(value: str) -> list[str]:
        return [v.strip() for v in value.split(",") if v.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return self._split(self.cors_origins)

    @property
    def admin_email_list(self) -> list[str]:
        return [v.lower() for v in self._split(self.admin_emails)]

    @property
    def admin_phone_list(self) -> list[str]:
        return self._split(self.admin_phones)

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
