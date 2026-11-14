from typing import Any

import httpx

from app.core.config import PROVIDER_URL


class ProviderError(Exception):
    pass


class ProviderUnavailable(ProviderError):
    pass


class ProviderClient:
    def __init__(self):
        self.base_url = PROVIDER_URL.rstrip("/")
        self.timeout = httpx.Timeout(8.0, connect=3.0)

    def create_call(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = httpx.post(
                f"{self.base_url}/v1/calls",
                json=payload,
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(str(exc)) from exc

        if response.status_code in (200, 201):
            return response.json()

        if response.status_code == 503:
            raise ProviderUnavailable("Provider returned HTTP 503")

        if response.status_code == 504:
            raise ProviderUnavailable("Provider returned ambiguous HTTP 504")

        raise ProviderError(
            f"Provider rejected call: HTTP {response.status_code}: "
            f"{response.text[:1000]}"
        )

    def find_by_request_id(self, request_id: str) -> dict[str, Any] | None:
        try:
            response = httpx.get(
                f"{self.base_url}/v1/calls",
                params={"request_id": request_id},
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(str(exc)) from exc

        if response.status_code == 404:
            return None

        if response.status_code == 200:
            return response.json()

        raise ProviderError(
            f"Provider lookup failed: HTTP {response.status_code}: "
            f"{response.text[:1000]}"
        )

    def get_call(self, call_sid: str) -> dict[str, Any] | None:
        try:
            response = httpx.get(
                f"{self.base_url}/v1/calls/{call_sid}",
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(str(exc)) from exc

        if response.status_code == 404:
            return None

        if response.status_code == 200:
            return response.json()

        raise ProviderError(
            f"Provider call lookup failed: HTTP {response.status_code}: "
            f"{response.text[:1000]}"
        )

    def get_clock(self) -> dict[str, Any]:
        try:
            response = httpx.get(
                f"{self.base_url}/v1/clock",
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(str(exc)) from exc


provider = ProviderClient()
