from typing import cast

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from atlas.config import Settings
from atlas.fetcher import FetchNetworkError, FetchResult
from atlas.models import CrawlRun, DomainState, FrontierEntry
from atlas.robots import RobotsService
from atlas.schemas import AllowedDomainInput, CrawlRunCreate
from atlas.services.runs import create_run


def _run_entry(session: Session) -> tuple[CrawlRun, FrontierEntry]:
    run = create_run(
        session,
        CrawlRunCreate(
            name="robots",
            seeds=["https://example.com/private/page"],
            allowed_domains=[AllowedDomainInput(domain="example.com", include_subdomains=False)],
        ),
        commit=False,
    )
    session.commit()
    entry = session.scalar(select(FrontierEntry).where(FrontierEntry.run_id == run.id))
    assert entry is not None
    return run, entry


def _result(body: str, status: int = 200) -> FetchResult:
    return FetchResult(
        status_code=status,
        final_url="https://example.com/robots.txt",
        headers={},
        body=body.encode(),
        content_type="text/plain",
        latency_ms=1,
        redirect_chain=[],
        request_headers={},
    )


def test_robots_policy_is_cached_and_exposes_sitemaps(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    run, entry = _run_entry(db_session)
    calls = 0

    def fetch(*_args: object, **_kwargs: object) -> FetchResult:
        nonlocal calls
        calls += 1
        return _result(
            "User-agent: *\nDisallow: /private\nCrawl-delay: 2\n"
            "Sitemap: https://example.com/sitemap.xml\n"
        )

    monkeypatch.setattr("atlas.robots.fetch_url", fetch)
    service = RobotsService(Settings())

    first = service.decide(db_session, run, entry, [("example.com", False)])
    second = service.decide(db_session, run, entry, [("example.com", False)])

    assert not first.allowed
    assert first.reason == "robots_disallowed"
    assert first.crawl_delay_ms == 2000
    assert first.sitemaps == ("https://example.com/sitemap.xml",)
    assert second == first
    assert calls == 1


@pytest.mark.parametrize(
    ("status", "allowed", "reason"),
    [
        (404, True, "robots_unavailable_http_404"),
        (401, False, "robots_http_401"),
        (503, False, "robots_temporary_http_503"),
    ],
)
def test_robots_http_fail_closed_rules(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    allowed: bool,
    reason: str,
) -> None:
    run, entry = _run_entry(db_session)

    def fetch(
        _run: CrawlRun,
        _url: str,
        _domains: list[tuple[str, bool]],
        **_kwargs: object,
    ) -> FetchResult:
        return _result("", status)

    monkeypatch.setattr("atlas.robots.fetch_url", fetch)

    decision = RobotsService(Settings()).decide(db_session, run, entry, [("example.com", False)])

    assert decision.allowed is allowed
    assert decision.reason == reason


def test_robots_network_error_is_temporarily_unavailable(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    run, entry = _run_entry(db_session)

    def fail(*_args: object, **_kwargs: object) -> FetchResult:
        raise FetchNetworkError("offline")

    monkeypatch.setattr("atlas.robots.fetch_url", fail)

    decision = RobotsService(Settings()).decide(db_session, run, entry, [("example.com", False)])
    state = cast(
        DomainState,
        db_session.scalar(select(DomainState).where(DomainState.run_id == run.id)),
    )

    assert not decision.allowed
    assert decision.reason == "robots_unavailable:FetchNetworkError"
    assert state.robots_expires_at is not None
