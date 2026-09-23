"""Lightweight GitHub enrichment via the public API.

Scoring: 0-5 for recent activity + 0-5 for maintained/relevant repos (capped
at 10 by the rubric). Failures (rate limit, private profile, network) never
fail the batch — they record a status string instead.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import httpx

from ..config import Settings
from ..models import GitHubEnrichment

API = "https://api.github.com"
RECENT_DAYS = 90

_PY_AI_TOPICS = {
    "python", "machine-learning", "ml", "ai", "llm", "rag", "langchain",
    "langgraph", "nlp", "deep-learning", "pytorch", "fastapi", "data-science",
}


def extract_username(github_url: str | None) -> str | None:
    if not github_url:
        return None
    parsed = urlparse(github_url)
    host = (parsed.netloc or "").lower()
    if host and host != "github.com" and not host.endswith(".github.com"):
        return None  # gitlab.com/bitbucket.io etc. are not GitHub profiles
    path = parsed.path.strip("/")
    username = path.split("/")[0] if path else None
    return username or None


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _headers(settings: Settings) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "resume-screener/1.0",
    }
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    return headers


# The /rate_limit endpoint itself does not count against the quota.
_rate_budget: dict[str, int] = {"remaining": 999}


def _refresh_rate_budget(client: httpx.Client) -> int:
    """Update cached quota from the free /rate_limit endpoint (best effort)."""
    try:
        resp = client.get(f"{API}/rate_limit")
        core = resp.json().get("resources", {}).get("core", {})
        _rate_budget["remaining"] = int(core.get("remaining", 0))
    except Exception:  # noqa: BLE001 — budget check must never break enrichment
        pass
    return _rate_budget["remaining"]


def _rate_budget_ok(client: httpx.Client, needed: int = 2) -> bool:
    """Only spend quota we know we have (each username needs 1-2 calls)."""
    remaining = _rate_budget["remaining"]
    if remaining >= needed:
        return True
    return _refresh_rate_budget(client) >= needed


def _activity_score(events: list[dict], repos: list[dict]) -> tuple[int, list[str]]:
    """0-5 from recent public events + recently pushed repos."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=RECENT_DAYS)
    recent_events = [
        e for e in events
        if (_parse_dt(e.get("created_at")) or now.replace(year=2000)) >= cutoff
    ]
    recent_repos = [
        r for r in repos
        if (_parse_dt(r.get("pushed_at")) or now.replace(year=2000)) >= cutoff
    ]
    notes: list[str] = []
    score = 0
    if recent_events:
        score += 3 if len(recent_events) >= 30 else (2 if len(recent_events) >= 10 else 1)
        notes.append(f"{len(recent_events)} public events in last {RECENT_DAYS}d")
    if recent_repos:
        score += 2 if len(recent_repos) >= 3 else 1
        notes.append(f"{len(recent_repos)} repos pushed in last {RECENT_DAYS}d")
    if not notes:
        notes.append("no recent public activity")
    return min(5, score), notes


def _repo_score(repos: list[dict]) -> tuple[int, list[str]]:
    """0-5 from maintained + Python/AI-relevant public repos."""
    now = datetime.now(timezone.utc)
    year_ago = now - timedelta(days=365)
    maintained = [
        r for r in repos
        if not r.get("fork")
        and (_parse_dt(r.get("pushed_at")) or now.replace(year=2000)) >= year_ago
    ]
    relevant = [
        r for r in maintained
        if (r.get("language") or "").lower() == "python"
        or bool(_PY_AI_TOPICS.intersection({t.lower() for t in r.get("topics", [])}))
        or any(k in (r.get("description") or "").lower()
               for k in ("ai", "llm", "rag", "agent", "ml"))
    ]
    score = 0
    score += 3 if len(maintained) >= 5 else (2 if len(maintained) >= 2 else (1 if maintained else 0))
    score += 2 if len(relevant) >= 3 else (1 if relevant else 0)
    notes = [
        f"{len(maintained)} maintained repos ({len(relevant)} Python/AI relevant)",
    ]
    return min(5, score), notes


