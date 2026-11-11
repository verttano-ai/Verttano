from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Aplicação
    APP_NAME: str = "Verttano"
    URL_BASE: str = "http://localhost:8000"
    SECRET_KEY: str = "troque-esta-chave-por-uma-aleatoria-forte"
    ADMIN_TOKEN: str = "admin-token-forte-aqui"

    # Groq
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "openai/gpt-oss-120b"

    # Mercado Pago
    MP_ACCESS_TOKEN: str = ""
    MP_WEBHOOK_SECRET: str = ""

    # Limites
    LIMITE_GRATUITO_DIARIO_USD: float = 0.50

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
