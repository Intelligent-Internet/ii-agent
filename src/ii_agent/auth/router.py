"""Authentication API endpoints."""

import base64
import hashlib
import json
import secrets
import time
from typing import Any, Dict, Optional
from urllib.parse import urlparse, urlencode

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi_sso.sso.google import GoogleSSO
from itsdangerous import URLSafeSerializer, BadSignature

from ii_agent.auth.dependencies import DBSession, CurrentUser, SettingsDep
from ii_agent.auth.exceptions import AuthException, InvalidTokenException
from ii_agent.auth.jwt_handler import jwt_handler
from ii_agent.auth.oidc_verify import verify_id_token_pyjwt, verify_at_hash_if_present
from ii_agent.auth.schemas import TokenResponse
from ii_agent.core.config.settings import get_settings
from ii_agent.core.exceptions import BadGatewayError, InternalError, ValidationError
from ii_agent.users.dependencies import UserServiceDep
from ii_agent.users.schemas import UserPublic

router = APIRouter(prefix="/auth", tags=["Authentication"])

II_STATE_SESSION_KEY = "ii_oauth_state"
II_CODE_VERIFIER_SESSION_KEY = "ii_code_verifier"
II_RETURN_TO_SESSION_KEY = "ii_return_to"

# Simple in-memory rate limiter for dev login
_DEV_LOGIN_TIMESTAMPS: dict[str, float] = {}
_DEV_LOGIN_RATE_LIMIT_SECONDS = 10  # Allow one request per 10 seconds per IP
II_RETURN_URL_SESSION_KEY = "ii_return_url"

# ---------------------------------------------------------------------------
# Auth callback HTML template (inlined from templates.py — single consumer)
# ---------------------------------------------------------------------------

_AUTH_CALLBACK_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>II Login</title>
</head>
<body>
<script>
  (function() {
    const payload = %s;
    const targetOrigin = %s;
    const redirectUrl = %s;
    const message = { type: 'ii-auth-success', payload };
    const fallbackOrigin = (() => {
      if (targetOrigin) return targetOrigin;
      try {
        if (redirectUrl) return new URL(redirectUrl).origin;
      } catch (e) {}
      return window.location.origin;
    })();

    function redirectWithHash() {
      if (!redirectUrl) return;
      try {
        const url = new URL(redirectUrl);
        url.hash = 'ii-auth=' + encodeURIComponent(JSON.stringify(payload));
        window.location.replace(url.toString());
      } catch (e) {
        window.location.replace(redirectUrl);
      }
    }

    try {
      if (window.opener && !window.opener.closed) {
        window.opener.postMessage(message, fallbackOrigin || '*');
        window.close();
        return;
      }
    } catch (err) {
      console.error('postMessage to opener failed', err);
    }

    if (redirectUrl) {
      redirectWithHash();
      return;
    }

    document.body.innerHTML = '<p>Login successful. You can close this window.</p>';
  })();
