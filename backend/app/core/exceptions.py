import hmac

from fastapi import Header, HTTPException

from app.core.config import get_settings


class ConnectorError(Exception):
    """Raised by connectors for provider failures. Recorded, never silently hidden."""

    def __init__(self, source: str, message: str, kind: str = "error"):
        super().__init__(message)
        self.source = source
        self.message = message
        self.kind = kind  # error | quota | rate_limit | unavailable | auth


class ConnectorUnavailable(ConnectorError):
    def __init__(self, source: str, message: str):
        super().__init__(source, message, kind="unavailable")


def require_internal_token(x_internal_token: str = Header(default="")) -> None:
    if not hmac.compare_digest(x_internal_token.encode(), get_settings().internal_api_token.encode()):
        raise HTTPException(status_code=401, detail="Invalid internal token")
