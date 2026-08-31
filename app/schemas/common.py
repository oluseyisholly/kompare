from math import ceil
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PaginationMeta(BaseModel):
    page: int
    per_page: int
    total: int
    total_pages: int
    has_next: bool
    has_previous: bool


class PaginatedData(BaseModel, Generic[T]):
    items: list[T]
    pagination: PaginationMeta


class ApiResponse(BaseModel, Generic[T]):
    responseCode: int
    message: str
    data: T


def build_pagination(*, page: int, per_page: int, total: int) -> PaginationMeta:
    total_pages = ceil(total / per_page) if total else 0
    return PaginationMeta(
        page=page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_previous=page > 1,
    )


def build_paginated_data(*, items: list[T], page: int, per_page: int, total: int) -> PaginatedData[T]:
    return PaginatedData(
        items=items,
        pagination=build_pagination(page=page, per_page=per_page, total=total),
    )


def build_paginated_response(
    *,
    items: list[T],
    page: int,
    per_page: int,
    total: int,
    message: str,
    response_code: int = 200,
) -> ApiResponse[PaginatedData[T]]:
    return ApiResponse(
        responseCode=response_code,
        message=message,
        data=build_paginated_data(items=items, page=page, per_page=per_page, total=total),
    )
