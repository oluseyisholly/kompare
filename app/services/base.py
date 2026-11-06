from typing import Dict, List, Type, TypeVar

from pydantic import BaseModel
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestError, NotFoundError
from app.core.logger import logger

ModelType = TypeVar("ModelType")


class BaseService:
    def __init__(self, db: Session, model: Type[ModelType]) -> None:
        """Initialize the service with a database session and a model."""
        self.db = db
        self.model = model
        # Obtener el nombre de la clave primaria dinámicamente
        self.pk_name = self._get_primary_key_name()
        logger.info(f"Service initialized for model {self.model.__name__} with PK: {self.pk_name}")

    def _get_primary_key_name(self) -> str:
        """Get the primary key column name for the model."""
        mapper = inspect(self.model)
        pk_columns = [key.name for key in mapper.primary_key]
        if not pk_columns:
            raise ValueError(f"Model {self.model.__name__} has no primary key defined")
        return pk_columns[0]  # Retorna la primera PK (en caso de PKs compuestas)

    def create_item(self, item_data: BaseModel) -> ModelType:
        """Create a new item in the database."""
        item = self.model(**item_data.model_dump())
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        pk_value = getattr(item, self.pk_name)
        logger.info(f"Created {self.model.__name__} with ID {pk_value}")
        return item

    def list_items(self, order_by: str | None = None) -> List[ModelType]:
        """Retrieve a list of all items, optionally ordered by a field."""
        parts = (order_by or self.pk_name).split()
        columns = inspect(self.model).columns.keys()
        if (
            len(parts) not in {1, 2}
            or parts[0] not in columns
            or (len(parts) == 2 and parts[1].lower() not in {"asc", "desc"})
        ):
            raise BadRequestError("Invalid sort column or direction")
        column = getattr(self.model, parts[0])
        ordering = column.desc() if len(parts) == 2 and parts[1].lower() == "desc" else column.asc()
        items = self.db.query(self.model).order_by(ordering).all()
        logger.info(f"Retrieved {len(items)} {self.model.__name__}(s)")
        return items

    def get_item(self, item_id: int) -> ModelType:
        """Retrieve a single item by its ID."""
        primary_key_field = getattr(self.model, self.pk_name)
        item = self.db.query(self.model).filter(primary_key_field == item_id).first()
        if not item:
            raise NotFoundError(
                f"{self.model.__name__} with ID {item_id} not found",
                data={"item_id": item_id, "model": self.model.__name__},
            )
        logger.info(f"Retrieved {self.model.__name__} with ID {item_id}")
        return item

    def update_item(self, item_id: int, item_data: BaseModel) -> ModelType:
        """Update an existing item with new data."""
        primary_key_field = getattr(self.model, self.pk_name)
        item = self.db.query(self.model).filter(primary_key_field == item_id).first()
        if not item:
            logger.warning(f"{self.model.__name__} with ID {item_id} not found")
            raise NotFoundError(
                f"{self.model.__name__} with ID {item_id} not found",
                data={"item_id": item_id, "model": self.model.__name__},
            )

        for key, value in item_data.model_dump(exclude_unset=True).items():
            setattr(item, key, value)

        self.db.commit()
        self.db.refresh(item)
        logger.info(f"Updated {self.model.__name__} with ID {item_id}")
        return item

    def delete_item(self, item_id: int) -> Dict[str, str]:
        """Delete an item from the database."""
        primary_key_field = getattr(self.model, self.pk_name)
        item = self.db.query(self.model).filter(primary_key_field == item_id).first()
        if not item:
            logger.warning(f"{self.model.__name__} with ID {item_id} not found for deletion")
            raise NotFoundError(
                f"{self.model.__name__} with ID {item_id} not found",
                data={"item_id": item_id, "model": self.model.__name__},
            )

        self.db.delete(item)
        self.db.commit()
        logger.info(f"Deleted {self.model.__name__} with ID {item_id}")
        return {"message": f"{self.model.__name__} with ID {item_id} deleted successfully"}
