from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    deepgram_api_key: str = ""
    deepgram_model: str = "nova-2"
    deepgram_language: str = "en"
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""
    elevenlabs_model: str = "eleven_multilingual_v2"
    redis_url: str = "redis://localhost:6379/0"
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/voiceintake"
    log_level: str = "info"
    langsmith_api_key: str = ""
    langsmith_project: str = ""


settings = Settings()
