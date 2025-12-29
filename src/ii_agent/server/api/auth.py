"""Authentication API endpoints."""

import base64
import hashlib
import json
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.parse import urlparse, urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi_sso.sso.google import GoogleSSO
from itsdangerous import URLSafeSerializer, BadSignature
from sqlalchemy import select, func

from ii_agent.server.auth.oidc_verify import (
    verify_id_token_pyjwt,
    verify_at_hash_if_present,
)

from ii_agent.db.models import User, APIKey, WaitlistEntry
from ii_agent.server.api.deps import DBSession
from ii_agent.server.api.deps import CurrentUser
from ii_agent.server.models.auth import (
    TokenResponse,
)
from ii_agent.server.auth.jwt_handler import jwt_handler
from ii_agent.core.config.ii_agent_config import config
from ii_agent.server.models.users import UserPublic
from ii_agent.server.auth.api_key_utils import generate_prefixed_api_key


router = APIRouter(prefix="/auth", tags=["Authentication"])


II_STATE_SESSION_KEY = "ii_oauth_state"
II_CODE_VERIFIER_SESSION_KEY = "ii_code_verifier"
II_RETURN_TO_SESSION_KEY = "ii_return_to"
II_RETURN_URL_SESSION_KEY = "ii_return_url"


serializer = URLSafeSerializer(config.session_secret_key, salt="ii-state")


def _make_state() -> str:
    raw = secrets.token_urlsafe(32)
    return serializer.dumps(raw)


def _verify_state(value: str) -> bool:
    try:
        serializer.loads(value)
        return True
    except BadSignature:
        return False


def _make_pkce_pair() -> tuple[str, str]:
    code_verifier = (
        base64.urlsafe_b64encode(secrets.token_bytes(40)).rstrip(b"=").decode("ascii")
    )
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge


def _sanitize_return_to(value: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    if not value:
        return None, None

    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Invalid return_to parameter")

    origin = f"{parsed.scheme}://{parsed.netloc}"
    return origin, value


async def _exchange_code_for_token(
    code: str, code_verifier: Optional[str]
) -> Dict[str, Any]:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": config.ii_redirect_uri,
        "client_id": config.ii_client_id,
    }
    if code_verifier:
        data["code_verifier"] = code_verifier

    headers = {"content-type": "application/x-www-form-urlencoded"}
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(config.ii_token_url, data=data, headers=headers)
    if response.status_code != 200:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Token exchange failed: {response.text}",
        )
    return response.json()


async def _fetch_userinfo_if_enabled(
    access_token: Optional[str],
) -> Optional[Dict[str, Any]]:
    if not access_token or not config.ii_use_userinfo:
        return None

    url = config.ii_userinfo_url
    if not url:
        async with httpx.AsyncClient(timeout=10) as client:
            discovery_resp = await client.get(
                f"{config.ii_issuer}/.well-known/openid-configuration"
            )
        if discovery_resp.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=(
                    f"Discovery fetch failed: {discovery_resp.status_code} "
                    f"{discovery_resp.text}"
                ),
            )
        url = discovery_resp.json().get("userinfo_endpoint")
        if not url:
            raise HTTPException(
                status_code=502,
                detail="userinfo_endpoint missing in discovery document",
            )

    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, headers=headers)
    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code, detail=f"userinfo failed: {resp.text}"
        )
    return resp.json()


@router.get("/oauth/ii/login")
async def ii_login(request: Request, return_to: Optional[str] = None):
    """Initiate II OAuth login by redirecting to the authorization server."""

    if not config.ii_client_id:
        raise HTTPException(status_code=500, detail="II OAuth client_id not configured")

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
        "client_id": config.ii_client_id,
        "response_type": "code",
        "redirect_uri": config.ii_redirect_uri,
        "scope": config.ii_scope,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }

    query = urlencode(params)
    return RedirectResponse(url=f"{config.ii_auth_url}?{query}", status_code=302)


