from __future__ import annotations

import time
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/154.0 Safari/537.36 "
    "vpn-blocked-apps-tracker/2.0"
)


def build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=0.8,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "HEAD"}),
        respect_retry_after_header=True,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    session.headers.update({"User-Agent": DEFAULT_UA, "Accept-Language": "ru,en;q=0.7"})
    return session


def fetch_text(session: requests.Session, url: str, timeout: int = 20) -> tuple[str, str]:
    response = session.get(url, timeout=timeout, allow_redirects=True)
    response.raise_for_status()
    return response.url, response.text


def domain_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


class PoliteDelay:
    def __init__(self, seconds: float = 0.7):
        self.seconds = max(0.0, seconds)
        self._last = 0.0

    def wait(self) -> None:
        if not self.seconds:
            return
        now = time.monotonic()
        remaining = self.seconds - (now - self._last)
        if remaining > 0:
            time.sleep(remaining)
        self._last = time.monotonic()
