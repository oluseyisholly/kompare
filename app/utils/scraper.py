from collections.abc import Mapping

import httpx
from bs4 import BeautifulSoup

QueryParams = Mapping[str, str | int | float | bool | None]
Headers = Mapping[str, str]

DEFAULT_BROWSER_HEADERS: dict[str, str] = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Upgrade-Insecure-Requests": "1",
}
DEFAULT_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/127.0.0.0 Safari/537.36"
)


async def get_html(
    url: str,
    *,
    params: QueryParams | None = None,
    headers: Headers | None = None,
    timeout: float = 10.0,
    client: httpx.AsyncClient | None = None,
) -> str:
    """Fetch a page and return its HTML content."""

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
        return response.text
    finally:
        if owns_client:
            await request_client.aclose()


async def get_soup(
    url: str,
    *,
    params: QueryParams | None = None,
    headers: Headers | None = None,
    timeout: float = 10.0,
    parser: str = "html.parser",
    client: httpx.AsyncClient | None = None,
) -> BeautifulSoup:
    """Fetch a page and parse it with BeautifulSoup."""

    html = await get_html(
        url,
        params=params,
        headers=headers,
        timeout=timeout,
        client=client,
    )
    return BeautifulSoup(html, parser)


async def render_html(
    url: str,
    *,
    wait_for: str = "networkidle",
    timeout: float = 30.0,
    headers: Headers | None = None,
) -> str:
    """Render a JavaScript-driven page with Playwright and return its HTML."""

    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            context = await browser.new_context(
                extra_http_headers=dict(headers or {}),
            )
            page = await context.new_page()
            await page.goto(url, wait_until=wait_for, timeout=timeout * 1000)
            return await page.content()
        finally:
            await browser.close()


def get_browser_headers(headers: Headers | None = None) -> dict[str, str]:
    """Return a browser-like header set merged with caller overrides."""

    merged_headers = dict(DEFAULT_BROWSER_HEADERS)
    if headers:
        merged_headers.update(dict(headers))
    if "User-Agent" not in merged_headers:
        merged_headers["User-Agent"] = DEFAULT_BROWSER_USER_AGENT
    return merged_headers


async def render_browser_html(
    url: str,
    *,
    wait_for: str = "domcontentloaded",
    timeout: float = 30.0,
    headers: Headers | None = None,
    wait_after_load_ms: int = 3000,
) -> str:
    """Open a page in Playwright using browser-like defaults and return HTML."""

    from playwright.async_api import async_playwright

    browser_headers = get_browser_headers(headers)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            context = await browser.new_context(
                user_agent=browser_headers["User-Agent"],
                locale="en-US",
                extra_http_headers=browser_headers,
                viewport={"width": 1440, "height": 900},
            )
            page = await context.new_page()
            await page.goto(url, wait_until=wait_for, timeout=timeout * 1000)
            if wait_after_load_ms > 0:
                await page.wait_for_timeout(wait_after_load_ms)
            return await page.content()
        finally:
            await browser.close()


async def render_browser_soup(
    url: str,
    *,
    wait_for: str = "domcontentloaded",
    timeout: float = 30.0,
    headers: Headers | None = None,
    parser: str = "html.parser",
    wait_after_load_ms: int = 3000,
) -> BeautifulSoup:
    """Open a page in Playwright with browser-like defaults and parse it."""

    html = await render_browser_html(
        url,
        wait_for=wait_for,
        timeout=timeout,
        headers=headers,
        wait_after_load_ms=wait_after_load_ms,
    )
    return BeautifulSoup(html, parser)


async def render_soup(
    url: str,
    *,
    wait_for: str = "networkidle",
    timeout: float = 30.0,
    headers: Headers | None = None,
    parser: str = "html.parser",
) -> BeautifulSoup:
    """Render a JavaScript-driven page and parse it with BeautifulSoup."""

    html = await render_html(
        url,
        wait_for=wait_for,
        timeout=timeout,
        headers=headers,
    )
    return BeautifulSoup(html, parser)
