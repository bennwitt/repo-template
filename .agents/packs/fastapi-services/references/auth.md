# Auth: settings, dependencies and tests

Tested with FastAPI 0.142.4, PyJWT 2.15.1 (`pyjwt[crypto]`), pydantic-settings 2.15.0 and httpx2
2.13.1. Open WebUI's forwarded-user JWT was checked in its source at 0.11.4 and 0.12.0.

## Settings

```python
# app/settings.py
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env")

    api_key: SecretStr = SecretStr("")
    openwebui_user_jwt_secret: SecretStr = SecretStr("")
    idp_jwks_url: str = ""
    idp_issuer: str = ""
    idp_audience: str = ""
    cors_origins: list[str] = []  # APP_CORS_ORIGINS='["https://chat.example.com"]'


@lru_cache
def get_settings() -> Settings:
    return Settings()


SettingsDep = Annotated[Settings, Depends(get_settings)]
```

An empty secret means "not configured", and the dependencies below then reject every call with 401.
Tenant IDs, client IDs and keys go in the environment or a git-ignored `.env`, never in committed
files.

## Dependencies

```python
# app/auth.py
import secrets
from functools import lru_cache
from typing import Annotated, Any

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.settings import SettingsDep

bearer = HTTPBearer()
BearerDep = Annotated[HTTPAuthorizationCredentials, Depends(bearer)]


def unauthorized(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"})


def require_api_key(settings: SettingsDep, creds: BearerDep) -> None:
    """The static key configured on the Open WebUI connection (or any service-to-service caller)."""
    expected = settings.api_key.get_secret_value()
    # Compare bytes: compare_digest raises TypeError on a non-ASCII str, which would be a 500.
    if not expected or not secrets.compare_digest(creds.credentials.encode(), expected.encode()):
        raise unauthorized("Invalid API key")


class OpenWebUIUser(BaseModel):
    sub: str
    email: str
    name: str
    role: str


def openwebui_user(
    settings: SettingsDep, x_openwebui_user_jwt: Annotated[str, Header()]
) -> OpenWebUIUser:
    """The user behind an Open WebUI call, from FORWARD_USER_INFO_HEADER_JWT_SECRET's signed header."""
    secret = settings.openwebui_user_jwt_secret.get_secret_value()
    if not secret:
        raise unauthorized("User token not configured")
    try:
        claims = jwt.decode(
            x_openwebui_user_jwt,
            secret,
            algorithms=["HS256"],
            issuer="open-webui",
            options={"require": ["exp", "iss", "sub"]},
        )
    except jwt.PyJWTError:
        raise unauthorized("Invalid user token") from None
    return OpenWebUIUser.model_validate(claims)


@lru_cache
def jwks_client(url: str) -> jwt.PyJWKClient:
    """One client per JWKS URL, so its key-set cache (300 s by default) is shared across requests."""
    return jwt.PyJWKClient(url)


def idp_claims(settings: SettingsDep, creds: BearerDep) -> dict[str, Any]:
    """An access token from an OIDC identity provider. A plain `def`: PyJWKClient fetches with urllib."""
    try:
        key = jwks_client(settings.idp_jwks_url).get_signing_key_from_jwt(creds.credentials)
        return jwt.decode(
            creds.credentials,
            key,
            algorithms=["RS256"],
            audience=settings.idp_audience,
            issuer=settings.idp_issuer,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except jwt.PyJWKClientConnectionError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Signing keys unavailable") from None
    except jwt.PyJWTError:
        raise unauthorized("Invalid access token") from None
```

Apply them where they belong: `APIRouter(prefix="/v1", dependencies=[Depends(require_api_key)])`
for the OpenAI-compatible routes, and a typed parameter where the handler needs the identity:

```python
@router.get("/search")
def search_docs(q: str, user: Annotated[OpenWebUIUser, Depends(openwebui_user)]) -> list[Doc]:
    """Search the product documentation. Use for questions about features, setup or errors."""
```

Notes:

- `jwt.decode` takes the `PyJWK` from `get_signing_key_from_jwt` directly. Always pass the
  `algorithms` list yourself; never take it from the token header.
- A missing `X-OpenWebUI-User-Jwt` header is a 422 (a required header), not a 401. Make the
  parameter optional and raise 401 yourself if callers need a uniform status.
- The forwarded JWT has no `aud` claim, so `openwebui_user` passes no audience. The claims are
  minted by Open WebUI from its own user record. The plain `X-OpenWebUI-User-*` headers it sends
  without `FORWARD_USER_INFO_HEADER_JWT_SECRET` are unsigned. Trust them only when a network
  boundary guarantees that nothing but Open WebUI reaches the service.