@router.get("/oauth/ii/callback")
async def ii_callback(
    request: Request,
    db: DBSession,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
):
    """Handle II OAuth callback, verify tokens, and emit auth result."""

    if error:
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}")

    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")

    expected_state = request.session.get(II_STATE_SESSION_KEY)
    if not expected_state or state != expected_state or not _verify_state(state):
        raise HTTPException(status_code=400, detail="Invalid state")

    code_verifier = request.session.get(II_CODE_VERIFIER_SESSION_KEY)

    token_set = await _exchange_code_for_token(code, code_verifier)

    id_token = token_set.get("id_token")
    hydra_access_token = token_set.get("access_token")

    if not id_token:
        raise HTTPException(
            status_code=502, detail="Missing id_token in token response"
        )

    try:
        claims = verify_id_token_pyjwt(
            id_token=id_token,
            issuer=config.ii_issuer,
            audience=config.ii_client_id,
            expected_nonce=None,
            leeway=60,
        )
        if hydra_access_token:
            verify_at_hash_if_present(claims, hydra_access_token, alg="RS256")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=401, detail=f"ID token verification failed: {exc}"
        ) from exc

    email_claim = claims.get("email")
    email = (email_claim or "").strip().lower()
    if not email:
        raise HTTPException(status_code=502, detail="Email claim missing from ID token")

    email_verified = bool(claims.get("email_verified", False))
    first_name = claims.get("name").get("first") or ""
    last_name = claims.get("name").get("last") or ""
    picture = claims.get("picture") or None

    userinfo = None
    try:
        userinfo = await _fetch_userinfo_if_enabled(hydra_access_token)
    except HTTPException:
        # userinfo is optional; ignore failures to avoid blocking login
        userinfo = None

    if userinfo:
        first_name = userinfo.get("given_name") or first_name
        last_name = userinfo.get("family_name") or last_name
        picture = userinfo.get("picture") or picture

    if config.waitlist_enabled:
        waitlist_result = await db.execute(
            select(WaitlistEntry).where(func.lower(WaitlistEntry.email) == email)
        )
        waitlist_entry = waitlist_result.scalar_one_or_none()

        if not email.endswith("@ii.inc") and waitlist_entry is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Thank you for your interest. We’re currently in private beta and expanding access soon.",
            )

    result = await db.execute(select(User).where(func.lower(User.email) == email))
    user_stored = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)

    if not user_stored:
        new_user = User(
            id=str(uuid.uuid4()),
            email=email,
            first_name=first_name,
            last_name=last_name,
            avatar=picture,
            role="user",
            is_active=True,
            email_verified=email_verified,
            credits=config.default_user_credits,
            created_at=now,
            last_login_at=now,
            subscription_plan=config.default_subscription_plan,
            login_provider="ii",
        )
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)

        api_key = APIKey(
            id=str(uuid.uuid4()),
            user_id=new_user.id,
            api_key=generate_prefixed_api_key(),
            is_active=True,
            created_at=now,
        )
        db.add(api_key)
        await db.commit()

        user_stored = new_user
    else:
        user_stored.first_name = first_name or user_stored.first_name
        user_stored.last_name = last_name or user_stored.last_name
        user_stored.avatar = picture or user_stored.avatar
        user_stored.email_verified = user_stored.email_verified or email_verified
        user_stored.login_provider = "ii"
        user_stored.last_login_at = now
        await db.commit()
        await db.refresh(user_stored)

    access_token = jwt_handler.create_access_token(
        user_id=str(user_stored.id),
        email=str(user_stored.email),
        role=str(user_stored.role),
    )
    refresh_token = jwt_handler.create_refresh_token(user_id=str(user_stored.id))

    token_payload = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": jwt_handler.access_token_expire_minutes * 60,
    }

    request.session.pop(II_STATE_SESSION_KEY, None)
    request.session.pop(II_CODE_VERIFIER_SESSION_KEY, None)

    return_origin = request.session.pop(II_RETURN_TO_SESSION_KEY, None)
    return_url = request.session.pop(II_RETURN_URL_SESSION_KEY, None)

    token_json = json.dumps(token_payload)
    origin_json = json.dumps(return_origin or "")
    redirect_url_json = json.dumps(return_url or "")

    html_content = f"""
<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <title>II Login</title>
</head>
<body>
<script>
  (function() {{
    const payload = {token_json};
    const targetOrigin = {origin_json};
    const redirectUrl = {redirect_url_json};
    const message = {{ type: 'ii-auth-success', payload }};
    const fallbackOrigin = (() => {{
      if (targetOrigin) return targetOrigin;
      try {{
        if (redirectUrl) return new URL(redirectUrl).origin;
      }} catch (e) {{}}
      return window.location.origin;
    }})();

    function redirectWithHash() {{
      if (!redirectUrl) return;
      try {{
        const url = new URL(redirectUrl);
        url.hash = 'ii-auth=' + encodeURIComponent(JSON.stringify(payload));
        window.location.replace(url.toString());
      }} catch (e) {{
        window.location.replace(redirectUrl);
      }}
    }}

    try {{
      if (window.opener && !window.opener.closed) {{
        window.opener.postMessage(message, fallbackOrigin || '*');
        window.close();
        return;
      }}
    }} catch (err) {{
      console.error('postMessage to opener failed', err);
    }}

    if (redirectUrl) {{
      redirectWithHash();
      return;
    }}

    document.body.innerHTML = '<p>Login successful. You can close this window.</p>';
  }})();
</script>
</body>
</html>
"""

    return HTMLResponse(content=html_content)


@router.get("/oauth/google/login")
async def google_login():
    """Redirect to Google SSO login."""

    google_sso = GoogleSSO(
        config.google_client_id or "",
        config.google_client_secret or "",
        redirect_uri=config.google_redirect_uri,
    )
    async with google_sso:
        return await google_sso.get_login_redirect(
            params={"prompt": "consent", "access_type": "offline"}
        )


