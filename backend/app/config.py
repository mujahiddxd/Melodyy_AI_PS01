from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://hod:hod@localhost:5433/hod"
    jwt_secret: str = "change-me"
    jwt_expire_hours: int = 24
    otp_provider: str = "mock"
    otp_secret: str = "change-me-too"
    msg91_auth_key: str = ""
    msg91_template_id: str = ""
    llm_provider: str = "openai"
    llm_api_key: str = ""
    llm_model_text: str = ""
    llm_model_vision: str = ""
    llm_mock: bool = True
    llm_api_keys: str = ""  # extra fallback keys, comma-separated; tried after llm_api_key
    llm_model_fallbacks: str = ""  # fallback models, comma-separated; tried after llm_model_text
    stt_provider: str = "sarvam"
    sarvam_api_key: str = ""
    openai_api_key: str = ""
    cloudinary_url: str = ""
    store_audio: bool = False
    google_maps_api_key: str = ""
    backend_public_url: str = "http://localhost:8000"  # used to build /media URLs for local photo storage
    frontend_origin: str = "http://localhost:3000"
    tz_name: str = "Asia/Kolkata"

    @property
    def llm_keys(self) -> list[str]:
        """Primary key first, then the fallbacks. Whitespace stripped; empties and duplicates dropped."""
        return _csv([self.llm_api_key, *self.llm_api_keys.split(",")])

    @property
    def llm_models(self) -> list[str]:
        return _csv([self.llm_model_text, *self.llm_model_fallbacks.split(",")])


def _csv(values: list[str]) -> list[str]:
    out: list[str] = []
    for v in values:
        v = v.strip()
        if v and v not in out:
            out.append(v)
    return out

@lru_cache
def get_settings() -> Settings:
    return Settings()
