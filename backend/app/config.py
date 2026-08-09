"""Application configuration for the Astitva backend."""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven settings that keep external providers configurable."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    project_name: str = "Astitva"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True
    secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    database_url: str = "postgresql+psycopg://astitva:astitva@localhost:5432/astitva"
    chroma_persist_directory: str = "./data/processed/chroma"
    chroma_collection_name: str = "astitva_documents"
    llm_provider: str = "placeholder"
    embedding_provider: str = "sentence_transformers"
    embedding_model: str = "all-MiniLM-L6-v2"
    vector_store_provider: str = "chromadb"
    risk_model_provider: str = "placeholder"
    # IBM Granite — local MLX server (primary) or Hugging Face (fallback)
    granite_base_url: str = "http://127.0.0.1:8080/v1"
    granite_local_model_id: str = "mlx-community/granite-3.3-8b-instruct-8bit"
    granite_model_id: str = "ibm-granite/granite-3.3-8b-instruct"  # HF fallback model id
    hf_api_token: str = ""
    allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    enable_audit_logging: bool = True
    enable_pii_filtering: bool = True

    @field_validator("debug", mode="before")
    @classmethod
    def normalize_debug(cls, value: object) -> bool:
        """Accept common non-boolean environment values for debug mode."""

        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on", "debug", "development"}:
                return True
            if normalized in {"0", "false", "no", "off", "release", "production"}:
                return False
        return bool(value)


@lru_cache
def get_settings() -> Settings:
    """Return a cached application settings object."""

    return Settings()
