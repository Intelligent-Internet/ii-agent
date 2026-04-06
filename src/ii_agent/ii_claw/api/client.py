"""HTTP client for communicating with II-Claw Rust backend."""

import httpx
from ii_agent.core.config.settings import get_settings

_client: httpx.AsyncClient | None = None


def _auth_headers() -> dict[str, str]:
    """Build Authorization header if II-Claw API key is configured."""
    settings = get_settings()
    if settings.ii_claw_client_api_key:
        return {"Authorization": f"Bearer {settings.ii_claw_client_api_key}"}
    return {}


async def get_client() -> httpx.AsyncClient:
    """Get or create a shared async HTTP client."""
    global _client
    if _client is None or _client.is_closed:
        settings = get_settings()
        _client = httpx.AsyncClient(
            base_url=settings.ii_claw_client_url,
            headers=_auth_headers(),
            timeout=30.0,
        )
    return _client


async def close_client():
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None


# ---------------------------------------------------------------------------
# Proxy helpers — forward Frontend requests to II-Claw
# ---------------------------------------------------------------------------

async def proxy_get(path: str, params: dict | None = None) -> httpx.Response:
    """Proxy a GET request to II-Claw."""
    client = await get_client()
    return await client.get(path, params=params)


async def proxy_post(path: str, json: dict | None = None) -> httpx.Response:
    """Proxy a POST request to II-Claw."""
    client = await get_client()
    return await client.post(path, json=json)


async def proxy_put(path: str, json: dict | None = None) -> httpx.Response:
    """Proxy a PUT request to II-Claw."""
    client = await get_client()
    return await client.put(path, json=json)


async def proxy_delete(path: str) -> httpx.Response:
    """Proxy a DELETE request to II-Claw."""
    client = await get_client()
    return await client.delete(path)


# ---------------------------------------------------------------------------
# Outbound: send messages to channels via II-Claw
# ---------------------------------------------------------------------------

async def send_to_user_channel(
    user_id: str,
    channel_name: str,
    recipient: str,
    *,
    text: str | None = None,
    image_url: str | None = None,
    file_url: str | None = None,
    filename: str | None = None,
    voice_url: str | None = None,
    video_url: str | None = None,
    caption: str | None = None,
    thread_id: str | None = None,
) -> dict:
    """Send a message via a user-scoped channel instance.

    Proxies to /api/users/{user_id}/channels/{name}/send.
    """
    body: dict = {"recipient": recipient}
    if text:
        body["message"] = text
    if image_url:
        body["image_url"] = image_url
    if file_url:
        body["file_url"] = file_url
    if filename:
        body["filename"] = filename
    if voice_url:
        body["voice_url"] = voice_url
    if video_url:
        body["video_url"] = video_url
    if caption:
        body["caption"] = caption
    if thread_id:
        body["thread_id"] = thread_id

    client = await get_client()
    resp = await client.post(
        f"/api/users/{user_id}/channels/{channel_name}/send", json=body
    )
    if resp.status_code >= 400:
        error_detail = resp.text
        raise httpx.HTTPStatusError(
            f"II-Claw error {resp.status_code}: {error_detail}",
            request=resp.request,
            response=resp,
        )
    return resp.json()
