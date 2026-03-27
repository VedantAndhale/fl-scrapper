from __future__ import annotations

import random
import time
from typing import Optional

import requests
from requests import Response
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import (
    REQUEST_BACKOFF_SECONDS,
    REQUEST_JITTER_RANGE_SECONDS,
    REQUEST_RETRIES,
    REQUEST_TIMEOUT_SECONDS,
    USER_AGENT,
)


class HttpClient:
    def __init__(self) -> None:
        self.session = requests.Session()
        retry = Retry(
            total=REQUEST_RETRIES,
            read=REQUEST_RETRIES,
            connect=REQUEST_RETRIES,
            backoff_factor=REQUEST_BACKOFF_SECONDS,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET", "HEAD"),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=32, pool_maxsize=32)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/json,application/xhtml+xml,*/*",
                "Accept-Language": "en-US,en;q=0.9",
                "Connection": "keep-alive",
            }
        )

    def get(self, url: str, timeout: Optional[float] = None) -> Response:
        self._pace()
        return self.session.get(url, timeout=timeout or REQUEST_TIMEOUT_SECONDS)

    @staticmethod
    def _pace() -> None:
        low, high = REQUEST_JITTER_RANGE_SECONDS
        time.sleep(random.uniform(low, high))
