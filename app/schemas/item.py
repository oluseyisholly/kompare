from typing import Optional

from pydantic import BaseModel


class ItemBase(BaseModel):
    name: str
    description: Optional[str] = None


class ItemCreate(ItemBase):
    pass


class ItemRead(ItemBase):
    id: int

    class Config:
        orm_mode = True


class ItemPage(BaseModel):
    total: int
    skip: int
    limit: int
    items: list[ItemRead]
