"""Browser-extension client for the ii-browser Chrome extension.

Sub-package of :mod:`ii_agent.clients` so it ships with the standard
distribution. The pieces this package owns are:

* :mod:`ii_agent.clients.browser_extension.factory` — builds an
  :class:`IIAgent` with extension-side overrides for system prompt and
  tool/skill subset, delegating capability assembly to the shared
  :mod:`ii_agent.clients.proxy_capabilities` helpers.

The Pydantic content schemas (``BrowserExtensionCommandContent`` /
``BrowserExtensionContinueRunContent``) live in
:mod:`ii_agent.realtime.schemas` next to every other ``CommandContent``
variant. The Socket.IO handlers live in
:mod:`ii_agent.realtime.handlers.browser_extension_query` and
:mod:`ii_agent.realtime.handlers.browser_extension_continue_run`, and are
registered by ``ii_agent.realtime.handlers.factory.CommandHandlerFactory``.
"""

from ii_agent.clients.browser_extension.factory import browser_extension_agent_factory

__all__ = ["browser_extension_agent_factory"]
