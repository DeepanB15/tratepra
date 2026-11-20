
"""Bounded HTTP retrieval for optional article enrichment.

RSS records remain valid when fetching or extraction fails.
Redirects are followed manually and each destination is validated.
"""
import ipaddress
import logging
import socket
from urllib.parse import urljoin, urlparse

import httpx

from app.ingestion.article_extractor import extract_article

log = logging.getLogger(__name__)

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
FETCH_TIMEOUT_SECONDS = 8.0
MAX_REDIRECTS = 3
USER_AGENT = "TratepraResearch/1.0"

REDIRECT_CODES = {301, 302, 303, 307, 308}


def _public_http_url(url: str) -> bool:
    try:
        parsed = urlparse(url)

        if parsed.scheme not in {"http", "https"}:
            return False
        if not parsed.hostname or parsed.username or parsed.password:
            return False

        host = parsed.hostname.lower()

        if (
            host == "localhost"
            or host.endswith(".localhost")
            or host.endswith(".local")
        ):
            return False

        port = parsed.port or (443 if parsed.scheme == "https" else 80)

        try:
            addresses = {ipaddress.ip_address(host)}
        except ValueError:
            addresses = {
                ipaddress.ip_address(item[4][0])
                for item in socket.getaddrinfo(
                    host, port, type=socket.SOCK_STREAM
                )
            }

        return bool(addresses) and all(
            address.is_global for address in addresses
        )

    except (ValueError, OSError, socket.gaierror):
        return False


def fetch_article(url: str):
    """Fetch and extract an article using bounded, validated redirects."""
    current_url = url

    try:
        with httpx.Client(
            timeout=FETCH_TIMEOUT_SECONDS,
            follow_redirects=False,
            trust_env=False,
            headers={"User-Agent": USER_AGENT},
        ) as client:

            for redirect_count in range(MAX_REDIRECTS + 1):
                if not _public_http_url(current_url):
                    return None

                with client.stream("GET", current_url) as response:

                    if response.status_code in REDIRECT_CODES:
                        if redirect_count >= MAX_REDIRECTS:
                            return None

                        location = response.headers.get("location")
                        if not location:
                            return None

                        next_url = urljoin(current_url, location)

                        if not _public_http_url(next_url):
                            return None

                        current_url = next_url
                        continue

                    if response.status_code != 200:
                        return None

                    content_type = response.headers.get(
                        "content-type", ""
                    ).lower()

                    if "text/html" not in content_type:
                        return None

                    chunks = []
                    total = 0

                    for chunk in response.iter_bytes():
                        total += len(chunk)

                        if total > MAX_RESPONSE_BYTES:
                            return None

                        chunks.append(chunk)

                    result = extract_article(b"".join(chunks))

                    if result.status == "extracted":
                        return result

                    return None

    except (httpx.HTTPError, OSError, ValueError):
        log.info(
            "Article fetch failed for %s",
            current_url,
            exc_info=True,
        )

    return None
