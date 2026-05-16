from __future__ import annotations

from dataclasses import dataclass
from os import getenv
import base64


@dataclass(frozen=True)
class Settings:
    db_path: str
    gigachat_api_base: str
    gigachat_auth_url: str
    gigachat_client_id: str
    gigachat_client_secret: str
    gigachat_scope: str
    gigachat_model: str
    gigachat_verify_ssl: bool
    history_messages_limit: int


def get_settings() -> Settings:
    creds = getenv("GIGACHAT_CREDENTIALS", "").strip()
    client_id = ""
    client_secret = ""
    if creds:
        try:
            decoded = base64.b64decode(creds).decode("utf-8")
            if ":" in decoded:
                client_id, client_secret = decoded.split(":", 1)
        except Exception:
            pass

    if not client_id:
        client_id = getenv("GIGACHAT_CLIENT_ID", "").strip()
    if not client_secret:
        client_secret = getenv("GIGACHAT_CLIENT_SECRET", "").strip()

    return Settings(
        db_path=getenv("DB_PATH", "/data/app.db"),
        gigachat_api_base=getenv("GIGACHAT_API_BASE", "https://gigachat.devices.sberbank.ru/api/v1"),
        gigachat_auth_url=getenv("GIGACHAT_AUTH_URL", "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"),
        gigachat_client_id=client_id,
        gigachat_client_secret=client_secret,
        gigachat_scope=getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS"),
        gigachat_model=getenv("GIGACHAT_MODEL", "GigaChat"),
        gigachat_verify_ssl=getenv("GIGACHAT_VERIFY_SSL", "1").strip() not in ("0", "false", "False", "no", "NO"),
        history_messages_limit=int(getenv("HISTORY_MESSAGES_LIMIT", "24")),
    )