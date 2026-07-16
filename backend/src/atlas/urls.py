import ipaddress
import posixpath
import re
import socket
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit


class UrlPolicyError(ValueError):
    pass


TRACKING_KEYS = {"fbclid", "gclid", "dclid", "msclkid", "mc_cid", "mc_eid"}
TRACKING_PREFIXES = ("utm_",)
SUPPORTED_SCHEMES = {"http", "https"}


@dataclass(frozen=True, slots=True)
class ValidatedTarget:
    url: str
    host: str
    addresses: tuple[str, ...]


def normalize_domain(value: str) -> str:
    candidate = value.strip().rstrip(".").lower()
    if "://" in candidate:
        parsed = urlsplit(candidate)
        candidate = parsed.hostname or ""
    if not candidate or "/" in candidate or "@" in candidate:
        raise UrlPolicyError("Allowed domains must be hostnames, not paths or credentials")
    try:
        return candidate.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise UrlPolicyError("Domain is not valid IDNA") from exc


def normalize_url(value: str, *, base_url: str | None = None) -> str:
    raw = value.strip()
    if base_url is not None:
        raw = urljoin(base_url, raw)

    parsed = urlsplit(raw)
    scheme = parsed.scheme.lower()
    if scheme not in SUPPORTED_SCHEMES:
        raise UrlPolicyError("Only http and https URLs are supported")
    if parsed.username is not None or parsed.password is not None:
        raise UrlPolicyError("Credentials in URLs are not allowed")
    if not parsed.hostname:
        raise UrlPolicyError("URL must include a hostname")

    try:
        host = parsed.hostname.rstrip(".").lower().encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise UrlPolicyError("URL hostname is not valid IDNA") from exc

    try:
        port = parsed.port
    except ValueError as exc:
        raise UrlPolicyError("URL port is invalid") from exc

    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    netloc = host if port is None or default_port else f"{host}:{port}"

    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    trailing_slash = path.endswith("/")
    path = posixpath.normpath(path)
    if not path.startswith("/"):
        path = f"/{path}"
    if trailing_slash and path != "/":
        path = f"{path}/"

    query_items: list[tuple[str, str]] = []
    for key, item_value in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered in TRACKING_KEYS or lowered.startswith(TRACKING_PREFIXES):
            continue
        query_items.append((key, item_value))
    query = urlencode(sorted(query_items), doseq=True)

    return urlunsplit((scheme, netloc, path, query, ""))


def host_for_url(url: str) -> str:
    parsed = urlsplit(url)
    if not parsed.hostname:
        raise UrlPolicyError("URL must include a hostname")
    return parsed.hostname.rstrip(".").lower().encode("idna").decode("ascii")


def is_host_allowed(host: str, allowed_domains: list[tuple[str, bool]]) -> bool:
    normalized_host = normalize_domain(host)
    for domain, include_subdomains in allowed_domains:
        normalized_domain = normalize_domain(domain)
        if normalized_host == normalized_domain:
            return True
        if include_subdomains and normalized_host.endswith(f".{normalized_domain}"):
            return True
    return False


def validate_fetch_target(
    url: str,
    allowed_domains: list[tuple[str, bool]],
    *,
    allow_private_networks: bool = False,
) -> ValidatedTarget:
    normalized = normalize_url(url)
    host = host_for_url(normalized)
    if (
        host == "localhost" or host.endswith(".localhost") or host.endswith(".local")
    ) and not allow_private_networks:
        raise UrlPolicyError("Local network destinations are not allowed")
    if not is_host_allowed(host, allowed_domains):
        raise UrlPolicyError("URL host is outside the crawl allowlist")

    port = urlsplit(normalized).port or (443 if normalized.startswith("https://") else 80)
    try:
        records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UrlPolicyError(f"Hostname could not be resolved: {host}") from exc

    addresses = tuple(sorted({str(record[4][0]) for record in records}))
    if not addresses:
        raise UrlPolicyError("Hostname did not resolve to an address")
    if not allow_private_networks:
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if not ip.is_global:
                raise UrlPolicyError(f"Non-public destination is not allowed: {address}")

    return ValidatedTarget(url=normalized, host=host, addresses=addresses)