@router.get("/oauth/google/callback")
async def google_callback(
    request: Request,
    db: DBSession,
):
    """Handle Google SSO callback and login."""
    state = request.query_params.get("state")
    if state:
        serializer = URLSafeSerializer(config.session_secret_key)
        connector_state: Optional[dict[str, Any]] = None
        try:
            loaded_state = serializer.loads(state)
            if isinstance(loaded_state, dict):
                connector_state = loaded_state
        except BadSignature:
            connector_state = None

        if connector_state and connector_state.get("connector") == "google_drive":
            # Redirect to frontend route that handles both mobile and desktop flows
            code = request.query_params.get("code")
            error = request.query_params.get("error")
            error_description = request.query_params.get("error_description")

            # Get frontend URL from state or fall back to referer
            frontend_url = connector_state.get("frontend_url")
            if not frontend_url:
                # Try to extract from referer header
                referer = request.headers.get("referer")
                if referer:
                    from urllib.parse import urlparse
                    parsed = urlparse(referer)
                    frontend_url = f"{parsed.scheme}://{parsed.netloc}"

            if not frontend_url:
                raise HTTPException(
                    status_code=400,
                    detail="Could not determine frontend URL for redirect"
                )

            # Build query parameters for frontend redirect
            from urllib.parse import urlencode

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
        config.google_client_id or "",
        config.google_client_secret or "",
        redirect_uri=(url or config.google_redirect_uri),
    )
    async with google_sso:
        user_info = await google_sso.verify_and_process(request)
    if not user_info:
        raise ValueError("Failed to get user info from Google SSO")

    email = (user_info.email or "").strip().lower()
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email not provided by Google account",
        )
    if config.waitlist_enabled:
        waitlist_result = await db.execute(
            select(WaitlistEntry).where(func.lower(WaitlistEntry.email) == email)
        )
        waitlist_entry = waitlist_result.scalar_one_or_none()

        if not email.endswith("@ii.inc") and waitlist_entry is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Thank you for your interest. We’re currently in private beta and expanding access soon.",
            )

    result = await db.execute(select(User).where(func.lower(User.email) == email))
    user_stored = result.scalar_one_or_none()
    if not user_stored:
        # Register new user if not exists
        new_user = User(
            id=str(uuid.uuid4()),
            email=email,
            first_name=user_info.first_name or "",
            last_name=user_info.last_name or "",
            avatar=user_info.picture or None,
            role="user",
            is_active=True,
            email_verified=True,
            credits=config.default_user_credits,  # Initial signup credits from config
            bonus_credits=(
                config.beta_program_bonus_credits
                if config.beta_program_enabled
                else 0.0
            ),
            created_at=datetime.now(timezone.utc),
            subscription_plan=config.default_subscription_plan,
            login_provider="google",
        )
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)

        # Generate API key for the new user
        api_key = APIKey(
            id=str(uuid.uuid4()),
            user_id=new_user.id,
            api_key=generate_prefixed_api_key(),
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        db.add(api_key)
        await db.commit()
        user_stored = new_user

    access_token = jwt_handler.create_access_token(
        user_id=str(user_stored.id),
        email=str(user_stored.email),
        role=str(user_stored.role),
    )

    refresh_token = jwt_handler.create_refresh_token(user_id=str(user_stored.id))

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=jwt_handler.access_token_expire_minutes * 60,
    )


@router.get("/me", response_model=UserPublic)
async def reader_user_me(current_user: CurrentUser) -> Any:
    return current_user


@router.get("/dev/login")
async def dev_login(db: DBSession) -> TokenResponse:
    """Development-only login endpoint.

    Creates a token for the admin user without external OAuth.
    Only available when DEV_AUTH_ENABLED=true environment variable is set.
    """
    import os

    if os.getenv("DEV_AUTH_ENABLED", "").lower() != "true":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dev login is not enabled. Set DEV_AUTH_ENABLED=true to enable.",
        )

    # Get or create admin user
    admin_user = (
        await db.execute(select(User).filter(User.email == "admin@ii.inc"))
    ).scalar_one_or_none()

    if not admin_user:
        admin_user = User(
            id="admin",
            email="admin@ii.inc",
            first_name="Admin",
            last_name="User",
            role="admin",
            is_active=True,
            email_verified=True,
            credits=1000.0,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(admin_user)
        await db.commit()
        await db.refresh(admin_user)

    # Create tokens
    access_token = jwt_handler.create_access_token(
        user_id=admin_user.id,
        email=admin_user.email,
        role=admin_user.role or "admin",
    )
    refresh_token = jwt_handler.create_refresh_token(user_id=admin_user.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=jwt_handler.access_token_expire_minutes * 60,
    )
