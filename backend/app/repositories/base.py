from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.base import BaseModel

ModelT = TypeVar("ModelT", bound=BaseModel)


class BaseRepository(Generic[ModelT]):
    """Generic repository offering tenant-scoped primitive operations."""

    model: type[ModelT]

    def __init__(self, db: Session):
        self.db = db

    def get(self, id_: str) -> ModelT | None:
        return self.db.get(self.model, id_)

    def get_for_business(self, business_id: str, id_: str) -> ModelT | None:
        stmt = select(self.model).where(
            self.model.id == id_, self.model.business_id == business_id
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_for_business(
        self, business_id: str, *, skip: int = 0, limit: int = 100, **filters: Any
    ) -> list[ModelT]:
        stmt = select(self.model).where(self.model.business_id == business_id)
        for key, value in filters.items():
            if value is not None and hasattr(self.model, key):
                stmt = stmt.where(getattr(self.model, key) == value)
        stmt = stmt.offset(skip).limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    def add(self, entity: ModelT) -> ModelT:
        self.db.add(entity)
        self.db.flush()
        return entity

    def delete(self, entity: ModelT) -> None:
        self.db.delete(entity)
        self.db.flush()
