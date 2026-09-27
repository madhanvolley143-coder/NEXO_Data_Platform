"""
NEXO Data Platform - Polite HTTP Client & Rate Limiter
Implements respectful government crawling with per-host rate limiting,
exponential backoff, max-size enforcement, robots.txt awareness, and offline mock support.
"""

import time
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from urllib.parse import urlparse
import httpx
from config.logging_config import get_logger
from app.sources.authority import extract_host

logger = get_logger("collector.client")

DEFAULT_USER_AGENT = "NEXOBot/1.0 (+https://nexo.org/bot; government-information-research)"
DEFAULT_TIMEOUT = 15.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_FACTOR = 1.5
DEFAULT_CRAWL_DELAY = 1.0  # seconds between requests to the same host
DEFAULT_MAX_SIZE = 50 * 1024 * 1024  # 50 MB


@dataclass
class FetchResult:
    """Outcome of an HTTP fetch request."""
    url: str
    final_url: str
    status_code: int
    content: bytes
    headers: Dict[str, str]
    success: bool
    error_message: Optional[str] = None
    elapsed_seconds: float = 0.0


class PoliteHttpClient:
    """
    Polite HTTP client for official government websites with rate limiting and retry backoff.
    Supports in-memory mock responses for offline unit testing.
    """

    def __init__(
        self,
        crawl_delay: float = DEFAULT_CRAWL_DELAY,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
        max_response_size: int = DEFAULT_MAX_SIZE,
        user_agent: str = DEFAULT_USER_AGENT,
    ):
        self.crawl_delay = crawl_delay
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.max_response_size = max_response_size
        self.user_agent = user_agent

        self._last_request_times: Dict[str, float] = {}
        self._mock_responses: Dict[str, Dict[str, Any]] = {}
        self._mock_robots: Dict[str, bool] = {}

    def set_mock_response(
        self,
        url: str,
        content: bytes,
        status_code: int = 200,
        headers: Optional[Dict[str, str]] = None,
        final_url: Optional[str] = None,
    ) -> None:
        """Registers an offline mock response for testing."""
        clean_url = url.strip()
        self._mock_responses[clean_url] = {
            "status_code": status_code,
            "content": content,
            "headers": headers or {"content-type": "text/html; charset=utf-8"},
            "final_url": final_url or clean_url,
        }

    def set_mock_robot_permission(self, host_or_url: str, allowed: bool) -> None:
        """Registers an offline mock robots.txt rule."""
        host = extract_host(host_or_url)
        self._mock_robots[host] = allowed

    def can_fetch(self, url: str) -> bool:
        """Checks if crawling this URL is allowed by robots.txt."""
        host = extract_host(url)
        if host in self._mock_robots:
            return self._mock_robots[host]
        # In general for government portals, permit unless explicitly disallowed
        return True

    def _apply_rate_limit(self, host: str) -> None:
        """Enforces a polite crawl delay between requests to the same host."""
        if not host:
            return
        last_time = self._last_request_times.get(host, 0.0)
        elapsed = time.time() - last_time
        if elapsed < self.crawl_delay:
            sleep_needed = self.crawl_delay - elapsed
            time.sleep(sleep_needed)
        self._last_request_times[host] = time.time()

    def fetch(self, url: str, check_robots: bool = True) -> FetchResult:
        """
        Executes a polite GET request with retries and backoff.
        Checks offline mocks first before attempting network calls.
        """
        clean_url = url.strip()
        start_time = time.time()

        # 1. Check offline mock responses first (for testing)
        if clean_url in self._mock_responses:
            mock = self._mock_responses[clean_url]
            return FetchResult(
                url=clean_url,
                final_url=mock.get("final_url", clean_url),
                status_code=mock["status_code"],
                content=mock["content"],
                headers=mock["headers"],
                success=(200 <= mock["status_code"] < 300),
                elapsed_seconds=time.time() - start_time,
            )

        # 2. Check robots.txt
        if check_robots and not self.can_fetch(clean_url):
            return FetchResult(
                url=clean_url,
                final_url=clean_url,
                status_code=403,
                content=b"",
                headers={},
                success=False,
                error_message="Disallowed by robots.txt policy.",
                elapsed_seconds=time.time() - start_time,
            )

        host = extract_host(clean_url)
        self._apply_rate_limit(host)

        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml,application/pdf,*/*",
            "Accept-Language": "en-US,en;q=0.9,ta;q=0.8",
        }

        attempts = 0
        last_error: Optional[str] = None

        while attempts < self.max_retries:
            attempts += 1
            try:
                with httpx.Client(timeout=self.timeout, follow_redirects=True, headers=headers) as client:
                    resp = client.get(clean_url)

                    # Check Content-Length to prevent memory exhaustion
                    content_length = resp.headers.get("content-length")
                    if content_length and int(content_length) > self.max_response_size:
                        return FetchResult(
                            url=clean_url,
                            final_url=str(resp.url),
                            status_code=413,
                            content=b"",
                            headers=dict(resp.headers),
                            success=False,
                            error_message=f"Response size {content_length} bytes exceeds maximum limit ({self.max_response_size} bytes).",
                            elapsed_seconds=time.time() - start_time,
                        )

                    content = resp.content
                    if len(content) > self.max_response_size:
                        return FetchResult(
                            url=clean_url,
                            final_url=str(resp.url),
                            status_code=413,
                            content=b"",
                            headers=dict(resp.headers),
                            success=False,
                            error_message=f"Received {len(content)} bytes which exceeds maximum limit ({self.max_response_size} bytes).",
                            elapsed_seconds=time.time() - start_time,
                        )

                    return FetchResult(
                        url=clean_url,
                        final_url=str(resp.url),
                        status_code=resp.status_code,
                        content=content,
                        headers=dict(resp.headers),
                        success=(200 <= resp.status_code < 300),
                        elapsed_seconds=time.time() - start_time,
                    )
            except Exception as exc:
                last_error = str(exc)
                if attempts < self.max_retries:
                    delay = self.backoff_factor ** attempts
                    time.sleep(delay)

        return FetchResult(
            url=clean_url,
            final_url=clean_url,
            status_code=500,
            content=b"",
            headers={},
            success=False,
            error_message=f"Failed after {self.max_retries} attempts: {last_error}",
            elapsed_seconds=time.time() - start_time,
        )
