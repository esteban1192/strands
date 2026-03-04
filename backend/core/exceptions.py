"""
Domain-specific exceptions for the core layer.
"""


class CoreException(Exception):
    """Base exception for all core-layer errors."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class MCPConnectionError(CoreException):
    """Raised when we cannot connect to an MCP server."""
    pass


class MCPSyncError(CoreException):
    """Raised when tool synchronisation from an MCP server fails."""
    pass


class UnsupportedTransportError(CoreException):
    """Raised when an MCP has a transport_type we don't support yet."""
    pass
