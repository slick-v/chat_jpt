from pydantic_settings import BaseSettings,SettingsConfigDict
from pydantic import SecretStr

class Settings(BaseSettings):
    # protected_namespaces=() stops pydantic warning about the "model_" prefix in model_name

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", protected_namespaces=())

    groq_api_key:str
    model_name:str = "openai/gpt-oss-120b"
    max_tokens: int =1024
    temperature: float = 0.1
    max_history_messages: int = 20 
    system_prompt: str = "You are a helpful, concise assistant."

    # DB
    database_path:str = "chat.db"
    # SecretStr hides the value if settings ever get printed or logged
    # AUTH
    jwt_secret_key:SecretStr
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60





settings = Settings()

