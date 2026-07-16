from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urljoin, urlsplit

import httpx
from protego import Protego
from sqlalchemy import select
from sqlalchemy.orm import Session

from atlas.config import Settings
from atlas.models import CrawlRun, DomainState, FrontierEntry
from atlas.urls import normalize_url, validate_fetch_target


@dataclass(frozen=True, slots=True)
class RobotsDecision:
    allowed: bool
    reason: str
    crawl_delay_ms: int


class RobotsService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def decide(
        self,
        session: Session,
        run: CrawlRun,
        entry: FrontierEntry,
        allowed_domains: list[tuple[str, bool]],
    ) -> RobotsDecision:
        state = session.scalar(
            select(DomainState).where(
                DomainState.run_id == run.id,
                DomainState.host == entry.host,
            )
        )
        if state is None:
            state = DomainState(run_id=run.id, host=entry.host)
            session.add(state)
            session.flush()

        now = datetime.now(UTC)
        if state.robots_expires_at is None or state.robots_expires_at <= now:
            self._refresh(state, run, entry, allowed_domains)
            session.flush()

        delay_ms = max(run.per_domain_delay_ms, state.crawl_delay_ms or 0)
        status = state.robots_status_code
        if state.robots_error:
            return RobotsDecision(False, f"robots_unavailable:{state.robots_error}", delay_ms)
        if status in {401, 403}:
            return RobotsDecision(False, f"robots_http_{status}", delay_ms)
        if status is not None and (status == 429 or status >= 500):
            return RobotsDecision(False, f"robots_temporary_http_{status}", delay_ms)
        if status is not None and 400 <= status < 500:
            return RobotsDecision(True, f"robots_unavailable_http_{status}", delay_ms)
        if not state.robots_body:
            return RobotsDecision(True, "robots_empty", delay_ms)

        policy = Protego.parse(state.robots_body)
        crawl_delay = policy.crawl_delay(run.user_agent)
        if crawl_delay is not None:
            delay_ms = max(delay_ms, int(float(crawl_delay) * 1000))
            state.crawl_delay_ms = delay_ms
        allowed = policy.can_fetch(entry.normalized_url, run.user_agent)
        return RobotsDecision(
            allowed, "robots_allowed" if allowed else "robots_disallowed", delay_ms
        )

    def _refresh(
        self,
        state: DomainState,
        run: CrawlRun,
        entry: FrontierEntry,
        allowed_domains: list[tuple[str, bool]],
    ) -> None:
        scheme = urlsplit(entry.normalized_url).scheme
        robots_url = f"{scheme}://{entry.host}/robots.txt"
        state.robots_url = robots_url
        state.robots_error = None
        state.robots_body = None
        state.robots_status_code = None
        now = datetime.now(UTC)

        try:
            timeout = httpx.Timeout(run.request_timeout_seconds)
            current_url = robots_url
            with httpx.Client(
                timeout=timeout,
                follow_redirects=False,
                headers={"User-Agent": run.user_agent, "Accept": "text/plain,*/*;q=0.1"},
            ) as client:
                for redirect_count in range(run.max_redirects + 1):
                    validated = validate_fetch_target(
                        current_url,
                        allowed_domains,
                        allow_private_networks=self.settings.allow_private_networks,
                    )
                    response = client.get(validated.url)
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location or redirect_count >= run.max_redirects:
                            raise RuntimeError("robots redirect policy failed")
                        current_url = normalize_url(urljoin(validated.url, location))
                        continue
                    if len(response.content) > 512_000:
                        raise RuntimeError("robots response exceeded 512 KB")
                    state.robots_url = str(response.url)
                    state.robots_status_code = response.status_code
                    state.robots_body = response.text if response.status_code < 400 else None
                    break
        except (httpx.HTTPError, RuntimeError, ValueError) as exc:
            state.robots_error = type(exc).__name__
            state.robots_expires_at = now + timedelta(minutes=15)
        else:
            state.robots_expires_at = now + timedelta(hours=self.settings.robots_cache_hours)

        state.robots_fetched_at = now