- With `ENABLE_FORWARD_USER_INFO_HEADERS=true`, Open WebUI also sends the user JWT (or the plain
  headers) to OpenAI-compatible connections, together with `X-OpenWebUI-Chat-Id`.

## Entra ID values

Which access token version the API receives is set by `requestedAccessTokenVersion` in the API's
own app registration manifest (`accessTokenAcceptedVersion` in the older Azure AD Graph format),
whatever endpoint the client used:

| `requestedAccessTokenVersion` | `iss` | `aud` |
|---|---|---|
| `2` | `https://login.microsoftonline.com/<tenant-id>/v2.0` | always the API's client ID (a GUID) |
| `1` or null | `https://sts.windows.net/<tenant-id>/` | one of the API's Application ID URIs (with or without a trailing slash) or its client ID, depending on how the client asked |

For a new API, set it to `2`, so the audience is one fixed value. With v1 tokens, pass every
accepted value as a list to `audience`. Read `issuer` and `jwks_uri` once from the metadata
document for that version (drop `/v2.0` from the URL for v1 tokens), then store them in settings:

```bash
curl -s "https://login.microsoftonline.com/$TENANT_ID/v2.0/.well-known/openid-configuration" | jq '{issuer, jwks_uri}'
```

Source: Microsoft Learn, "Access tokens in the Microsoft identity platform", "Access token claims
reference" and "Secure applications and APIs by validating claims". Once the signature, issuer
and audience check out,
that guidance also asks you to check `tid` against your tenant and to authorize the subject by
`oid`/`sub` or `roles`/`groups`, never by `email`, `preferred_username`, `unique_name` or `upn`. It
also asks you to authorize the calling app by `scp`, which app-only tokens lack.

## Self-issued tokens

FastAPI's tutorial (https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/) is current: PyJWT,
`pwdlib[argon2]`, `PasswordHash.recommended()`, a dummy hash for unknown usernames. Load
`SECRET_KEY` from settings (`openssl rand -hex 32` makes one) rather than its hard-coded value.
The tutorial's `verify_password` is already a plain `def`, but its `async def
login_for_access_token` calls it on the event loop, so every login blocks the server while Argon2
runs. Make that path operation a plain `def`, or call the hash through
`await run_in_threadpool(...)` (`fastapi.concurrency`). `password_hash.verify_and_update(password,
hash)` returns `(valid, new_hash_or_None)`, so a hash can be upgraded at login when the parameters
change.

## Tests

```python
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

from app.auth import jwks_client
from app.settings import Settings

ISSUER, AUDIENCE = "https://login.example.com/tenant-id/v2.0", "api-client-id"


@pytest.fixture
def idp_key(monkeypatch: pytest.MonkeyPatch) -> rsa.RSAPrivateKey:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(RSAAlgorithm.to_jwk(key.public_key())) | {"kid": "test", "alg": "RS256", "use": "sig"}
    monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", lambda self: {"keys": [jwk]})
    jwks_client.cache_clear()  # a cached client would keep the previous test's key set
    return key


def test_idp_token(client: TestClient, idp_key: rsa.RSAPrivateKey) -> None:
    now = int(time.time())
    claims = {"iss": ISSUER, "aud": AUDIENCE, "sub": "user-1", "exp": now + 60}
    token = jwt.encode(claims, idp_key, algorithm="RS256", headers={"kid": "test"})
    assert client.get("/tools/me", headers={"Authorization": f"Bearer {token}"}).json() == {"sub": "user-1"}
    wrong = jwt.encode(claims | {"aud": "other-api"}, idp_key, algorithm="RS256", headers={"kid": "test"})
    assert client.get("/tools/me", headers={"Authorization": f"Bearer {wrong}"}).status_code == 401


def test_openwebui_user(client: TestClient, settings: Settings) -> None:
    now = int(time.time())
    claims = {"sub": "u1", "email": "a@example.com", "name": "A", "role": "user",
              "iss": "open-webui", "iat": now, "exp": now + 300}
    token = jwt.encode(claims, settings.openwebui_user_jwt_secret.get_secret_value(), algorithm="HS256")
    r = client.get("/tools/search", params={"q": "setup"}, headers={"X-OpenWebUI-User-Jwt": token})
    assert r.status_code == 200
```

The `settings` fixture is the autouse one from SKILL.md, extended with the IdP and Open WebUI
fields. Give `openwebui_user_jwt_secret` at least 32 bytes, in tests and on Open WebUI alike:
PyJWT emits `InsecureKeyLengthWarning` for a shorter HS256 key, and under
`filterwarnings = ["error"]` that warning fails the test. `/tools/me` is a plain handler that
depends on `idp_claims` and returns `{"sub": claims["sub"]}`.
