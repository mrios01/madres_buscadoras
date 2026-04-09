from functools import lru_cache
import os
from pydantic import BaseModel
from dotenv import load_dotenv


def _optional_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


class Settings(BaseModel):
    app_env: str = "local"
    app_port: int = 8888
    debug: bool = True

    mongodb_uri: str
    mongodb_dbname: str

    cookie_secret: str
    password_salt: str

    media_backend: str = "local"  # local | gcs
    media_local_root: str = "./data/media"
    media_public_base_url: str = "http://localhost:8080/media"

    gcs_project_id: str | None = None
    gcs_bucket: str | None = None
    gcs_signed_url_ttl_seconds: int = 3600

    auth_cookie_name: str = "ml_session"
    auth_cookie_secure: bool = False
    auth_cookie_samesite: str = "lax"
    auth_session_ttl_days: int = 14

    google_client_id: str | None = None
    google_client_secret: str | None = None

    recaptcha_site_key: str | None = None
    recaptcha_secret_key: str | None = None
    recaptcha_project_id: str | None = None
    recaptcha_min_score: float = 0.5

    bulletin_pubsub_enabled: bool = False
    bulletin_project_id: str | None = None
    bulletin_topic_id: str | None = None
    bulletin_subscription_id: str | None = None


@lru_cache
def get_settings() -> Settings:
    load_dotenv()
    return Settings(
        app_env=os.getenv("APP_ENV", "local"),
        app_port=int(os.getenv("APP_PORT", "8888")),
        debug=os.getenv("DEBUG", "true").lower() == "true",
        mongodb_uri=os.getenv("MONGODB_URI", "mongodb://127.0.0.1:27017"),
        mongodb_dbname=os.getenv("MONGODB_DBNAME", "marzlive_upgrade"),
        cookie_secret=os.getenv("COOKIE_SECRET", "change-me"),
        password_salt=os.getenv("PASSWORD_SALT", "change-me"),
        media_backend=os.getenv("MEDIA_BACKEND", "local"),
        media_local_root=os.getenv("MEDIA_LOCAL_ROOT", "./data/media"),
        media_public_base_url=os.getenv(
            "MEDIA_PUBLIC_BASE_URL",
            "http://localhost:8080/media",
        ),
        gcs_project_id=_optional_env("GCS_PROJECT_ID"),
        gcs_bucket=_optional_env("GCS_BUCKET"),
        gcs_signed_url_ttl_seconds=int(
            os.getenv("GCS_SIGNED_URL_TTL_SECONDS", "3600")
        ),
        auth_cookie_name=os.getenv("AUTH_COOKIE_NAME", "ml_session"),
        auth_cookie_secure=(
            os.getenv("AUTH_COOKIE_SECURE", "false").lower() == "true"
        ),
        auth_cookie_samesite=os.getenv("AUTH_COOKIE_SAMESITE", "lax"),
        auth_session_ttl_days=int(os.getenv("AUTH_SESSION_TTL_DAYS", "14")),
        google_client_id=_optional_env("GOOGLE_CLIENT_ID"),
        google_client_secret=_optional_env("GOOGLE_CLIENT_SECRET"),
        recaptcha_site_key=_optional_env("RECAPTCHA_SITE_KEY"),
        recaptcha_secret_key=_optional_env("RECAPTCHA_SECRET_KEY"),
        recaptcha_project_id=_optional_env("RECAPTCHA_PROJECT_ID"),
        recaptcha_min_score=float(os.getenv("RECAPTCHA_MIN_SCORE", "0.5")),
        bulletin_pubsub_enabled=(
            os.getenv("BULLETIN_PUBSUB_ENABLED", "false").lower()
            == "true"
        ),
        bulletin_project_id=(
            _optional_env("BULLETIN_PROJECT_ID")
            or _optional_env("GCP_PROJECT_ID")
            or _optional_env("GCS_PROJECT_ID")
        ),
        bulletin_topic_id=_optional_env("BULLETIN_TOPIC_ID"),
        bulletin_subscription_id=_optional_env("BULLETIN_SUBSCRIPTION_ID"),
    )
