from enum import Enum


UPLOAD_FOLDER_NAME = "uploaded_files"
COMPLETE_MESSAGE = "Completed the task."
DEFAULT_MODEL = "claude-sonnet-4@20250514"

TOKEN_BUDGET = 120_000
SUMMARY_MAX_TOKENS = 32_000
VISIT_WEB_PAGE_MAX_OUTPUT_LENGTH = 40_000


class WorkSpaceMode(Enum):
    DOCKER = "docker"
    E2B = "e2b"
    LOCAL = "local"

    def __str__(self):
        return self.value


# MiniMax model constants
MINIMAX_API_BASE_URL = "https://api.minimax.io/v1"
MINIMAX_DEFAULT_MODEL = "MiniMax-M2.7"


def is_minimax_family(model_name: str) -> bool:
    """Check if a model belongs to the MiniMax family."""
    if not model_name:
        return False
    return "minimax" in model_name.lower()
