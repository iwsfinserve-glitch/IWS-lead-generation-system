from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator, AliasChoices, Field

class Settings(BaseSettings):
    API_BASE_URL: str = Field(
        default="http://localhost:8000/api/v1",
        validation_alias=AliasChoices("API_BASE_URL", "BACKEND_URL")
    )

    @field_validator("API_BASE_URL", mode="before")
    @classmethod
    def format_api_url(cls, v: str) -> str:
        if not v:
            return "http://localhost:8000/api/v1"
        v = v.strip().rstrip("/")
        if not (v.startswith("http://") or v.startswith("https://")):
            v = f"https://{v}"
        if not v.endswith("/api/v1"):
            v = f"{v}/api/v1"
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
