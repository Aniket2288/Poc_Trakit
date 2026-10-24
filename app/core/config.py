from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "TrackIt"

    database_host: str
    database_port: int = 5432
    database_user: str
    database_password: str
    database_name: str

    # Tokens
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 7

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173", "https://poc-trakit-frontend.onrender.com"]

    # Attachments
    upload_dir: str = "uploads"
    max_upload_bytes: int = 5 * 1024 * 1024  # 5 MB
    download_url_seconds: int = 300           # signed links work for 5 minutes

    # Background jobs and email
    redis_url: str = "redis://localhost:6379/1"
    email_backend: str = "console"  # "console" prints emails to the worker log; "smtp" sends them (e.g. to MailHog)
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    email_from: str = "TrackIt <no-reply@trackit.local>"
    frontend_url: str = "http://localhost:5173"

    # Logging and protection
    log_level: str = "INFO"
    log_sql: bool = False          # true = log every SQL statement (with request_id); used to spot N+1 queries
    auth_rate_limit: int = 10      # requests per window, per client IP, on /auth/*
    auth_rate_window_seconds: int = 60

    @property
    def database_url(self) -> URL:
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.database_user,
            password=self.database_password,
            host=self.database_host,
            port=self.database_port,
            database=self.database_name,
        )


settings = Settings()
