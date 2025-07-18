from abc import ABC, abstractmethod
from typing import Any

class BaseTool(ABC):
    name: str
    description: str

    @abstractmethod
    def run_impl(self, *args, **kwargs) -> Any:
        raise NotImplementedError