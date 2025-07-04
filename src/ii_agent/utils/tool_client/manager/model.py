from dataclasses import dataclass


@dataclass
class SessionResult:
    success: bool
    output: str


@dataclass
class StrReplaceResponse:
    success: bool
    file_content: str


@dataclass
class StrReplaceToolError(Exception):
    message: str

    def __str__(self):
        return self.message
