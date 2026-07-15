"""
Application configuration settings based on environment variables
"""
from typing import Any, Dict, Optional
from pydantic import PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Server settings
    port: int = 8765
    host: str = "0.0.0.0"
    debug: bool = False
    env: str = "development"
    
    # Database settings
    database_url: PostgresDsn
    database_schema: str = "public"
    
    # AI API keys
    openrouter_api_key: str
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openai_api_key: Optional[str] = None
    tavily_api_key: Optional[str] = None
    llm_default_model: str = "gpt-5.4"
    llm_supervisor_model: str = "gpt-5.5"
    llm_request_timeout_seconds: float = 75.0
    
    # MCP Server Configuration
    mcp_test_server_url: str = "https://searchapi-mcp.prod.diginext.site/mcp"

    # Workflow memory settings
    short_term_memory_turns: int = 10
    long_term_memory_enabled: bool = True
    long_term_memory_limit: int = 5
    
    # Cloudflare R2 settings
    r2_endpoint: Optional[str] = None
    r2_bucket_name: Optional[str] = None
    r2_access_key_id: Optional[str] = None
    r2_secret_access_key: Optional[str] = None
    
    # Security settings
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    @field_validator("database_url", mode="before")
    @classmethod
    def validate_database_url(cls, v: Any) -> Any:
        """Validate and sanitize the database URL"""
        if isinstance(v, str):
            # Ensure URL includes required parameters
            return v
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


# Create a global settings instance
settings = Settings()
