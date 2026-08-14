from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel

from app.core.logger import logger
from app.repositories.base import BaseRepository


class BaseService:
    def __init__(self, repository: BaseRepository[Any]) -> None:
        self.repository = repository
        self.db = repository.db
        self.model = repository.model
        logger.info(f"Service initialized for repository {self.model.__name__}")

    def create_item(self, item_data: BaseModel) -> Any:
        entity = self.repository.create(item_data.dict())
        logger.info(f"Created {self.model.__name__} with ID {getattr(entity, self.repository.pk_name)}")
        return entity

    def list_items(self, order_by: str | None = None) -> list[Any]:
        items = self.repository.list(order_by=order_by)
        logger.info(f"Retrieved {len(items)} {self.model.__name__}(s)")
        return items

    def paginate_items(
        self,
        skip: int = 0,
        limit: int = 10,
        order_by: str | None = None,
    ) -> dict[str, Any]:
        items, total = self.repository.paginate(skip=skip, limit=limit, order_by=order_by)
        logger.info(
            f"Retrieved {len(items)} {self.model.__name__}(s) page (skip={skip}, limit={limit})"
        )
        return {
            "total": total,
            "skip": skip,
            "limit": limit,
            "items": items,
        }

    def get_item(self, item_id: int) -> Any:
        entity = self.repository.get(item_id)
        if not entity:
            raise HTTPException(
                status_code=404,
                detail=f"{self.model.__name__} with ID {item_id} not found",
            )
        logger.info(f"Retrieved {self.model.__name__} with ID {item_id}")
        return entity

    def update_item(self, item_id: int, item_data: BaseModel) -> Any:
        entity = self.repository.update(item_id, item_data.dict(exclude_unset=True))
        if not entity:
            raise HTTPException(
                status_code=404,
                detail=f"{self.model.__name__} with ID {item_id} not found",
            )
        logger.info(f"Updated {self.model.__name__} with ID {item_id}")
        return entity

    def delete_item(self, item_id: int) -> dict[str, str]:
        entity = self.repository.delete(item_id)
        if not entity:
            raise HTTPException(
                status_code=404,
                detail=f"{self.model.__name__} with ID {item_id} not found",
            )
        logger.info(f"Deleted {self.model.__name__} with ID {item_id}")
        return {"message": f"{self.model.__name__} with ID {item_id} deleted successfully"}
