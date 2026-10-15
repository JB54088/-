import json
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen


class DataPoolClientError(RuntimeError):
    pass


class DataPoolClient:
    """Small HTTP adapter for a separately deployed Playwright data-pool service."""

    def __init__(self, base_url: str, api_key: str = "", timeout_seconds: int = 30, customers_path: str = "/customers", orders_path: str = "/orders"):
        self.base_url = base_url.strip()
        self.api_key = api_key.strip()
        self.timeout_seconds = timeout_seconds
        self.customers_path = customers_path
        self.orders_path = orders_path

    def _request(self, path: str, params: dict[str, str] | None = None):
        if not self.base_url:
            raise DataPoolClientError("未配置 DATA_POOL_URL，无法连接数据池")
        url = urljoin(f"{self.base_url.rstrip('/')}/", path.lstrip("/"))
        if params:
            url = f"{url}?{urlencode(params)}"
        headers = {"Accept": "application/json", "User-Agent": "customer-assets-data-pool-client/1.0"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            headers["X-Data-Pool-Key"] = self.api_key
        request = Request(url, headers=headers, method="GET")
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise DataPoolClientError(f"数据池请求失败 HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise DataPoolClientError(f"数据池连接失败: {exc}") from exc

    @staticmethod
    def _rows(payload, key: str) -> list[dict]:
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for candidate in (key, "data", "items", "results"):
                value = payload.get(candidate)
                if isinstance(value, list):
                    return value
        raise DataPoolClientError(f"数据池返回格式错误，未找到 {key} 数组")

    def fetch_customers(self, updated_after: datetime | None = None) -> list[dict]:
        params = {"updated_after": updated_after.isoformat()} if updated_after else None
        return self._rows(self._request(self.customers_path, params), "customers")

    def fetch_orders(self, updated_after: datetime | None = None) -> list[dict]:
        params = {"updated_after": updated_after.isoformat()} if updated_after else None
        return self._rows(self._request(self.orders_path, params), "orders")
