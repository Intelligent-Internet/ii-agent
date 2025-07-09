"""CLI utility functions for ii-agent."""

import hashlib
import uuid
from typing import Optional, Dict, Any

from ii_agent.events.event import Event
from ii_agent.events.action import Action
from ii_agent.events.observation import Observation
from ii_agent.core.config.ii_agent_config import IIAgentConfig

from .tui import UsageMetrics


def generate_sid(config: IIAgentConfig, session_name: Optional[str] = None) -> str:
    """Generate a session ID."""
    if session_name:
        # Create deterministic UUID from session name
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, session_name))
    else:
        # Create random UUID
        return str(uuid.uuid4())


def update_usage_metrics(event: Event, usage_metrics: UsageMetrics):
    """Update usage metrics based on event."""
    if hasattr(event, 'metadata') and event.metadata:
        metadata = event.metadata
        
        # Update token counts if available
        if 'input_tokens' in metadata:
            usage_metrics.input_tokens += metadata['input_tokens']
        
        if 'output_tokens' in metadata:
            usage_metrics.output_tokens += metadata['output_tokens']
        
        # Update cost if available
        if 'cost' in metadata:
            usage_metrics.total_cost += metadata['cost']
    
    # Estimate tokens if not provided (rough estimation)
    if isinstance(event, Action) and hasattr(event, 'content'):
        if event.content:
            estimated_tokens = len(event.content.split()) * 1.3  # Rough token estimation
            usage_metrics.input_tokens += int(estimated_tokens)
    
    if isinstance(event, Observation) and hasattr(event, 'content'):
        if event.content:
            estimated_tokens = len(event.content.split()) * 1.3  # Rough token estimation
            usage_metrics.output_tokens += int(estimated_tokens)


def format_session_id(session_id: str) -> str:
    """Format session ID for display."""
    if len(session_id) > 8:
        return session_id[:8] + '...'
    return session_id


def truncate_text(text: str, max_length: int = 100) -> str:
    """Truncate text to specified length."""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + '...'


