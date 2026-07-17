from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from protego import Protego
from sqlalchemy import select
from sqlalchemy.orm import Session

from atlas.config import Settings
from atlas.fetcher import FetchNetworkError, FetchTimeoutError, fetch_url
from atlas.models import CrawlRun, DomainState, FrontierEntry


@dataclass(frozen=True, slots=True)
class RobotsDecision:
    allowed: bool
    reason: str
    crawl_delay_ms: int
    sitemaps: tuple[str, ...] = ()


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
            allowed,
            "robots_allowed" if allowed else "robots_disallowed",
            delay_ms,
            tuple(policy.sitemaps),
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
            response = fetch_url(
                run,
                robots_url,
                allowed_domains,
                allow_private_networks=self.settings.allow_private_networks,
                accept="text/plain,*/*;q=0.1",
                max_response_bytes=512_000,
            )
            state.robots_url = response.final_url
            state.robots_status_code = response.status_code
            state.robots_body = (
                response.body.decode("utf-8", errors="replace")
                if response.status_code < 400
                else None
            )
        except (FetchNetworkError, FetchTimeoutError, RuntimeError, ValueError) as exc:
            state.robots_error = type(exc).__name__
            state.robots_expires_at = now + timedelta(minutes=15)
        else:
            state.robots_expires_at = now + timedelta(hours=self.settings.robots_cache_hours)

        state.robots_fetched_at = now
