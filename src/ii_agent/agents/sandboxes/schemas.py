"""Pydantic schemas (DTOs) for sandboxes domain."""

from datetime import datetime
from enum import Enum
import mimetypes
import os
from typing import IO, Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict


class SandboxStatus(str, Enum):
    """Sandbox lifecycle status values."""

    NOT_INITIALIZED = "not_initialized"
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    DELETED = "deleted"
    ERROR = "error"


class FileUpload(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    path: str
    content: str | bytes | IO


class SandboxInfo(BaseModel):
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat() if v else None})

    id: str
    provider: str
    session_id: str
    status: SandboxStatus
    vscode_url: Optional[str] = None
    vnc_url: Optional[str] = None
    expired_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(exclude_none=True, mode="json")


class SandboxFileInfo(BaseModel):
    """Information about a written file in the sandbox."""

    name: str
    type: Literal["file", "dir"]
    path: str


class FileTreeNode(BaseModel):
    """A node in the file tree (file or directory)."""

    name: str
    path: str
    type: Literal["file", "directory"]
    children: Optional[List["FileTreeNode"]] = None
    size: Optional[int] = None


class FileChangeEvent(BaseModel):
    """A filesystem change event from the sandbox watcher."""

    type: Literal["create", "write", "remove", "rename"]
    path: str
    name: str


class FileContentResponse(BaseModel):
    """Response containing file content and detected language."""

    path: str
    content: str | None = None
    language: str | None = None
    file_kind: Literal["text", "image", "binary"] = "text"
    mime_type: str | None = None
    message: str | None = None
    too_big: bool = False


# Directories to exclude from file tree listings
EXCLUDED_DIRS = frozenset(
    {
        "node_modules",
        ".git",
        ".next",
        "__pycache__",
        ".cache",
        "dist",
        "build",
        ".venv",
        "venv",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        "coverage",
        ".turbo",
        ".ii_app",
        ".ii-app",
        "logs",
    }
)

# Directory names under WATCH_ROOT to ignore in watcher events.
# Events for these directories and their descendants are silently dropped
# so that high-frequency writes (e.g. log streaming, npm install) don't flood the client.
WATCHER_IGNORED_DIRS = (
    ".ii_app",
    ".ii-app",
    "logs",
    "node_modules",
    ".next",
    ".git",
    "__pycache__",
    ".cache",
    ".venv",
    "venv",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "coverage",
    ".turbo",
    "dist",
    "build",
)
WATCHER_IGNORED_PATHS = frozenset(f"/workspace/{directory}" for directory in WATCHER_IGNORED_DIRS)
WATCHER_IGNORED_PREFIXES = tuple(f"{path}/" for path in WATCHER_IGNORED_PATHS)

# Map file extensions to language identifiers for syntax highlighting
EXTENSION_TO_LANGUAGE = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "jsx",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".json": "json",
    ".md": "markdown",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".sql": "sql",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".dockerfile": "dockerfile",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".xml": "xml",
    ".svg": "xml",
    ".graphql": "graphql",
    ".prisma": "prisma",
    ".env": "bash",
    ".gitignore": "bash",
    ".txt": "plaintext",
}

# Max file size in bytes for content display (500KB)
MAX_FILE_CONTENT_SIZE = 512_000

# Max file size in bytes for inline pre-fetch during tree load (50KB)
INLINE_CONTENT_MAX_SIZE = 50_000

# Max total bytes to pre-fetch across all files during tree load (2MB)
INLINE_CONTENT_TOTAL_MAX = 2_000_000

# Eagerly inline root-level files plus one nested directory layer.
# The tree root itself is depth 0, so grandchildren files are depth 2.
INLINE_CONTENT_PREFETCH_DEPTH = 2

# Binary file extensions that should never be read as text
BINARY_EXTENSIONS = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".bmp",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".otf",
        ".zip",
        ".tar",
        ".gz",
        ".bz2",
        ".7z",
        ".rar",
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".mp3",
        ".mp4",
        ".wav",
        ".avi",
        ".mov",
        ".webm",
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".bin",
        ".pyc",
        ".pyo",
        ".class",
        ".o",
        ".obj",
        ".lock",
    }
)

IMAGE_EXTENSIONS = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".bmp",
        ".svg",
        ".avif",
        ".apng",
        ".tif",
        ".tiff",
        ".heic",
        ".heif",
    }
)


def detect_language(file_path: str) -> str:
    """Detect language from file extension."""
    _, ext = os.path.splitext(file_path.lower())
    # Handle dotfiles like Dockerfile, Makefile
    basename = os.path.basename(file_path).lower()
    if basename == "dockerfile":
        return "dockerfile"
    if basename == "makefile":
        return "makefile"
    return EXTENSION_TO_LANGUAGE.get(ext, "plaintext")


def guess_mime_type(file_path: str) -> str | None:
    """Guess the MIME type for a sandbox file path."""

    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type:
        return mime_type

    _, ext = os.path.splitext(file_path.lower())
    return {
        ".svg": "image/svg+xml",
        ".avif": "image/avif",
        ".apng": "image/apng",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
        ".heic": "image/heic",
        ".heif": "image/heif",
    }.get(ext)


def is_svg_file_path(file_path: str) -> bool:
    """Return whether the file path points to an SVG file."""

    _, ext = os.path.splitext(file_path.lower())
    return ext == ".svg" or guess_mime_type(file_path) == "image/svg+xml"


def is_image_file_path(file_path: str, *, include_svg: bool = True) -> bool:
    """Return whether the file path points to an image file."""

    mime_type = guess_mime_type(file_path)
    _, ext = os.path.splitext(file_path.lower())
    is_image = (mime_type is not None and mime_type.startswith("image/")) or ext in IMAGE_EXTENSIONS
    if not is_image:
        return False
    if include_svg:
        return True
    return not is_svg_file_path(file_path)


def is_binary_file_path(file_path: str) -> bool:
    """Return whether the file path should be treated as binary."""

    if is_image_file_path(file_path, include_svg=False):
        return True

    _, ext = os.path.splitext(file_path.lower())
    return ext in BINARY_EXTENSIONS


SandboxProvider = Literal["e2b", "docker"]
