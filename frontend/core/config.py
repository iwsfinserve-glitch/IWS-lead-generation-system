from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    API_BASE_URL: str = "http://localhost:8000/api/v1"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

# Instantiate a global settings object to be imported by other modules
settings = Settings()