def enrich_single(github_url: str | None, settings: Settings) -> GitHubEnrichment:
    """Fetch profile + repos + events for one candidate. Never raises."""
    username = extract_username(github_url)
    if not username:
        return GitHubEnrichment(status="no_username")
    if not settings.github_enabled:
        return GitHubEnrichment(username=username, status="disabled")

    headers = _headers(settings)
    timeout = settings.github_timeout
    try:
        with httpx.Client(headers=headers, timeout=timeout, follow_redirects=True) as client:
            # Preflight: skip cleanly instead of burning 403s when out of quota.
            if not _rate_budget_ok(client, needed=1):
                return GitHubEnrichment(
                    username=username, status="rate_limited",
                    summary="GitHub API rate limit exhausted; enrichment skipped.",
                )

            # Call 1 (required): repos give activity + relevance signals.
            repos_resp = client.get(
                f"{API}/users/{username}/repos",
                params={"per_page": 100, "sort": "pushed"},
            )
            if repos_resp.status_code == 404:
                return GitHubEnrichment(username=username, status="not_found",
                                        summary="GitHub profile not found (private or typo).")
            if repos_resp.status_code in (403, 429):
                _rate_budget["remaining"] = 0
                return GitHubEnrichment(username=username, status="rate_limited",
                                        summary="GitHub API rate limited; enrichment skipped.")
            repos_resp.raise_for_status()
            repos = repos_resp.json()
            if isinstance(repos, dict):  # error payload shape
                repos = []

            # Call 2 (optional): public events refine recency. Skipped when
            # only 1 request of budget remains — repos alone still score.
            rate_limited_midway = False
            events: list = []
            if _rate_budget_ok(client, needed=1):
                events_resp = client.get(
                    f"{API}/users/{username}/events/public", params={"per_page": 100}
                )
                rate_limited_midway = events_resp.status_code in (403, 429)
                events = events_resp.json() if events_resp.status_code == 200 else []
                if isinstance(events, dict):
                    events = []
            else:
                rate_limited_midway = True  # note: events skipped for budget
            if rate_limited_midway:
                _rate_budget["remaining"] = 0

            # Derive profile stats from the same payload (saves a 3rd call).
            profile = {
                "public_repos": len(repos),
                "bio": None,
            }
    except httpx.HTTPError as exc:
        return GitHubEnrichment(username=username, status="error",
                                summary=f"GitHub API request failed: {type(exc).__name__}")
    except (ValueError, TypeError, KeyError) as exc:
        return GitHubEnrichment(username=username, status="error",
                                summary=f"Unexpected GitHub payload: {type(exc).__name__}")

    activity, activity_notes = _activity_score(events, repos)
    repo_points, repo_notes = _repo_score(repos)
    summary_parts = activity_notes + repo_notes
    if rate_limited_midway:
        summary_parts.append("events API rate-limited; activity may be understated")

    summary = f"@{username}: " + "; ".join(summary_parts)
    if profile.get("bio"):
        summary += f" | bio: {profile['bio'][:80]}"

    return GitHubEnrichment(
        username=username,
        status="ok",
        activity_score=activity,
        repo_score=repo_points,
        summary=summary,
        detail={
            "public_repos": profile.get("public_repos"),
            "followers": profile.get("followers"),
            "created_at": profile.get("created_at"),
        },
    )


def enrich_batch(
    urls: dict[str, str | None], settings: Settings
) -> dict[str, GitHubEnrichment]:
    """Enrich many candidates with bounded concurrency. Never raises.

    ``urls`` maps candidate key -> github url (may be None).
    Identical usernames are fetched once and reused (memoized), which keeps a
    50-resume batch well inside unauthenticated rate limits.
    """
    if not settings.github_enabled:
        return {
            key: GitHubEnrichment(status="disabled") for key in urls
        }

    # Group candidate keys by username so each unique profile is fetched once.
    by_username: dict[str, list[str]] = {}
    key_username: dict[str, str | None] = {}
    for key, url in urls.items():
        username = extract_username(url)
        key_username[key] = username
        if username:
            by_username.setdefault(username, []).append(key)

    unique_results: dict[str, GitHubEnrichment] = {}
    usernames = sorted(by_username)
    with ThreadPoolExecutor(max_workers=min(settings.max_workers, 4)) as pool:
        future_to_user = {
            pool.submit(
                enrich_single, f"https://github.com/{username}", settings
            ): username
            for username in usernames
        }
        for future, username in future_to_user.items():
            try:
                unique_results[username] = future.result(
                    timeout=settings.github_timeout + 15
                )
            except Exception as exc:  # noqa: BLE001 — isolation by design
                unique_results[username] = GitHubEnrichment(
                    username=username, status="error",
                    summary=f"enrichment crashed: {type(exc).__name__}",
                )
            time.sleep(0.2)  # stay gentle on unauthenticated rate limits

    # Fan the unique results back out to every candidate key.
    return {
        key: (
            unique_results[key_username[key]]
            if key_username[key]
            else GitHubEnrichment(status="no_username")
        )
        for key in urls
    }