def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe file operations."""
    # Remove or replace unsafe characters
    unsafe_chars = '<>:"/\\|?*'
    for char in unsafe_chars:
        filename = filename.replace(char, '_')
    
    # Remove leading/trailing spaces and dots
    filename = filename.strip(' .')
    
    # Ensure filename isn't empty
    if not filename:
        filename = 'untitled'
    
    return filename


def calculate_content_hash(content: str) -> str:
    """Calculate hash of content for caching/comparison."""
    return hashlib.md5(content.encode('utf-8')).hexdigest()


def parse_command_with_args(command: str) -> tuple[str, list[str]]:
    """Parse command string into command and arguments."""
    parts = command.strip().split()
    if not parts:
        return '', []
    
    cmd = parts[0]
    args = parts[1:] if len(parts) > 1 else []
    return cmd, args


def format_file_size(size_bytes: int) -> str:
    """Format file size in human readable format."""
    if size_bytes == 0:
        return '0 B'
    
    size_names = ['B', 'KB', 'MB', 'GB', 'TB']
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024
        i += 1
    
    return f'{size_bytes:.1f} {size_names[i]}'


def estimate_token_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    """Estimate cost based on token usage and model."""
    # Rough cost estimates (USD per 1K tokens)
    cost_per_1k = {
        'gpt-4o': {'input': 0.005, 'output': 0.015},
        'gpt-4o-mini': {'input': 0.0015, 'output': 0.0060},
        'gpt-4-turbo': {'input': 0.01, 'output': 0.03},
        'gpt-3.5-turbo': {'input': 0.0015, 'output': 0.002},
        'claude-3-5-sonnet-20241022': {'input': 0.003, 'output': 0.015},
        'claude-3-opus-20240229': {'input': 0.015, 'output': 0.075},
        'claude-3-haiku-20240307': {'input': 0.0025, 'output': 0.0125},
        'gemini-1.5-pro': {'input': 0.00125, 'output': 0.005},
        'gemini-1.5-flash': {'input': 0.00075, 'output': 0.003},
    }
    
    if model in cost_per_1k:
        rates = cost_per_1k[model]
        input_cost = (input_tokens / 1000) * rates['input']
        output_cost = (output_tokens / 1000) * rates['output']
        return input_cost + output_cost
    
    # Default estimation if model not recognized
    return (input_tokens / 1000) * 0.001 + (output_tokens / 1000) * 0.002


def validate_session_name(name: str) -> bool:
    """Validate session name format."""
    if not name or not name.strip():
        return False
    
    # Check length
    if len(name) > 100:
        return False
    
    # Check for invalid characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        if char in name:
            return False
    
    return True


def get_system_info() -> Dict[str, Any]:
    """Get system information for diagnostics."""
    import platform
    import sys
    
    return {
        'platform': platform.system(),
        'platform_version': platform.version(),
        'python_version': sys.version,
        'python_executable': sys.executable,
        'architecture': platform.machine(),
    }


def format_duration(seconds: float) -> str:
    """Format duration in human readable format."""
    if seconds < 60:
        return f'{seconds:.1f}s'
    elif seconds < 3600:
        minutes = seconds / 60
        return f'{minutes:.1f}m'
    else:
        hours = seconds / 3600
        return f'{hours:.1f}h'


def clean_ansi_codes(text: str) -> str:
    """Remove ANSI escape codes from text."""
    import re
    ansi_escape = re.compile(r'\\x1B(?:[@-Z\\\\-_]|\\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)


def is_interactive_terminal() -> bool:
    """Check if running in an interactive terminal."""
    import sys
    return sys.stdout.isatty() and sys.stdin.isatty()


def get_terminal_size() -> tuple[int, int]:
    """Get terminal size (width, height)."""
    import os
    try:
        size = os.get_terminal_size()
        return size.columns, size.lines
    except OSError:
        return 80, 24  # Default fallback


def setup_signal_handlers():
    """Setup signal handlers for graceful shutdown."""
    import signal
    import sys
    
    def signal_handler(signum, frame):
        print('\\nReceived interrupt signal. Shutting down gracefully...')
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def create_session_backup(session_id: str, data: Dict[str, Any]) -> str:
    """Create a backup of session data."""
    import json
    import os
    from datetime import datetime
    
    backup_dir = os.path.expanduser('~/.ii_agent/backups')
    os.makedirs(backup_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'session_{session_id[:8]}_{timestamp}.json'
    filepath = os.path.join(backup_dir, filename)
    
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2, default=str)
    
    return filepath


def load_session_backup(filepath: str) -> Dict[str, Any]:
    """Load session data from backup file."""
    import json
    
    with open(filepath, 'r') as f:
        return json.load(f)


def cleanup_old_backups(max_backups: int = 10):
    """Clean up old backup files."""
    import os
    import glob
    
    backup_dir = os.path.expanduser('~/.ii_agent/backups')
    if not os.path.exists(backup_dir):
        return
    
    # Get all backup files sorted by modification time
    backup_files = glob.glob(os.path.join(backup_dir, 'session_*.json'))
    backup_files.sort(key=os.path.getmtime, reverse=True)
    
    # Remove old backups
    for backup_file in backup_files[max_backups:]:
        try:
            os.remove(backup_file)
        except OSError:
            pass


def validate_file_path(filepath: str) -> bool:
    """Validate file path for security."""
    import os
    
    # Normalize path
    filepath = os.path.normpath(filepath)
    
    # Check for path traversal attempts
    if '..' in filepath or filepath.startswith('/'):
        return False
    
    # Check for absolute paths
    if os.path.isabs(filepath):
        return False
    
    return True


def safe_file_read(filepath: str, max_size: int = 1024 * 1024) -> Optional[str]:
    """Safely read file with size limit."""
    import os
    
    if not validate_file_path(filepath):
        return None
    
    if not os.path.exists(filepath):
        return None
    
    # Check file size
    if os.path.getsize(filepath) > max_size:
        return None
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except (IOError, UnicodeDecodeError):
        return None


def get_available_models() -> Dict[str, list[str]]:
    """Get list of available models by provider."""
    return {
        'OpenAI': [
            'gpt-4o',
            'gpt-4o-mini',
            'gpt-4-turbo',
            'gpt-3.5-turbo',
        ],
        'Anthropic': [
            'claude-3-5-sonnet-20241022',
            'claude-3-opus-20240229',
            'claude-3-haiku-20240307',
        ],
        'Google': [
            'gemini-1.5-pro',
            'gemini-1.5-flash',
            'gemini-pro',
        ],
    }


def detect_model_provider(model: str) -> str:
    """Detect provider from model name."""
    if model.startswith('gpt-'):
        return 'OpenAI'
    elif model.startswith('claude-'):
        return 'Anthropic'
    elif model.startswith('gemini-'):
        return 'Google'
    else:
        return 'Unknown'