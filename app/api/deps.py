"""FastAPI dependency helpers wiring the session into feature repositories.

Follows the repository pattern: endpoints declare a repository dependency
(e.g. ``order_repo: OrderRepositoryDep``) and never touch the ORM session
themselves. FastAPI caches ``get_db_session`` per request so every repository
injected into one request shares the same transaction.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import models, repository, session


def get_repository(
    model: type[models.Base],
) -> Callable[[AsyncSession], repository.DatabaseRepository]:
    """Dependency factory returning the database session bound to ``model``."""

    def func(sess: AsyncSession = Depends(session.get_db_session)) -> repository.DatabaseRepository:  # noqa: B008
        return repository.DatabaseRepository(model, sess)

    return func


async def get_order_repository(sess: AsyncSession = Depends(session.get_db_session)) -> repository.OrderRepository:  # noqa: B008
    return repository.OrderRepository(sess)


async def get_symbol_repository(sess: AsyncSession = Depends(session.get_db_session)) -> repository.SymbolRepository:  # noqa: B008
    return repository.SymbolRepository(sess)


async def get_llm_usage_repository(
    sess: AsyncSession = Depends(session.get_db_session),  # noqa: B008
) -> repository.LLMUsageRepository:
    return repository.LLMUsageRepository(sess)


async def get_experiment_repository(
    sess: AsyncSession = Depends(session.get_db_session),  # noqa: B008
) -> repository.ExperimentRepository:
    return repository.ExperimentRepository(sess)


OrderRepositoryDep = Annotated[repository.OrderRepository, Depends(get_order_repository)]
SymbolRepositoryDep = Annotated[repository.SymbolRepository, Depends(get_symbol_repository)]
LLMUsageRepositoryDep = Annotated[repository.LLMUsageRepository, Depends(get_llm_usage_repository)]
ExperimentRepositoryDep = Annotated[repository.ExperimentRepository, Depends(get_experiment_repository)]