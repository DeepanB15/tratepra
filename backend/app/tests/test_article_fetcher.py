
from unittest.mock import patch

from app.ingestion.article_fetcher import (
    _public_http_url,
    fetch_article,
)


def test_rejects_non_http_url():
    assert _public_http_url("file:///etc/passwd") is False


def test_rejects_localhost():
    assert _public_http_url("http://localhost/article") is False
    assert _public_http_url("http://127.0.0.1/article") is False


def test_rejects_private_ip():
    assert _public_http_url("http://192.168.1.10/article") is False


def test_rejects_credentials_in_url():
    assert (
        _public_http_url("https://user:pass@example.com/article")
        is False
    )


def test_rejects_redirect_to_private_address():
    with patch(
        "app.ingestion.article_fetcher._public_http_url",
        side_effect=[True, False],
    ):
        with patch(
            "app.ingestion.article_fetcher.httpx.Client"
        ) as client_class:
            client = client_class.return_value.__enter__.return_value
            response = client.stream.return_value.__enter__.return_value
            response.status_code = 302
            response.headers = {
                "location": "http://127.0.0.1/private"
            }

            assert fetch_article("https://example.com/article") is None
