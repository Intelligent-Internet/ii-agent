"""Per-client agent factories and shared building blocks.

Each subpackage under ``clients/`` (e.g. ``browser_extension``) wires the
standard ii-agent runtime to a specific external client. The modules
sitting directly under this package are generic helpers reused across all
clients — keep client-specific quirks inside the subpackage.
"""
