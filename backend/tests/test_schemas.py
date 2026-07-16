import pytest
from pydantic import ValidationError

from atlas.schemas import AllowedDomainInput, CrawlRunCreate


def test_run_configuration_accepts_safe_bounded_values() -> None:
    request = CrawlRunCreate(
        name="Docs crawl",
        seeds=["https://example.com/docs"],
        allowed_domains=[AllowedDomainInput(domain="example.com")],
        max_pages=500,
        max_depth=3,
    )

    assert request.max_pages == 500
    assert request.per_domain_delay_ms == 1000


def test_run_configuration_rejects_duplicate_seeds() -> None:
    with pytest.raises(ValidationError, match="Seed URLs must be unique"):
        CrawlRunCreate(
            name="Duplicate seeds",
            seeds=["https://example.com", "https://example.com"],
            allowed_domains=[AllowedDomainInput(domain="example.com")],
        )


def test_run_configuration_enforces_politeness_floor() -> None:
    with pytest.raises(ValidationError):
        CrawlRunCreate(
            name="Too fast",
            seeds=["https://example.com"],
            allowed_domains=[AllowedDomainInput(domain="example.com")],
            per_domain_delay_ms=10,
        )


def test_run_configuration_rejects_blank_name() -> None:
    with pytest.raises(ValidationError, match="Run name cannot be blank"):
        CrawlRunCreate(
            name="   ",
            seeds=["https://example.com"],
            allowed_domains=[AllowedDomainInput(domain="example.com")],
        )
