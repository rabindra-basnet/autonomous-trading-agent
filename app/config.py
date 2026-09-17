"""Central Application and Infrastructure Configuration."""

from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

from app.core.logging import setup_logging

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # App
    app_name: str = "AutoQuant-AI-Backend"
    environment: str = "production"
    api_host: str = "0.0.0.0"
    api_port: int = Field(default=8000, validation_alias="PORT")
    log_level: str = "INFO"

    # PostgreSQL
    database_url: str = Field(default="", validation_alias="DATABASE_URL")

    # Alembic
    alembic_config_path: Path = PROJECT_ROOT / "alembic.ini"
    alembic_script_location: Path = PROJECT_ROOT / "alembic"

    # DuckDB Analytical Lake
    duckdb_path: str = Field(default="data/trading_agent.duckdb", validation_alias="DUCKDB_PATH")

    # Redis Streams
    redis_url: str = Field(default="", validation_alias="REDIS_URL")
    event_bus_mode: str = Field(default="redis_streams", validation_alias="EVENT_BUS")

    # Universal OpenAI-Compatible LLM Configuration
    llm_base_url: str = Field(default="https://api.groq.com/openai/v1", validation_alias="OPENAI_BASE_URL")
    llm_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    llm_model: str = Field(default="llama-3.3-70b-versatile", validation_alias="OPENAI_MODEL")

    # LLM token cost accounting (USD per 1M tokens).
    # Optional per-model overrides via JSON, e.g.:
    # OPENAI_MODEL_PRICES='{"deepseek-v4-flash": {"input_per_1m": 0.14, "output_per_1m": 0.28}}'
    llm_input_price_per_1m: float = Field(default=0.0, validation_alias="OPENAI_INPUT_PRICE_PER_1M")
    llm_output_price_per_1m: float = Field(default=0.0, validation_alias="OPENAI_OUTPUT_PRICE_PER_1M")
    llm_model_prices: dict[str, dict[str, float]] = Field(default_factory=dict, validation_alias="OPENAI_MODEL_PRICES")


settings = Settings()

# Initialize root logging with configured log level
setup_logging(level=settings.log_level)
