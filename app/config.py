"""Central Application and Infrastructure Configuration."""

import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings
from pydantic import Field

load_dotenv()


class Settings(BaseSettings):
    # App
    app_name: str = "AutoQuant-AI-Backend"
    environment: str = "production"
    api_host: str = "0.0.0.0"
    api_port: int = Field(default=8000, validation_alias="PORT")
    log_level: str = "INFO"

    # PostgreSQL (Neon)
    database_url: str = Field(
        default="postgresql+asyncpg://neondb_owner:npg_l3VD4XPMNadO@ep-proud-breeze-au6jseod-pooler.c-10.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require",
        alias="DATABASE_URL",
    )

    # DuckDB Analytical Lake
    duckdb_path: str = Field(default="data/trading_agent.duckdb", alias="DUCKDB_PATH")

    # Redis Streams (Upstash)
    redis_url: str = Field(
        default="rediss://default:gQAAAAAABE5yAAIgcDI0NmM3NGMxY2JiMmM0NjkyYWVjYTA1OTU3MDA2Mzk0ZQ@informed-sunfish-282226.upstash.io:6379",
        alias="REDIS_URL",
    )
    event_bus_mode: str = Field(default="redis_streams", alias="EVENT_BUS")

    # Universal OpenAI-Compatible LLM API Configuration
    llm_base_url: str = Field(default="https://api.groq.com/openai/v1", alias="OPENAI_BASE_URL")
    llm_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    llm_model: str = Field(default="llama-3.3-70b-versatile", alias="OPENAI_MODEL")


settings = Settings()
