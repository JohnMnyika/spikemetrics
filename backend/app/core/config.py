from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+asyncpg://spike:spike@db:5432/spikemetrics"
    football_data_token: str = ""
    api_football_key: str = ""
    demo_mode: bool = True
    api_football_daily_limit: int = 100
    football_data_per_minute: int = 10
    football_data_competitions: str = "PL,PD,BL1,SA,FL1,CL,PPL,DED,ELC,BSA"
    sync_interval_hours: int = 6
    cors_origins: str = "http://localhost:5173"
    admin_api_token: str = ""
    cron_secret: str = ""


settings = Settings()
