"""Async client for the official ClinicalTrials.gov API v2 (https://clinicaltrials.gov/data-api/api).

Verified against the live API (version 2.0.5) on 2026-11-06:
  GET /studies          query.cond, query.term, query.intr, filter.overallStatus (pipe-separated),
                        filter.geo=distance(lat,lon,Nmi), pageSize (<=1000), pageToken, countTotal
                        -> {"studies": [...], "nextPageToken": str?, "totalCount": int?}
  GET /studies/{nctId}  -> study, 404 "NCT number ... not found", 400 for malformed ids
  GET /version          -> {"apiVersion", "dataTimestamp"}

Failure handling: a client-side rate limiter keeps us under the documented per-IP limit; 429 and
5xx responses and network errors are retried with exponential backoff (honoring Retry-After).
When retries are exhausted we raise CTGovUnavailable; callers must surface that explicitly and
never substitute invented data.
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field

import httpx

from app.core.config import get_settings

NCT_RE = re.compile(r"^NCT\d{8}$")
VALID_STATUSES = {
    "ACTIVE_NOT_RECRUITING", "COMPLETED", "ENROLLING_BY_INVITATION", "NOT_YET_RECRUITING", "RECRUITING",
    "SUSPENDED", "TERMINATED", "WITHDRAWN", "AVAILABLE", "NO_LONGER_AVAILABLE", "TEMPORARILY_NOT_AVAILABLE",
    "APPROVED_FOR_MARKETING", "WITHHELD", "UNKNOWN",
}


class CTGovError(Exception):
    pass


class InvalidNCTId(CTGovError):
    pass


class StudyNotFound(CTGovError):
    pass


class CTGovUnavailable(CTGovError):
    """Live data could not be retrieved (network failure, repeated 5xx, or rate limiting)."""


class _RateLimiter:
    def __init__(self, per_minute: int):
        self.interval = 60.0 / max(per_minute, 1)
        self._lock = asyncio.Lock()
        self._next = 0.0

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            if self._next > now:
                await asyncio.sleep(self._next - now)
            self._next = max(now, self._next) + self.interval


@dataclass
class SearchPage:
    studies: list[dict]
    next_page_token: str | None
    total_count: int | None


@dataclass
class SearchResult:
    studies: list[dict] = field(default_factory=list)
    total_count: int | None = None
    pages_fetched: int = 0


def validate_nct_id(nct_id: str) -> str:
    nct = nct_id.strip().upper()
    if not NCT_RE.match(nct):
        raise InvalidNCTId(f"'{nct_id}' is not a valid NCT identifier (expected NCT followed by 8 digits)")
    return nct


class ClinicalTrialsClient:
    def __init__(self, http: httpx.AsyncClient | None = None, *, base_url: str | None = None,
                 max_retries: int | None = None, requests_per_minute: int | None = None,
                 backoff_base: float = 1.0):
        s = get_settings()
        self.base_url = (base_url or s.ctgov_base_url).rstrip("/")
        self.max_retries = s.ctgov_max_retries if max_retries is None else max_retries
        self.backoff_base = backoff_base
        self._own_http = http is None
        self.http = http or httpx.AsyncClient(
            timeout=s.ctgov_timeout_seconds,
            headers={"Accept": "application/json", "User-Agent": "TrialMatchAI/0.1"},
        )
        self._limiter = _RateLimiter(requests_per_minute or s.ctgov_requests_per_minute)

    async def aclose(self) -> None:
        if self._own_http:
            await self.http.aclose()

    async def _get(self, path: str, params: dict | None = None) -> httpx.Response:
        url = f"{self.base_url}{path}"
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            await self._limiter.wait()
            try:
                resp = await self.http.get(url, params=params)
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_exc = exc
            else:
                if resp.status_code < 400 or resp.status_code in (400, 404):
                    return resp
                if resp.status_code == 429 or resp.status_code >= 500:
                    last_exc = CTGovUnavailable(f"ClinicalTrials.gov returned HTTP {resp.status_code}")
                    if attempt < self.max_retries:
                        await asyncio.sleep(self._retry_delay(resp, attempt))
                        continue
                    break
                raise CTGovError(f"Unexpected HTTP {resp.status_code} from ClinicalTrials.gov")
            if attempt < self.max_retries:
                await asyncio.sleep(self.backoff_base * (2 ** attempt))
        raise CTGovUnavailable(
            "Live clinical trial data could not be retrieved from ClinicalTrials.gov. "
            f"Reason: {type(last_exc).__name__}: {last_exc}"
        )

    def _retry_delay(self, resp: httpx.Response, attempt: int) -> float:
        ra = resp.headers.get("Retry-After")
        if ra and ra.isdigit():
            return min(float(ra), 30.0)
        return self.backoff_base * (2 ** attempt)

    async def version(self) -> dict:
        resp = await self._get("/version")
        return resp.json()

    async def get_study(self, nct_id: str) -> dict:
        nct = validate_nct_id(nct_id)
        resp = await self._get(f"/studies/{nct}")
        if resp.status_code == 404:
            raise StudyNotFound(f"{nct} was not found on ClinicalTrials.gov")
        if resp.status_code == 400:
            raise InvalidNCTId(resp.text[:200])
        return resp.json()

    async def search_page(self, *, condition: str | None = None, term: str | None = None,
                          intervention: str | None = None, statuses: list[str] | None = None,
                          geo: tuple[float, float, int] | None = None, page_size: int = 50,
                          page_token: str | None = None, count_total: bool = True) -> SearchPage:
        params: dict[str, str | int] = {"pageSize": min(max(page_size, 1), 1000), "format": "json"}
        if condition:
            params["query.cond"] = condition
        if term:
            params["query.term"] = term
        if intervention:
            params["query.intr"] = intervention
        if statuses:
            bad = [s for s in statuses if s not in VALID_STATUSES]
            if bad:
                raise CTGovError(f"Unknown recruitment status filter(s): {bad}")
            params["filter.overallStatus"] = "|".join(statuses)
        if geo:
            lat, lon, miles = geo
            params["filter.geo"] = f"distance({lat:.4f},{lon:.4f},{int(miles)}mi)"
        if page_token:
            params["pageToken"] = page_token
        if count_total:
            params["countTotal"] = "true"
        if not any(k.startswith("query.") for k in params):
            raise CTGovError("At least one of condition, term or intervention is required")
        resp = await self._get("/studies", params)
        if resp.status_code == 400:
            raise CTGovError(f"ClinicalTrials.gov rejected the query: {resp.text[:200]}")
        data = resp.json()
        return SearchPage(
            studies=data.get("studies", []),
            next_page_token=data.get("nextPageToken"),
            total_count=data.get("totalCount"),
        )

    async def search(self, *, max_results: int = 50, page_size: int = 50, **kwargs) -> SearchResult:
        """Paginate with nextPageToken until max_results studies are collected or pages run out."""
        result = SearchResult()
        token: str | None = None
        while len(result.studies) < max_results:
            page = await self.search_page(page_size=min(page_size, max_results - len(result.studies)),
                                          page_token=token, count_total=result.pages_fetched == 0, **kwargs)
            result.pages_fetched += 1
            if result.pages_fetched == 1:
                result.total_count = page.total_count
            result.studies.extend(page.studies)
            token = page.next_page_token
            if not token or not page.studies:
                break
        result.studies = result.studies[:max_results]
        return result
