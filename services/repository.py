import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import NullPool

from config import settings


class Base(DeclarativeBase):
    pass


class EvaluationModel(Base):
    __tablename__ = "evaluations"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    app_id: Mapped[str] = mapped_column(String, index=True)
    timestamp: Mapped[str] = mapped_column(String, index=True)
    request: Mapped[str] = mapped_column(Text)   # JSON-encoded EvalRequest
    response: Mapped[str] = mapped_column(Text)   # JSON-encoded EvalResponse


def _make_engine(url: str):
    # NullPool avoids reusing a connection across event loops — safe for tests and
    # serverless/short-lived workers. A long-lived Postgres server can drop this
    # and tune pool_size/max_overflow instead.
    if url.startswith("sqlite"):
        return create_async_engine(url, poolclass=NullPool)
    return create_async_engine(url, pool_pre_ping=True)


engine = _make_engine(settings.database_url)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class EvaluationRepository:
    """
    Async SQLAlchemy store for evaluation logs. The same code targets SQLite
    (aiosqlite) locally and PostgreSQL (asyncpg) in production — only
    DATABASE_URL changes. Swapping the backend touches only this file; routes
    and services are untouched.
    """

    async def create_all(self) -> None:
        """Create tables if missing. Used for local/dev; production uses Alembic."""
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    @staticmethod
    def _to_dict(row: EvaluationModel) -> dict[str, Any]:
        return {
            "id": row.id,
            "app_id": row.app_id,
            "timestamp": row.timestamp,
            "request": json.loads(row.request),
            "response": json.loads(row.response),
        }

    async def save(
        self, app_id: str, request: dict[str, Any], response: dict[str, Any]
    ) -> str:
        record_id = str(uuid.uuid4())
        async with SessionLocal() as session:
            session.add(
                EvaluationModel(
                    id=record_id,
                    app_id=app_id,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    request=json.dumps(request),
                    response=json.dumps(response),
                )
            )
            await session.commit()
        return record_id

    async def find_by_id(self, record_id: str) -> dict[str, Any] | None:
        async with SessionLocal() as session:
            row = await session.get(EvaluationModel, record_id)
            return self._to_dict(row) if row else None

    async def find_by_app(self, app_id: str, limit: int = 50) -> list[dict[str, Any]]:
        async with SessionLocal() as session:
            result = await session.execute(
                select(EvaluationModel)
                .where(EvaluationModel.app_id == app_id)
                .order_by(EvaluationModel.timestamp.desc())
                .limit(limit)
            )
            return [self._to_dict(r) for r in result.scalars().all()]


# Module-level singleton — shared async engine + session factory across requests
repository = EvaluationRepository()
