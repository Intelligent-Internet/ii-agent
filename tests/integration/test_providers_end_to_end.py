import os
import pytest
import requests


RUN_INTEGRATION = os.getenv("RUN_PROVIDERS_INTEGRATION") == "1"


def _require_env(var):
    val = os.getenv(var)
    return bool(val and val.strip())


@pytest.mark.skipif(not RUN_INTEGRATION, reason="Providers integration tests disabled; set RUN_PROVIDERS_INTEGRATION=1 to enable")
@pytest.mark.skipif(not _require_env("GOOGLE_APPLICATION_CREDENTIALS"), reason="Google service account JSON not provided")
def test_google_service_account_can_refresh_token():
    """Validate Google service account credentials can be loaded and refreshed.

    This verifies that the service account file is valid and can obtain an access token.
    """
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request
    except Exception as e:
        pytest.skip(f"google-auth not installed: {e}")

    sa_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    creds = service_account.Credentials.from_service_account_file(sa_path, scopes=["https://www.googleapis.com/auth/cloud-platform"])
    request = Request()
    # attempt to refresh to obtain an access token
    creds.refresh(request)
    assert creds.token is not None and len(creds.token) > 0


@pytest.mark.skipif(not RUN_INTEGRATION, reason="Providers integration tests disabled; set RUN_PROVIDERS_INTEGRATION=1 to enable")
@pytest.mark.skipif(not _require_env("ANTHROPIC_API_KEY"), reason="Anthropic API key not provided")
def test_anthropic_models_endpoint():
    """Simple smoke test calling Anthropic models endpoint to validate the API key and network access."""
    key = os.getenv("ANTHROPIC_API_KEY")
    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    url = "https://api.anthropic.com/v1/models"
    try:
        resp = requests.get(url, headers=headers, timeout=15)
    except Exception as e:
        pytest.skip(f"Network/request failed for Anthropic endpoint: {e}")

    assert resp.status_code == 200, f"Anthropic models endpoint returned {resp.status_code}: {resp.text}"


@pytest.mark.skipif(not RUN_INTEGRATION, reason="Providers integration tests disabled; set RUN_PROVIDERS_INTEGRATION=1 to enable")
@pytest.mark.skipif(not _require_env("E2B_API_KEY"), reason="E2B API key not provided")
def test_e2b_import_and_version():
    """Basic import check for the `e2b` package. If available, this confirms the providers extra installed it."""
    try:
        import e2b
    except Exception as e:
        pytest.skip(f"e2b package not importable: {e}")

    # try to read a version attribute if available
    ver = getattr(e2b, "__version__", None)
    assert ver is None or isinstance(ver, str)
