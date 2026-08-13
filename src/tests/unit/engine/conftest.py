"""
Engine-level test configuration.

Patches broken imports in google.genai.interactions before any test module
imports the source under test. The installed google-genai SDK may not export
InteractionEvent from google.genai.interactions, but the source
file interactions.py tries to import it. We inject a compatible replacement
so the source module can be imported for testing.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _reset_host_monitor_state():
    """Reset the process-global host-monitor state between tests.

    Several tests (host_monitor + host_monitor_integration + sandbox
    service tests) mutate ``host_monitor`` module-level state via
    ``set_host_state(...)``. Without a teardown the OK/WARN/CRIT value
    leaks across tests and creates ordering-dependent failures.
    """
    yield
    try:
        from ii_agent.agents.sandboxes import host_monitor as _hm

        _hm.set_host_state(_hm.HostHealthState.OK, None)
    except Exception:
        # If the module isn't importable in some context, the leak is
        # harmless because no other test could have set state either.
        pass


# Ensure google.genai.interactions has the InteractionEvent attribute
# that the engine/runtime source code expects
try:
    import google.genai.interactions as _gi_module

    if not hasattr(_gi_module, "InteractionEvent"):
        # Create a stub class that can be used in isinstance() checks
        _gi_module.InteractionEvent = type("InteractionEvent", (), {})  # type: ignore[attr-defined]

    # Also ensure InteractionStartEvent and InteractionCompleteEvent exist
    if not hasattr(_gi_module, "InteractionStartEvent"):
        _gi_module.InteractionStartEvent = type("InteractionStartEvent", (), {})  # type: ignore[attr-defined]
    if not hasattr(_gi_module, "InteractionCompleteEvent"):
        _gi_module.InteractionCompleteEvent = type("InteractionCompleteEvent", (), {})  # type: ignore[attr-defined]
except ImportError:
    # If the entire module is missing, create a mock
    _mock_module = MagicMock()
    _mock_module.InteractionEvent = type("InteractionEvent", (), {})
    _mock_module.InteractionStartEvent = type("InteractionStartEvent", (), {})
    _mock_module.InteractionCompleteEvent = type("InteractionCompleteEvent", (), {})
    sys.modules["google.genai.interactions"] = _mock_module
