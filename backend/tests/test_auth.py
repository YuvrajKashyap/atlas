# pyright: reportPrivateUsage=false

from typing import Any

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

import atlas.auth as auth
from atlas.auth import Principal
from atlas.config import Settings


def test_auth_configuration_requires_oidc_in_production() -> None:
    with pytest.raises(RuntimeError, match="Production requires"):
        auth.validate_auth_configuration(Settings(environment="production", auth_mode="disabled"))
    with pytest.raises(RuntimeError, match="OIDC mode requires"):
        auth.validate_auth_configuration(Settings(auth_mode="oidc"))

    auth.validate_auth_configuration(
        Settings(
            environment="production",
            auth_mode="oidc",
            oidc_issuer="https://issuer.example",
            oidc_audience="atlas",
            oidc_jwks_url="https://issuer.example/jwks.json",
        )
    )


def test_disabled_auth_returns_local_admin_and_role_guards() -> None:
    principal = auth.get_principal(None, Settings(auth_mode="disabled"))

    assert principal.is_admin
    assert auth.require_viewer(principal) is principal
    assert auth.require_admin(principal) is principal
    with pytest.raises(HTTPException) as viewer_error:
        auth.require_viewer(Principal("no-role", frozenset(), {}))
    assert viewer_error.value.status_code == 403
    with pytest.raises(HTTPException) as admin_error:
        auth.require_admin(Principal("viewer", frozenset({"viewer"}), {}))
    assert admin_error.value.status_code == 403


def test_oidc_claims_map_cognito_groups_and_reject_invalid_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SigningKey:
        key = object()

    class JwksClient:
        def get_signing_key_from_jwt(self, _token: str) -> SigningKey:
            return SigningKey()

    settings = Settings(
        auth_mode="oidc",
        oidc_issuer="https://issuer.example",
        oidc_audience="atlas",
        oidc_jwks_url="https://issuer.example/jwks.json",
    )
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")

    def jwks_client(_url: str) -> JwksClient:
        return JwksClient()

    monkeypatch.setattr(auth, "_jwks_client", jwks_client)

    def admin_claims(*_args: object, **_kwargs: object) -> dict[str, Any]:
        return {"sub": "user-1", "cognito:groups": ["atlas-admin"]}

    monkeypatch.setattr(auth.jwt, "decode", admin_claims)
    principal = auth.get_principal(credentials, settings)
    assert principal.roles == frozenset({"admin", "viewer"})

    def no_roles(*_args: object, **_kwargs: object) -> dict[str, Any]:
        return {"sub": "user-2", "groups": []}

    monkeypatch.setattr(auth.jwt, "decode", no_roles)
    with pytest.raises(HTTPException) as forbidden:
        auth.get_principal(credentials, settings)
    assert forbidden.value.status_code == 403

    def invalid(*_args: object, **_kwargs: object) -> dict[str, Any]:
        raise jwt.InvalidTokenError("invalid")

    monkeypatch.setattr(auth.jwt, "decode", invalid)
    with pytest.raises(HTTPException) as unauthorized:
        auth.get_principal(credentials, settings)
    assert unauthorized.value.status_code == 401
    with pytest.raises(HTTPException) as missing:
        auth.get_principal(None, settings)
    assert missing.value.status_code == 401


def test_redis_rate_limit_fails_closed_and_enforces_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    principal = Principal("user", frozenset({"viewer"}), {})
    request = object()
    auth.enforce_rate_limit(request, principal, Settings(auth_mode="disabled"))  # type: ignore[arg-type]

    class FakeRedis:
        def __init__(self, value: int) -> None:
            self.value = value
            self.expired = False

        def execute_command(self, _command: str, _key: str) -> int:
            return self.value

        def expire(self, _key: str, _seconds: int) -> None:
            self.expired = True

    redis = FakeRedis(1)

    def redis_from_url(_url: str, **_kwargs: object) -> FakeRedis:
        return redis

    monkeypatch.setattr(auth.Redis, "from_url", redis_from_url)
    settings = Settings(auth_mode="oidc", rate_limit_per_minute=1)
    auth.enforce_rate_limit(request, principal, settings)  # type: ignore[arg-type]
    assert redis.expired

    redis.value = 2
    with pytest.raises(HTTPException) as limited:
        auth.enforce_rate_limit(request, principal, settings)  # type: ignore[arg-type]
    assert limited.value.status_code == 429

    def fail(_url: str) -> object:
        raise OSError("redis unavailable")

    monkeypatch.setattr(auth.Redis, "from_url", fail)
    with pytest.raises(HTTPException) as unavailable:
        auth.enforce_rate_limit(request, principal, settings)  # type: ignore[arg-type]
    assert unavailable.value.status_code == 503
