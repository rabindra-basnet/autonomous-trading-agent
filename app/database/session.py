"""Async database engine, session factory, and FastAPI session dependency.

The ``get_db_session`` dependency follows the FastAPI + SQLAlchemy pattern:
a generator that yields an ``AsyncSession``, commits on success and rolls
back (re-raising) on failure, so endpoint code never touches transactions.
"""

from __future__ import annotations

import asyncio
import logging
import ssl
import urllib.parse
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import exc
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

logger = logging.getLogger("DatabaseSession")


def sanitize_asyncpg_url(raw_url: str) -> tuple[str, dict]:
    """Sanitize Neon/Postgres connection URLs for asyncpg driver.

    Converts sslmode / channel_binding into a valid asyncpg SSL context and
    strips the query parameters asyncpg cannot handle.
    """
    parsed = urllib.parse.urlparse(raw_url)
    query_params = urllib.parse.parse_qs(parsed.query)

    connect_args: dict[str, Any] = {}
    sslmode = (query_params.get("sslmode") or [""])[0].lower()
    explicit_ssl = (query_params.get("ssl") or [""])[0].lower() in {"true", "1", "require"}
    requires_ssl = sslmode in {"require", "verify-ca", "verify-full"} or explicit_ssl
    if requires_ssl:
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        connect_args["ssl"] = ssl_ctx

    incompatible = {"sslmode", "channel_binding", "ssl"}
    filtered_query = {k: v for k, v in query_params.items() if k not in incompatible}
    new_query = urllib.parse.urlencode(filtered_query, doseq=True)
    clean_url = urllib.parse.urlunparse(parsed._replace(query=new_query))

    return clean_url, connect_args


clean_url, _connect_args = sanitize_asyncpg_url(settings.database_url)
engine = create_async_engine(
    clean_url,
    connect_args=_connect_args,
    echo=False,
    pool_pre_ping=True,
)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency providing a transactional ``AsyncSession``.

    Commits when the request succeeds and rolls back (then re-raises) when
    anything raises. The same session instance is reused by every repository
    injected into one request thanks to FastAPI's dependency caching.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except exc.SQLAlchemyError:
            await session.rollback()
            raise


async def run_migrations() -> None:
    """Apply Alembic migrations to ``head`` (runs in a thread; async-safe)."""
    from alembic.config import Config

    from alembic import command

    try:
        cfg = Config(str(settings.alembic_config_path))
        cfg.set_main_option("script_location", str(settings.alembic_script_location))
        await asyncio.to_thread(command.upgrade, cfg, "head")
        logger.info("PostgreSQL database migrations applied successfully.")
    except Exception:
        logger.exception("Error running PostgreSQL database migrations")
        raise