from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import uuid4

import httpx


@dataclass
class Token:
    access_token: str
    expires_at: datetime

    def is_valid(self) -> bool:
        return datetime.now(timezone.utc) < self.expires_at


class GigaChatClient:
    def __init__(
        self,
        *,
        api_base: str,
        auth_url: str,
        client_id: str,
        client_secret: str,
        scope: str,
        model: str,
        verify_ssl: bool = True,
    ) -> None:
        self._api_base = api_base.rstrip("/")
        self._auth_url = auth_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._scope = scope
        self._model = model
        self._verify_ssl = verify_ssl
        self._token: Optional[Token] = None

    async def _get_token(self) -> str:
        if self._token and self._token.is_valid():
            return self._token.access_token

        basic = base64.b64encode(f"{self._client_id}:{self._client_secret}".encode("utf-8")).decode("ascii")
        headers = {
            "Authorization": f"Basic {basic}",
            "RqUID": str(uuid4()),
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }
        data = {"scope": self._scope, "grant_type": "client_credentials"}

        async with httpx.AsyncClient(timeout=30.0, verify=self._verify_ssl) as client:
            resp = await client.post(self._auth_url, headers=headers, data=data)
            resp.raise_for_status()
            payload = resp.json()

        access_token = payload.get("access_token") or payload.get("accessToken")
        expires_in = payload.get("expires_in") or payload.get("expiresIn") or 1800
        if not access_token:
            raise RuntimeError("Не удалось получить access_token от GigaChat OAuth")

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in) - 30)
        self._token = Token(access_token=access_token, expires_at=expires_at)
        return access_token

    async def chat(self, messages: list[dict[str, Any]]) -> str:
        token = await self._get_token()
        url = f"{self._api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "RqUID": str(uuid4()),
        }
        body = {"model": self._model, "messages": messages, "stream": False}

        async with httpx.AsyncClient(timeout=60.0, verify=self._verify_ssl) as client:
            resp = await client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            payload = resp.json()

        try:
            return payload["choices"][0]["message"]["content"]
        except Exception as e:
            raise RuntimeError(f"Неожиданный ответ GigaChat: {payload}") from e