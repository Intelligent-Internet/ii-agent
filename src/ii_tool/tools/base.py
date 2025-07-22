from abc import ABC, abstractmethod
from typing import Any

class BaseTool(ABC):
    name: str
    description: str
    read_only: bool

    @abstractmethod
    def run_impl(self, *args, **kwargs) -> Any:
        raise NotImplementedError