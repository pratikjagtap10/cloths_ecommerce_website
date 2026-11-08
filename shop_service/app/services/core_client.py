"""
SYNCHRONOUS microservice communication: HTTP calls from this service to the
Django core service's internal API.

Resilience features:
  * timeout on every call (a slow service must not hang ours)
  * retries with exponential backoff for connection problems
  * clear errors: if the core service is down we answer 503, not 500
"""
import asyncio
import logging

import httpx

from ..config import settings

logger = logging.getLogger(__name__)


class CoreServiceError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _detail(response: httpx.Response) -> str:
    try:
        return response.json().get("detail") or response.text
    except ValueError:
        return response.text or f"Core service error ({response.status_code})"


class CoreClient:
    def __init__(
        self,
        base_url: str = settings.core_service_url,
        api_key: str = settings.internal_api_key,
        timeout: float = settings.core_timeout_seconds,
        retries: int = settings.core_max_retries,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.base_url = base_url
        self.headers = {"X-Internal-Key": api_key}
        self.timeout = timeout
        self.retries = retries
        self.transport = transport

    async def _request(self, method: str, path: str, *, retry_on_timeout: bool = True, **kwargs) -> httpx.Response:
        retryable: tuple[type[Exception], ...] = (httpx.ConnectError,)
        if retry_on_timeout:
            retryable += (httpx.TimeoutException,)

        for attempt in range(self.retries + 1):
            try:
                async with httpx.AsyncClient(
                    base_url=self.base_url, headers=self.headers, timeout=self.timeout, transport=self.transport
                ) as client:
                    return await client.request(method, path, **kwargs)
            except retryable as exc:
                logger.warning("Core service %s %s failed (attempt %s): %s", method, path, attempt + 1, exc)
                if attempt < self.retries:
                    await asyncio.sleep(0.2 * 2**attempt)  # 0.2s, 0.4s, ...
            except httpx.TimeoutException as exc:
                logger.warning("Core service %s %s timed out (not retried): %s", method, path, exc)
                break
        raise CoreServiceError(503, "Catalog service is unavailable. Please try again shortly.")

    async def get_variant(self, variant_id: int) -> dict:
        """GET /internal/variants/{id}/ -> price, stock and product info."""
        response = await self._request("GET", f"/internal/variants/{variant_id}/")
        if response.status_code == 404:
            raise CoreServiceError(404, "Product variant not found.")
        if response.status_code != 200:
            logger.error("Unexpected core response %s: %s", response.status_code, response.text)
            raise CoreServiceError(502, "Unexpected response from catalog service.")
        return response.json()

    async def create_order(self, payload: dict) -> dict:
        """POST /internal/orders/ -> the created order.

        Timeouts are NOT retried here: the first request may have created the order
        already, and retrying could create a duplicate."""
        response = await self._request("POST", "/internal/orders/", json=payload, retry_on_timeout=False)
        if response.status_code == 201:
            return response.json()
        if response.status_code in (400, 404, 409):
            raise CoreServiceError(response.status_code, _detail(response))
        logger.error("Unexpected core response %s: %s", response.status_code, response.text)
        raise CoreServiceError(502, "Unexpected response from catalog service.")


_client = CoreClient()


def get_core_client() -> CoreClient:
    """FastAPI dependency (overridden with a fake in tests)."""
    return _client