</script>
</body>
</html>
"""


def _render_auth_callback_html(
    token_payload: dict,
    return_origin: Optional[str],
    return_url: Optional[str],
) -> str:
    """Render the OAuth callback HTML that posts tokens back to the opener."""
    return _AUTH_CALLBACK_HTML % (
        json.dumps(token_payload),
        json.dumps(return_origin or ""),
        json.dumps(return_url or ""),
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_serializer(salt: str = "ii-state") -> URLSafeSerializer:
    return URLSafeSerializer(get_settings().oauth.session_secret_key, salt=salt)


def _make_state() -> str:
    raw = secrets.token_urlsafe(32)
    return _get_serializer().dumps(raw)


def _verify_state(value: str) -> bool:
    try:
        _get_serializer().loads(value)
        return True
    except BadSignature:
        return False


def _make_pkce_pair() -> tuple[str, str]:
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(40)).rstrip(b"=").decode("ascii")
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge


def _sanitize_return_to(value: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    if not value:
        return None, None

    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValidationError("Invalid return_to parameter")

    origin = f"{parsed.scheme}://{parsed.netloc}"
    return origin, value


def _make_token_payload(user_id: str, email: str, role: str) -> dict:
    """Build the JWT token payload dict for a user."""
    access_token = jwt_handler.create_access_token(
        user_id=user_id,
        email=email,
        role=role,
    )
    refresh_token = jwt_handler.create_refresh_token(user_id=user_id)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": jwt_handler.access_token_expire_minutes * 60,
    }


async def _exchange_code_for_token(code: str, code_verifier: Optional[str]) -> Dict[str, Any]:
    settings = get_settings()
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.oauth.ii_redirect_uri,
        "client_id": settings.oauth.ii_client_id,
    }
    if code_verifier:
        data["code_verifier"] = code_verifier

    headers = {"content-type": "application/x-www-form-urlencoded"}
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(settings.ii_token_url, data=data, headers=headers)
    if response.status_code != 200:
        raise BadGatewayError(f"Token exchange failed: {response.text}")
    return response.json()


async def _fetch_userinfo_if_enabled(
    access_token: Optional[str],
) -> Optional[Dict[str, Any]]:
    settings = get_settings()
    if not access_token or not settings.oauth.ii_use_userinfo:
        return None

    url = settings.oauth.ii_userinfo_url
    if not url:
        async with httpx.AsyncClient(timeout=10) as client:
            discovery_resp = await client.get(
                f"{settings.ii_issuer}/.well-known/openid-configuration"
            )
        if discovery_resp.status_code != 200:
            raise BadGatewayError(
                f"Discovery fetch failed: {discovery_resp.status_code} {discovery_resp.text}"
            )
        url = discovery_resp.json().get("userinfo_endpoint")
        if not url:
            raise BadGatewayError("userinfo_endpoint missing in discovery document")

    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, headers=headers)
    if resp.status_code != 200:
        raise BadGatewayError(f"userinfo failed: {resp.text}")
    return resp.json()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/oauth/ii/login")
async def ii_login(request: Request, settings: SettingsDep, return_to: Optional[str] = None):
    """Initiate II OAuth login by redirecting to the authorization server."""

    if not settings.oauth.ii_client_id:
        raise InternalError("II OAuth client_id not configured")

    origin, safe_url = _sanitize_return_to(return_to)
    if safe_url is None:
        referer = request.headers.get("referer")
        origin, safe_url = _sanitize_return_to(referer)

    state = _make_state()
    code_verifier, code_challenge = _make_pkce_pair()

    request.session[II_STATE_SESSION_KEY] = state
    request.session[II_CODE_VERIFIER_SESSION_KEY] = code_verifier
    if origin:
        request.session[II_RETURN_TO_SESSION_KEY] = origin
    if safe_url:
        request.session[II_RETURN_URL_SESSION_KEY] = safe_url

    params = {
        "client_id": settings.oauth.ii_client_id,
        "response_type": "code",
        "redirect_uri": settings.oauth.ii_redirect_uri,
        "scope": settings.oauth.ii_scope,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }

    query = urlencode(params)
    return RedirectResponse(url=f"{settings.ii_auth_url}?{query}", status_code=302)


@router.get("/oauth/ii/callback")
async def ii_callback(
    request: Request,
    db: DBSession,
    settings: SettingsDep,
    user_service: UserServiceDep,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
):
    """Handle II OAuth callback, verify tokens, and emit auth result."""

    if error:
        raise ValidationError(f"OAuth error: {error}")

    if not code or not state:
        raise ValidationError("Missing code or state")

    expected_state = request.session.get(II_STATE_SESSION_KEY)
    if not expected_state or state != expected_state or not _verify_state(state):
        raise ValidationError("Invalid state")

    code_verifier = request.session.get(II_CODE_VERIFIER_SESSION_KEY)

    token_set = await _exchange_code_for_token(code, code_verifier)

    id_token = token_set.get("id_token")
    hydra_access_token = token_set.get("access_token")

    if not id_token:
        raise BadGatewayError("Missing id_token in token response")

    try:
        claims = verify_id_token_pyjwt(
            id_token=id_token,
            issuer=settings.ii_issuer,
            audience=settings.oauth.ii_client_id,
            expected_nonce=None,
            leeway=60,
        )
        if hydra_access_token:
            verify_at_hash_if_present(claims, hydra_access_token, alg="RS256")
    except Exception as exc:  # noqa: BLE001
        raise InvalidTokenException(f"ID token verification failed: {exc}") from exc

    email_claim = claims.get("email")
    email = (email_claim or "").strip().lower()
    if not email:
        raise BadGatewayError("Email claim missing from ID token")

    email_verified = bool(claims.get("email_verified", False))
    first_name = claims.get("name").get("first") or ""
    last_name = claims.get("name").get("last") or ""
    picture = claims.get("picture") or None

    userinfo = None
    try:
        userinfo = await _fetch_userinfo_if_enabled(hydra_access_token)
    except BadGatewayError:
        userinfo = None

    if userinfo:
        first_name = userinfo.get("given_name") or first_name
        last_name = userinfo.get("family_name") or last_name
        picture = userinfo.get("picture") or picture

    await user_service.check_waitlist(db, email)
    user_stored = await user_service.find_or_create_oauth_user(
        db,
        email=email,
        first_name=first_name,
        last_name=last_name,
        avatar=picture,
        email_verified=email_verified,
        login_provider="ii",
    )

    token_payload = _make_token_payload(
        str(user_stored.id),
        str(user_stored.email),
        str(user_stored.role),
    )

    request.session.pop(II_STATE_SESSION_KEY, None)
    request.session.pop(II_CODE_VERIFIER_SESSION_KEY, None)

    return_origin = request.session.pop(II_RETURN_TO_SESSION_KEY, None)
    return_url = request.session.pop(II_RETURN_URL_SESSION_KEY, None)

    html_content = _render_auth_callback_html(token_payload, return_origin, return_url)
    return HTMLResponse(content=html_content)


@router.get("/oauth/google/login")
async def google_login(settings: SettingsDep):
    """Redirect to Google SSO login."""

    google_sso = GoogleSSO(
        settings.oauth.google_client_id or "",
        settings.oauth.google_client_secret or "",
        redirect_uri=settings.oauth.google_redirect_uri,
    )
    async with google_sso:
        return await google_sso.get_login_redirect(
            params={"prompt": "consent", "access_type": "offline"}
        )


@router.get("/oauth/google/callback")
async def google_callback(
    request: Request,
    db: DBSession,
    settings: SettingsDep,
    user_service: UserServiceDep,
):
    """Handle Google SSO callback and login."""
    state = request.query_params.get("state")
    if state:
        state_serializer = URLSafeSerializer(settings.oauth.session_secret_key)
        connector_state: Optional[dict[str, Any]] = None
        try:
            loaded_state = state_serializer.loads(state)
            if isinstance(loaded_state, dict):
                connector_state = loaded_state
        except BadSignature:
            connector_state = None

        if connector_state and connector_state.get("connector") == "google_drive":
            code = request.query_params.get("code")
            error = request.query_params.get("error")
            error_description = request.query_params.get("error_description")

            frontend_url = connector_state.get("frontend_url")
            if not frontend_url:
                referer = request.headers.get("referer")
                if referer:
                    parsed = urlparse(referer)
                    frontend_url = f"{parsed.scheme}://{parsed.netloc}"

            if not frontend_url:
                raise ValidationError("Could not determine frontend URL for redirect")

            params = {}
            if code:
                params["code"] = code
            if state:
                params["state"] = state
            if error:
                params["error"] = error
            if error_description:
                params["error_description"] = error_description

            query_string = urlencode(params)
            frontend_callback_url = f"{frontend_url}/google-drive-callback?{query_string}"

            return RedirectResponse(url=frontend_callback_url, status_code=302)

    url = request.query_params.get("redirect_uri")
    google_sso = GoogleSSO(
        settings.oauth.google_client_id or "",
        settings.oauth.google_client_secret or "",
        redirect_uri=(url or settings.oauth.google_redirect_uri),
    )
    async with google_sso:
        user_info = await google_sso.verify_and_process(request)
    if not user_info:
        raise AuthException("Failed to get user info from Google SSO")

    email = (user_info.email or "").strip().lower()
    if not email:
        raise ValidationError("Email not provided by Google account")

    bonus_credits = (
        settings.credits.beta_program_bonus_credits
        if settings.credits.beta_program_enabled
        else 0.0
    )
    await user_service.check_waitlist(db, email)
    user_stored = await user_service.find_or_create_oauth_user(
        db,
        email=email,
        first_name=user_info.first_name or "",
        last_name=user_info.last_name or "",
        avatar=user_info.picture or None,
        email_verified=True,
        bonus_credits=bonus_credits,
        login_provider="google",
    )

    token_payload = _make_token_payload(
        str(user_stored.id),
        str(user_stored.email),
        str(user_stored.role),
    )

    return TokenResponse(
        access_token=token_payload["access_token"],
        refresh_token=token_payload["refresh_token"],
        expires_in=token_payload["expires_in"],
    )


@router.get("/me", response_model=UserPublic)
async def reader_user_me(
    db: DBSession,
    current_user: CurrentUser,
) -> UserPublic:
    return UserPublic(
        id=str(current_user.id),
        email=str(current_user.email),
        role=str(current_user.role),
        first_name=str(current_user.first_name or ""),
        last_name=str(current_user.last_name or ""),
        avatar=current_user.avatar,
        subscription_status=current_user.subscription_status,
        subscription_plan=current_user.subscription_plan,
        subscription_billing_cycle=current_user.subscription_billing_cycle,
        subscription_current_period_end=current_user.subscription_current_period_end,
        language=str(current_user.language or "en"),
    )


@router.post("/dev/login")
async def dev_login(
    request: Request,
    db: DBSession,
    settings: SettingsDep,
    user_service: UserServiceDep,
):
    """Development-only login that creates/finds a local dev user.

    Only available when ``SANDBOX_LOCAL_MODE=true``.
    Returns JWT tokens for a deterministic dev user without OAuth.
    """
    if not settings.sandbox.local_mode:
        raise ValidationError("Dev login is only available in local mode")

    # Simple rate limiting by client IP
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    last_request = _DEV_LOGIN_TIMESTAMPS.get(client_ip, 0)
    if now - last_request < _DEV_LOGIN_RATE_LIMIT_SECONDS:
        raise ValidationError(
            f"Rate limited. Please wait {_DEV_LOGIN_RATE_LIMIT_SECONDS} seconds between requests."
        )
    _DEV_LOGIN_TIMESTAMPS[client_ip] = now

    # Clean up old entries (simple GC)
    stale_threshold = now - 3600  # Remove entries older than 1 hour
    for ip in list(_DEV_LOGIN_TIMESTAMPS.keys()):
        if _DEV_LOGIN_TIMESTAMPS[ip] < stale_threshold:
            del _DEV_LOGIN_TIMESTAMPS[ip]

    dev_email = "dev@localhost"
    user = await user_service.find_or_create_oauth_user(
        db,
        email=dev_email,
        first_name="Local",
        last_name="Developer",
        avatar=None,
        email_verified=True,
        login_provider="dev",
    )

    token_payload = _make_token_payload(
        str(user.id),
        str(user.email),
        str(user.role),
    )

    return TokenResponse(
        access_token=token_payload["access_token"],
        refresh_token=token_payload["refresh_token"],
        expires_in=token_payload["expires_in"],
    )


# Keep GET endpoint for backward compatibility but redirect to docs
@router.get("/dev/login")
async def dev_login_get(
    request: Request,
    db: DBSession,
    settings: SettingsDep,
    user_service: UserServiceDep,
):
    """Backward-compatible GET endpoint for dev login.

    In local mode, redirects to login via POST semantics for convenience.
    """
    return await dev_login(request, db, settings, user_service)
