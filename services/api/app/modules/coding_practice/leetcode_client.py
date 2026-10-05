from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx


ENDPOINT = "https://leetcode.com/graphql"
SUBMISSIONS_QUERY = """
query recentAcSubmissionList($username: String!) {
  recentAcSubmissionList(username: $username) { title titleSlug timestamp }
}
"""
PROBLEM_QUERY = """
query questionData($titleSlug: String!) {
  question(titleSlug: $titleSlug) { title titleSlug difficulty }
}
"""


class LeetCodeError(Exception):
    pass


class LeetCodeNetworkError(LeetCodeError):
    pass


class PrivateProfileError(LeetCodeError):
    pass


class EmptySubmissionError(LeetCodeError):
    pass


@dataclass
class _CacheEntry:
    expires_at: float
    submissions: list[dict[str, Any]]


class LeetCodeClient:
    def __init__(self, http_client: httpx.Client | None = None, cache_seconds: int = 180) -> None:
        self.http_client = http_client or httpx.Client(timeout=10.0)
        self.cache_seconds = cache_seconds
        self._cache: dict[str, _CacheEntry] = {}

    def _post(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json", "Referer": "https://leetcode.com/"}
        for attempt in range(2):
            try:
                response = self.http_client.post(ENDPOINT, json={"query": query, "variables": variables}, headers=headers)
                response.raise_for_status()
                payload = response.json()
                if payload.get("errors"):
                    raise LeetCodeError(str(payload["errors"]))
                return payload.get("data") or {}
            except (httpx.HTTPError, TimeoutError) as error:
                if attempt == 1:
                    raise LeetCodeNetworkError("LeetCode is temporarily unavailable") from error
                time.sleep(0.15)
        raise LeetCodeNetworkError("LeetCode is temporarily unavailable")

    def recent_accepted_submissions(self, username: str) -> list[dict[str, Any]]:
        key = username.strip().lower()
        cached = self._cache.get(key)
        if cached and cached.expires_at > time.monotonic():
            return list(cached.submissions)
        data = self._post(SUBMISSIONS_QUERY, {"username": username})
        if data.get("recentAcSubmissionList") is None:
            raise PrivateProfileError("This LeetCode profile is private or does not exist")
        submissions = data["recentAcSubmissionList"]
        if not submissions:
            raise EmptySubmissionError("This LeetCode profile has no recent accepted submissions")
        self._cache[key] = _CacheEntry(time.monotonic() + self.cache_seconds, list(submissions))
        return list(submissions)

    def problem(self, title_slug: str) -> dict[str, Any]:
        data = self._post(PROBLEM_QUERY, {"titleSlug": title_slug})
        problem = data.get("question")
        if not problem:
            raise LeetCodeError("LeetCode problem was not found")
        return problem
