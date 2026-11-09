from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AliasChoices, Field, model_validator
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
    smtp_username: str = ''
    smtp_password: str = ''
    smtp_starttls: bool = False
    smtp_ssl: bool = False
    mail_from: str = 'editor@conference.test'
    ai_provider: str = 'disabled'
    ai_model: str = ''
    ai_api_key: str = Field(default='',validation_alias=AliasChoices('AI_API_KEY','GEMINI_API_KEY','GOOGLE_API_KEY'))
    crossref_enabled: bool = False
    languagetool_url: str = ''
    review_chunk_chars: int = 10000
    review_retries: int = 3
    job_timeout_seconds: int = 1200
    compile_queue: Path = Path('data/compile-queue')
    compile_timeout_seconds: int = 180
    mail_mode: str = 'DEMO'
    n8n_url: str = 'http://127.0.0.1:5678'
    mailpit_api_url: str = 'http://127.0.0.1:8025'
    @model_validator(mode='after')
    def select_gemini_defaults(self):
        if self.ai_api_key and self.ai_provider=='disabled' and 'ai_provider' not in self.model_fields_set:self.ai_provider='gemini'
        if self.ai_provider=='gemini' and not self.ai_model:self.ai_model='gemini-2.5-flash'
        return self
settings = Settings()
settings.storage.mkdir(parents=True,exist_ok=True)
