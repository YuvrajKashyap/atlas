import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any, cast

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from redis import Redis

from atlas.config import Settings, get_settings

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class Principal:
    subject: str
    roles: frozenset[str]
    claims: dict[str, Any]

    @property
    def is_admin(self) -> bool:
        return "admin" in self.roles


@lru_cache
def _jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_keys=True)


def validate_auth_configuration(settings: Settings) -> None:
    if settings.environment.lower() == "production" and settings.auth_mode != "oidc":
        raise RuntimeError("Production requires ATLAS_AUTH_MODE=oidc")
    if settings.auth_mode == "oidc" and not (
        settings.oidc_issuer and settings.oidc_audience and settings.oidc_jwks_url
    ):
        raise RuntimeError("OIDC mode requires issuer, audience, and JWKS URL")


def _roles_from_claims(claims: dict[str, Any], settings: Settings) -> frozenset[str]:
    raw_groups = claims.get("cognito:groups", claims.get("groups", claims.get("roles", [])))
    groups = (
        {str(item) for item in cast(list[object], raw_groups)}
        if isinstance(raw_groups, list)
        else {str(raw_groups)}
    )
    roles: set[str] = set()
    if settings.oidc_admin_group in groups:
        roles.update({"admin", "viewer"})
    if settings.oidc_viewer_group in groups:
        roles.add("viewer")
    return frozenset(roles)


def get_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Principal:
    if settings.auth_mode == "disabled":
        return Principal("local-development", frozenset({"admin", "viewer"}), {})
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    try:
        signing_key = _jwks_client(settings.oidc_jwks_url).get_signing_key_from_jwt(
            credentials.credentials
        )
        claims = jwt.decode(
            credentials.credentials,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer,
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token"
        ) from exc
    roles = _roles_from_claims(claims, settings)
    if not roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Atlas role required")
    return Principal(str(claims.get("sub", "unknown")), roles, claims)


def require_viewer(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
    if "viewer" not in principal.roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Viewer role required")
    return principal


def require_admin(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
    if not principal.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return principal


def enforce_rate_limit(
    request: Request,
    principal: Annotated[Principal, Depends(require_viewer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    if settings.auth_mode == "disabled":
        return
    window = int(time.time() // 60)
    key = f"atlas:rate:{principal.subject}:{window}"
    try:
        redis = Redis.from_url(settings.redis_url, password=settings.redis_password or None)
        current = int(cast(int, redis.execute_command("INCR", key)))
        if current == 1:
            redis.expire(key, 120)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Rate limiter unavailable",
        ) from exc
    if current > settings.rate_limit_per_minute:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Request rate limit exceeded",
            headers={"Retry-After": "60"},
        )
