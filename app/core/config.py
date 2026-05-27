from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./ap_entries.db"
    LOG_LEVEL: str = "INFO"
    APP_NAME: str = "AP Integration API"
    APP_VERSION: str = "1.0.0"

    class Config:
        env_file = ".env"


settings = Settings()
