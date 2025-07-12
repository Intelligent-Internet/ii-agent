"""Utility functions for file system tools - Docker compatible version."""

import base64
import os
from pathlib import Path


def encode_image(image_path):
    """Encode image file to base64."""
    try:
        if image_path.startswith('http'):
            # Handle URL-based images
            import urllib.request
            with urllib.request.urlopen(image_path) as response:
                image_data = response.read()
        else:
            # Handle local file images
            with open(image_path, 'rb') as image_file:
                image_data = image_file.read()
        
        # Encode to base64
        base64_encoded = base64.b64encode(image_data).decode('utf-8')
        return base64_encoded
        
    except Exception as e:
        raise Exception(f"Failed to encode image {image_path}: {str(e)}")


def find_similar_file(file_path, workspace_path):
    """Find files with similar names but different extensions."""
    try:
        file_path = Path(file_path)
        workspace_path = Path(workspace_path)
        
        # Get the stem (filename without extension)
        stem = file_path.stem
        
        # Search for files with the same stem but different extensions
        similar_files = []
        for ext in ['.txt', '.md', '.py', '.js', '.json', '.yaml', '.yml']:
            potential_file = file_path.parent / (stem + ext)
            if potential_file.exists() and potential_file != file_path:
                similar_files.append(str(potential_file))
        
        return similar_files
        
    except Exception:
        return []