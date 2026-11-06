from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    database_url: str
    redis_url: str = 'redis://127.0.0.1:6379/0'
    admin_token: str
    signing_key: str
    storage: Path = Path('data')
    public_url: str = 'http://localhost:8000'
    smtp_host: str = '127.0.0.1'
    smtp_port: int = 1025
    mail_from: str = 'editor@conference.test'
    ai_provider: str = 'disabled'
    ai_model: str = ''
    ai_api_key: str = ''
    crossref_enabled: bool = False
    languagetool_url: str = ''
settings = Settings()
settings.storage.mkdir(parents=True,exist_ok=True)
