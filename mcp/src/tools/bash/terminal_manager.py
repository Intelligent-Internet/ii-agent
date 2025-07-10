from abc import ABC, abstractmethod
from typing import List
from data

class TerminalManager(ABC):
    @abstractmethod
    def create_session(self, session_name: str, base_dir: str):
        pass

    @abstractmethod
    def run_command(self, session_name: str, command: str, run_dir: str, timeout: int):
        pass

    @abstractmethod
    def get_session_output(self, session_name: str):
        pass

    @abstractmethod
    def delete_session(self, session_name: str):
        pass

    @abstractmethod
    def get_all_sessions(self) -> List[str]:
        pass


class TmuxTerminalManager(TerminalManager):