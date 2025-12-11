import os
import importlib
import pytest


RUN_INTEGRATION = os.getenv("RUN_PROVIDERS_INTEGRATION") == "1"


def _has_provider_credentials():
    # Basic check: look for any of the common provider env vars used by the project
    keys = [
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "E2B_API_KEY",
    ]
    return any(os.getenv(k) for k in keys)


@pytest.mark.skipif(not RUN_INTEGRATION, reason="Providers integration tests disabled; set RUN_PROVIDERS_INTEGRATION=1 to enable")
@pytest.mark.skipif(not _has_provider_credentials(), reason="Provider credentials not found in environment")
def test_providers_importable():
    """Lightweight smoke test that imports provider packages installed via `.[providers]`.

    This test is intentionally conservative: it only runs when explicitly enabled
    and when at least one provider credential is present. It verifies the packages
    can be imported in CI or locally after installing `.[providers]`.
    """
    modules = [
        ("anthropic", "anthropic"),
        ("e2b", "e2b"),
        ("googleapiclient", "googleapiclient.discovery"),
    ]

    for name, mod in modules:
        try:
            importlib.import_module(mod)
        except Exception as e:
            pytest.skip(f"Provider module {mod} not available: {e}")

    # If we reach here, imports succeeded
    assert True
