import hashlib
import json
import re
import time
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from app.adapters.giftcard.tbay import TbayAdapter, TbayResponseError


class TbayAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_pagination_retry_restarts_scope_and_succeeds(self):
        from app.adapters.giftcard.tbay import TbayPaginationError
        adapter = TbayAdapter()
        with patch.object(adapter, "_fetch_offers_once", new=AsyncMock(side_effect=[
            TbayPaginationError("count mismatch", code="806206"), [{"code": "complete"}],
        ])) as fetch, patch("app.adapters.giftcard.tbay.asyncio.sleep", new=AsyncMock()):
            rows = await adapter.fetch_offers("razer", "USD")
        self.assertEqual(rows, [{"code": "complete"}])
        self.assertEqual(fetch.await_count, 2)

    async def test_exhausted_retry_reports_scope(self):
        from app.adapters.giftcard.tbay import TbayPaginationError
        adapter = TbayAdapter()
        with patch.object(adapter, "_fetch_offers_once", new=AsyncMock(side_effect=
            TbayPaginationError("count mismatch", code="806206"))) as fetch, \
                patch("app.adapters.giftcard.tbay.asyncio.sleep", new=AsyncMock()):
            with self.assertRaises(TbayPaginationError) as caught:
                await adapter.fetch_offers("razer", "USD")
        self.assertEqual(fetch.await_count, 3)
        self.assertEqual(caught.exception.data["category_id"], "razer")
        self.assertEqual(caught.exception.data["attempt"], 3)

    async def asyncSetUp(self):
        self.adapter = TbayAdapter(signing_salt="test-salt")
        self.requests = []

    def transport(self, responder):
        def handle(request):
            self.requests.append(request)
            code = request.url.params["code"]
            expected = hashlib.md5(f'{code}{request.headers["requestTime"]}test-salth5'.encode()).hexdigest()
            self.assertEqual(request.headers["sign"], expected)
            if code == "600000":
                return httpx.Response(200, json={"errorCode": "0", "data": {"serverTimestamp": str(int(time.time()*1000))}})
            return responder(request)
        return httpx.MockTransport(handle)

    @staticmethod
    def payload(request):
        return json.loads(re.search(r'name="json"\r\n\r\n(.*?)\r\n', request.content.decode()).group(1))

    async def test_pagination_signing_and_sanitization(self):
        def response(request):
            params = self.payload(request)
            page = params["start"]
            row = {"code": str(page), "giftcardType": "razer", "tradeCurrency": "USD",
                   "fixTrade": "10||50", "user": {"email": "private@example.com"}, "publishIp": "private"}
            return httpx.Response(200, json={"errorCode": "0", "data": {"totalCount": 2, "totalPage": 2, "list": [row]}})
        async with httpx.AsyncClient(transport=self.transport(response)) as client:
            rows = await self.adapter.fetch_offers("razer", "usd", client=client, page_size=1)
            self.assertFalse(client.is_closed)
        self.assertEqual([row["code"] for row in rows], ["1", "2"])
        self.assertEqual(rows[0]["fixTrade"], "10||50")
        self.assertNotIn("user", rows[0])
        self.assertNotIn("publishIp", rows[0])
        self.assertEqual(len(self.requests), 3)

    async def test_business_error_does_not_become_empty_catalog(self):
        async with httpx.AsyncClient(transport=self.transport(lambda _: httpx.Response(200, json={"errorCode": "000351", "data": []}))) as client:
            with self.assertRaises(TbayResponseError):
                await self.adapter.fetch_categories(client=client)

    async def test_repeated_page_fails(self):
        data = {"totalCount": 3, "totalPage": 3, "list": [{"code": "same", "giftcardType": "razer", "tradeCurrency": "USD"}]}
        async with httpx.AsyncClient(transport=self.transport(lambda _: httpx.Response(200, json={"errorCode": "0", "data": data}))) as client:
            with self.assertRaises(TbayResponseError):
                await self.adapter.fetch_offers("razer", "USD", client=client)

    async def test_partial_catalog_is_rejected(self):
        data = {"totalCount": 10, "totalPage": 1, "list": []}
        async with httpx.AsyncClient(transport=self.transport(lambda _: httpx.Response(200, json={"errorCode": "0", "data": data}))) as client:
            with self.assertRaises(TbayResponseError):
                await self.adapter.fetch_offers("razer", "USD", client=client)

    async def test_http_failure_propagates(self):
        async with httpx.AsyncClient(transport=self.transport(lambda _: httpx.Response(429))) as client:
            with self.assertRaises(httpx.HTTPStatusError):
                await self.adapter.fetch_categories(client=client)

    async def test_invalid_json_fails(self):
        async with httpx.AsyncClient(transport=self.transport(lambda _: httpx.Response(200, text="<html>challenge</html>"))) as client:
            with self.assertRaises(TbayResponseError):
                await self.adapter.fetch_categories(client=client)

    async def test_invalid_points_rate_fails(self):
        async with httpx.AsyncClient(transport=self.transport(lambda _: httpx.Response(200, json={"errorCode": "0", "data": {"mid": "NaN"}}))) as client:
            with self.assertRaises(TbayResponseError):
                await self.adapter.fetch_points_rate(client=client)


if __name__ == "__main__":
    unittest.main()
