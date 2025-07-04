# Import all processors to ensure their decorators run and register them
from .next_shadcn_processor import NextShadcnProcessor
from .react_tailwind_python_processor import ReactTailwindPythonProcessor
from .react_vite_shadcn_processor import ReactViteShadcnProcessor

# Export the registry for easy access
from .web_processor_registry import WebProcessorRegistry

__all__ = [
    "WebProcessorRegistry",
    "NextShadcnProcessor",
    "ReactTailwindPythonProcessor",
    "ReactViteShadcnProcessor",
]
