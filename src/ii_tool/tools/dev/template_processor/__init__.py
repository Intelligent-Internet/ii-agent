# Import all processors to ensure their decorators run and register them
from .nextjs_shadcn import NextShadcnProcessor
from .react_tailwind_python import ReactTailwindPythonProcessor

# Export the registry for easy access
from .registry import WebProcessorRegistry

__all__ = [
    "WebProcessorRegistry",
    "NextShadcnProcessor",
    "ReactTailwindPythonProcessor",
]
