"""
File path autocompletion for CLI.

This module provides file path autocompletion when typing @file_path syntax.
"""

from pathlib import Path
from typing import List, Iterator
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document


class FilePathCompleter(Completer):
    """Completer for @file_path syntax with intelligent file suggestions."""
    
    def __init__(self, workspace_path: str):
        self.workspace_path = Path(workspace_path)
    
    def get_completions(self, document: Document, complete_event) -> Iterator[Completion]:
        """Get file path completions when @ syntax is detected."""
        text = document.text_before_cursor
        
        # Check if we're in @file_path context
        at_index = text.rfind('@')
        if at_index == -1:
            return
        
        # Extract the path part after @
        path_part = text[at_index + 1:]
        
        # Don't complete if there's a space after @ (means it's not a file path)
        if ' ' in path_part and not path_part.strip():
            return
        
        # Get suggestions
        suggestions = self._get_file_suggestions(path_part)
        
        for suggestion in suggestions:
            yield Completion(
                suggestion,
                start_position=-len(path_part),
                display_meta=self._get_file_meta(suggestion),
                style='class:file-completion'
            )
    
    def _get_file_suggestions(self, partial_path: str) -> List[str]:
        """Get file suggestions based on partial path."""
        suggestions = []
        
        try:
            if not partial_path:
                # Show common directories and files in workspace
                suggestions.extend(self._get_workspace_suggestions())
            elif '/' in partial_path:
                # Handle nested paths
                suggestions.extend(self._get_nested_path_suggestions(partial_path))
            else:
                # Handle partial filename/dirname matching
                suggestions.extend(self._get_matching_suggestions(partial_path))
        except Exception:
            # Fallback to workspace suggestions if there's an error
            suggestions.extend(self._get_workspace_suggestions())
        
        return sorted(suggestions)[:10]  # Limit to 10 suggestions
    
    def _get_workspace_suggestions(self) -> List[str]:
        """Get suggestions from workspace root."""
        suggestions = []
        
        try:
            for item in self.workspace_path.iterdir():
                if self._should_suggest_item(item):
                    suggestions.append(item.name)
        except Exception:
            pass
        
        return suggestions
    
    def _get_nested_path_suggestions(self, partial_path: str) -> List[str]:
        """Get suggestions for nested paths like 'src/ii_agent/'."""
        suggestions = []
        
        try:
            # Split path and get directory part
            path_parts = partial_path.split('/')
            filename_part = path_parts[-1]
            dir_parts = path_parts[:-1]
            
            # Build directory path
            current_dir = self.workspace_path
            for part in dir_parts:
                current_dir = current_dir / part
                if not current_dir.exists():
                    return suggestions
            
            # Get completions in that directory
            for item in current_dir.iterdir():
                if self._should_suggest_item(item) and item.name.startswith(filename_part):
                    # Return the full relative path
                    relative_path = '/'.join(dir_parts + [item.name])
                    suggestions.append(relative_path)
        except Exception:
            pass
        
        return suggestions
    
    def _get_matching_suggestions(self, partial_name: str) -> List[str]:
        """Get suggestions matching partial filename."""
        suggestions = []
        
        try:
            # Search in workspace root
            for item in self.workspace_path.iterdir():
                if (self._should_suggest_item(item) and 
                    item.name.lower().startswith(partial_name.lower())):
                    suggestions.append(item.name)
            
            # Also search in common subdirectories
            common_dirs = ['src', 'lib', 'docs', 'tests', 'scripts']
            for dir_name in common_dirs:
                dir_path = self.workspace_path / dir_name
                if dir_path.exists() and dir_path.is_dir():
                    for item in dir_path.iterdir():
                        if (self._should_suggest_item(item) and 
                            item.name.lower().startswith(partial_name.lower())):
                            suggestions.append(f"{dir_name}/{item.name}")
        except Exception:
            pass
        
        return suggestions
    
    def _should_suggest_item(self, path: Path) -> bool:
        """Determine if an item should be suggested."""
        # Skip hidden files and directories
        if path.name.startswith('.'):
            return False
        
        # Skip common build/cache directories
        skip_dirs = {
            '__pycache__', 'node_modules', '.git', '.venv', 'venv', 
            'env', 'build', 'dist', '.pytest_cache', '.mypy_cache'
        }
        if path.is_dir() and path.name in skip_dirs:
            return False
        
        # Suggest directories and common file types
        if path.is_dir():
            return True
        
        # Suggest files with common extensions
        common_extensions = {
            '.py', '.js', '.ts', '.tsx', '.jsx', '.html', '.css', '.scss',
            '.md', '.txt', '.json', '.yaml', '.yml', '.toml', '.ini',
            '.sh', '.bat', '.ps1', '.sql', '.dockerfile', '.gitignore'
        }
        
        return path.suffix.lower() in common_extensions or path.name in {
            'README', 'LICENSE', 'Makefile', 'Dockerfile', 'requirements.txt',
            'package.json', 'pyproject.toml', 'setup.py'
        }
    
    def _get_file_meta(self, suggestion: str) -> str:
        """Get metadata for file suggestion."""
        try:
            file_path = self.workspace_path / suggestion
            if file_path.exists():
                if file_path.is_dir():
                    item_count = len(list(file_path.iterdir()))
                    return f"Directory ({item_count} items)"
                else:
                    size = file_path.stat().st_size
                    if size < 1024:
                        return f"File ({size}B)"
                    elif size < 1024 * 1024:
                        return f"File ({size // 1024}KB)"
                    else:
                        return f"File ({size // (1024 * 1024)}MB)"
            return "File"
        except Exception:
            return "File"


class MentionCompleter(Completer):
    """Enhanced completer that handles @file_path and other @ mentions."""
    
    def __init__(self, workspace_path: str, commands: dict = None):
        self.file_completer = FilePathCompleter(workspace_path)
        self.commands = commands or {}
        
    def get_completions(self, document: Document, complete_event) -> Iterator[Completion]:
        """Get completions for @ mentions."""
        text = document.text_before_cursor
        
        # Find the last @ symbol
        at_index = text.rfind('@')
        if at_index == -1:
            return
        
        # Get the mention text after @
        mention_text = text[at_index + 1:]
        
        # Check if it looks like a file path (contains / or file extensions)
        if ('/' in mention_text or 
            any(mention_text.endswith(ext) for ext in ['.py', '.js', '.md', '.txt', '.json']) or
            not mention_text or
            mention_text.replace('_', '').replace('-', '').replace('.', '').isalnum()):
            
            # Delegate to file completer
            yield from self.file_completer.get_completions(document, complete_event)
        else:
            # Handle other types of mentions (could be expanded later)
            pass