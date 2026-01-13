"""Unit tests for ii_tool.interfaces.sandbox module.

This module tests the abstract sandbox interface:
- SandboxInterface ABC
- expose_port abstract method
"""

import pytest
from abc import ABC

from ii_tool.interfaces.sandbox import SandboxInterface


# =============================================================================
# SandboxInterface ABC Tests
# =============================================================================

class TestSandboxInterface:
    """Tests for SandboxInterface abstract base class."""

    def test_is_abstract_class(self):
        """SandboxInterface is an ABC."""
        assert issubclass(SandboxInterface, ABC)

    def test_cannot_instantiate_directly(self):
        """SandboxInterface cannot be instantiated directly."""
        with pytest.raises(TypeError) as exc_info:
            SandboxInterface()
        assert "abstract" in str(exc_info.value).lower()

    def test_expose_port_is_abstract(self):
        """expose_port method is abstract."""
        # Check that expose_port is in __abstractmethods__
        assert "expose_port" in SandboxInterface.__abstractmethods__

    def test_get_available_ports_has_default(self):
        """get_available_ports has a default implementation returning None."""
        # get_available_ports is NOT abstract - it has a default implementation
        assert "get_available_ports" not in SandboxInterface.__abstractmethods__


# =============================================================================
# Concrete Implementation Tests
# =============================================================================

class TestConcreteImplementation:
    """Tests for concrete implementations of SandboxInterface."""

    def test_concrete_class_can_be_created(self):
        """A concrete implementation can be instantiated."""
        
        class ConcreteSandbox(SandboxInterface):
            async def expose_port(self, port: int) -> str:
                return f"http://localhost:{port}"
        
        sandbox = ConcreteSandbox()
        assert isinstance(sandbox, SandboxInterface)

    def test_get_available_ports_default_returns_none(self):
        """Default get_available_ports returns None (any port allowed)."""
        
        class ConcreteSandbox(SandboxInterface):
            async def expose_port(self, port: int) -> str:
                return f"http://localhost:{port}"
        
        sandbox = ConcreteSandbox()
        # Default implementation returns None (cloud mode - any port)
        assert sandbox.get_available_ports() is None

    def test_get_available_ports_can_be_overridden(self):
        """get_available_ports can be overridden to return restricted ports."""
        
        class RestrictedPortSandbox(SandboxInterface):
            async def expose_port(self, port: int) -> str:
                return f"http://localhost:{port}"
            
            def get_available_ports(self):
                return [3000, 5173, 8080]
        
        sandbox = RestrictedPortSandbox()
        available = sandbox.get_available_ports()
        assert available == [3000, 5173, 8080]
        assert 8000 not in available

    @pytest.mark.asyncio
    async def test_expose_port_returns_url(self):
        """expose_port returns a URL string."""
        
        class MockSandbox(SandboxInterface):
            async def expose_port(self, port: int) -> str:
                return f"https://sandbox.example.com:{port}"
        
        sandbox = MockSandbox()
        url = await sandbox.expose_port(8080)
        assert url == "https://sandbox.example.com:8080"

    @pytest.mark.asyncio
    async def test_expose_port_accepts_various_ports(self):
        """expose_port accepts various port numbers."""
        
        class MockSandbox(SandboxInterface):
            async def expose_port(self, port: int) -> str:
                return f"http://test:{port}"
        
        sandbox = MockSandbox()
        
        # Standard ports
        assert await sandbox.expose_port(80) == "http://test:80"
        assert await sandbox.expose_port(443) == "http://test:443"
        assert await sandbox.expose_port(8080) == "http://test:8080"
        
        # High ports
        assert await sandbox.expose_port(30000) == "http://test:30000"
        assert await sandbox.expose_port(65535) == "http://test:65535"

    def test_missing_expose_port_raises(self):
        """Implementation without expose_port cannot be instantiated."""
        
        with pytest.raises(TypeError) as exc_info:
            class IncompleteSandbox(SandboxInterface):
                pass
            
            IncompleteSandbox()
        
        assert "abstract" in str(exc_info.value).lower()


# =============================================================================
# Interface Contract Tests
# =============================================================================

class TestInterfaceContract:
    """Tests verifying the interface contract."""

    def test_expose_port_signature(self):
        """expose_port has correct signature (port: int) -> str."""
        import inspect
        
        sig = inspect.signature(SandboxInterface.expose_port)
        params = list(sig.parameters.keys())
        
        # Should have self and port
        assert "self" in params
        assert "port" in params

    def test_interface_is_async(self):
        """expose_port is an async method."""
        import inspect
        
        assert inspect.iscoroutinefunction(SandboxInterface.expose_port)

    @pytest.mark.asyncio
    async def test_implementation_can_add_logic(self):
        """Implementation can add custom logic."""
        
        class LoggingSandbox(SandboxInterface):
            def __init__(self):
                self.exposed_ports = []
            
            async def expose_port(self, port: int) -> str:
                self.exposed_ports.append(port)
                return f"http://logged:{port}"
        
        sandbox = LoggingSandbox()
        await sandbox.expose_port(8080)
        await sandbox.expose_port(3000)
        
        assert sandbox.exposed_ports == [8080, 3000]

    @pytest.mark.asyncio
    async def test_implementation_can_raise_exceptions(self):
        """Implementation can raise exceptions."""
        
        class RestrictedSandbox(SandboxInterface):
            async def expose_port(self, port: int) -> str:
                if port < 1024:
                    raise PermissionError(f"Cannot expose privileged port {port}")
                return f"http://restricted:{port}"
        
        sandbox = RestrictedSandbox()
        
        # Should work for high ports
        url = await sandbox.expose_port(8080)
        assert "8080" in url
        
        # Should raise for low ports
        with pytest.raises(PermissionError):
            await sandbox.expose_port(80)
