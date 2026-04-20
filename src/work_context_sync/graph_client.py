from __future__ import annotations

import time

import httpx


class GraphClient:
    BASE_URL = "https://graph.microsoft.com/v1.0"

    def __init__(self, config, auth_session):
        self.config = config
        self.auth_session = auth_session

    def _headers(self) -> dict:
        token = self.auth_session.acquire_token()
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

    def _request_with_retry(self, client: httpx.Client, url: str, params: dict | None = None) -> httpx.Response:
        retries = self.config.graph.request_retry_count
        base_wait = self.config.graph.request_retry_base_seconds

        for attempt in range(retries + 1):
            response = client.get(url, headers=self._headers(), params=params)
            if response.status_code != 429:
                response.raise_for_status()
                return response

            if attempt >= retries:
                response.raise_for_status()

            retry_after = response.headers.get("Retry-After")
            wait_seconds = int(retry_after) if retry_after and retry_after.isdigit() else base_wait * (attempt + 1)
            print(f"Graph throttled on {url}; retrying in {wait_seconds}s")
            time.sleep(wait_seconds)

        raise RuntimeError("Unreachable retry loop in GraphClient")

    def get(self, path: str, params: dict | None = None) -> dict:
        with httpx.Client(timeout=30.0) as client:
            response = self._request_with_retry(client, f"{self.BASE_URL}{path}", params=params)
            return response.json()

    def get_all(self, path: str, params: dict | None = None) -> dict:
        items = []
        next_url = f"{self.BASE_URL}{path}"
        request_params = params or {}

        with httpx.Client(timeout=30.0) as client:
            while next_url:
                response = self._request_with_retry(client, next_url, params=request_params)
                payload = response.json()
                items.extend(payload.get("value", []))
                next_url = payload.get("@odata.nextLink")
                request_params = None

        return {"value": items}
