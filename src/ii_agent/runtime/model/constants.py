from enum import Enum


class RuntimeMode(Enum):
    DOCKER = "docker"
    LOCAL = "local"
    E2B = "e2b"
