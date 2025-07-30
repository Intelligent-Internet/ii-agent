"""Constants for tool configurations matching Claude Code specifications."""

# File system constants - PRODUCTION SECURITY LIMITS
MAX_FILES_LS = 1000
MAX_FILE_READ_LINES = 2000
MAX_LINE_LENGTH = 2000
DEFAULT_TIMEOUT_MS = 120000  # 2 minutes
MAX_TIMEOUT_MS = 600000  # 10 minutes
MAX_OUTPUT_CHARS = 30000

# Security and performance limits
MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024  # 100MB - prevent memory exhaustion
MAX_CONTENT_SIZE_BYTES = 50 * 1024 * 1024  # 50MB - for content operations
MAX_DIRECTORY_DEPTH = 20  # Prevent excessive traversal
MAX_CONCURRENT_OPERATIONS = 5  # Limit concurrent file operations
FILE_OPERATION_TIMEOUT = 30.0  # seconds
ENCODING_DETECTION_SAMPLE_SIZE = 8192  # bytes to read for encoding detection

# Workspace security
ALLOWED_FILE_EXTENSIONS = {
    '.txt', '.md', '.py', '.js', '.ts', '.tsx', '.jsx', '.json', '.xml', '.html', 
    '.css', '.scss', '.sass', '.yml', '.yaml', '.toml', '.ini', '.cfg', '.conf',
    '.sh', '.bash', '.zsh', '.fish', '.ps1', '.bat', '.cmd', '.sql', '.go', '.rs',
    '.java', '.kt', '.scala', '.rb', '.php', '.swift', '.dart', '.vue', '.svelte'
}

RESTRICTED_DIRECTORIES = {'.git', '.ssh', '.aws', '.docker', 'node_modules', '__pycache__'}
RESTRICTED_FILE_PATTERNS = {'*.key', '*.pem', '*.crt', '*.p12', '*.pfx', 'id_rsa*', 'id_dsa*'}

# Search constants
MAX_SEARCH_FILES = 1000
MAX_MATCHES_PER_FILE = 10
MAX_TOTAL_MATCHES = 100
MAX_GLOB_RESULTS = 100

# Notebook constants
NOTEBOOK_EXTENSIONS = ['.ipynb']
SUPPORTED_CELL_TYPES = ['code', 'markdown', 'raw']
EDIT_MODES = ['replace', 'insert', 'delete']

# Binary file extensions to skip in searches
BINARY_EXTENSIONS = {
    '.exe', '.bin', '.dll', '.so', '.dylib', '.class', '.jar', '.war',
    '.zip', '.tar', '.gz', '.7z', '.rar', '.pdf', '.doc', '.docx',
    '.xls', '.xlsx', '.ppt', '.pptx', '.jpg', '.jpeg', '.png', '.gif',
    '.bmp', '.ico', '.mp3', '.mp4', '.avi', '.mov', '.wmv', '.flv',
    '.webm', '.mkv'
}

# Web search constants
MIN_QUERY_LENGTH = 2
WEB_SEARCH_US_ONLY = True

# Agent tool constants
AGENT_AVAILABLE_TOOLS = [
    'Bash', 'Glob', 'Grep', 'LS', 'exit_plan_mode', 'Read', 'Edit', 
    'MultiEdit', 'Write', 'NotebookRead', 'NotebookEdit', 'WebFetch', 
    'TodoRead', 'TodoWrite', 'WebSearch', 'mcp__ide__getDiagnostics', 
    'mcp__ide__executeCode'
]

# Todo management constants
TODO_STATES = ['pending', 'in_progress', 'completed']
TODO_PRIORITIES = ['high', 'medium', 'low']
MAX_TODOS_IN_PROGRESS = 1