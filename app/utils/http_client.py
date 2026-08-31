from collections.abc import Callable, Mapping
from typing import Any, TypeVar, overload

import httpx

T = TypeVar("T")

QueryParams = Mapping[str, str | int | float | bool | None]
Headers = Mapping[str, str]


@overload
async def get_json(
    url: str,
    *,
    parser: Callable[[Any], T],
    params: QueryParams | None = None,
    headers: Headers | None = None,
    timeout: float = 10.0,
    client: httpx.AsyncClient | None = None,
) -> T: ...


@overload
async def get_json(
    url: str,
    *,
    parser: None = None,
    params: QueryParams | None = None,
    headers: Headers | None = None,
    timeout: float = 10.0,
    client: httpx.AsyncClient | None = None,
) -> Any: ...


async def get_json(
    url: str,
    *,
    parser: Callable[[Any], T] | None = None,
    params: QueryParams | None = None,
    headers: Headers | None = None,
    timeout: float = 10.0,
    client: httpx.AsyncClient | None = None,
) -> T | Any:
    """Send a GET request and return its decoded JSON response.

    Pass a parser such as ``SomePydanticModel.model_validate`` when a typed
    result is required. HTTPX exceptions are allowed to reach the caller so
    adapters can decide how failures should be recorded or retried.
    """

    owns_client = client is None
    request_client = client or httpx.AsyncClient()

    try:
        response = await request_client.get(
            url,
            params=params,
            headers=headers,
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        return parser(payload) if parser else payload
    finally:
        if owns_client:
            await request_client.aclose()
