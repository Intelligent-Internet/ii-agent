import os
import base64
from glob import glob


def encode_image(image_path: str):
    """Read an image file and encode it to base64."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def find_similar_file(file_path: str) -> str | None:
    """Find similar files with different extensions."""
    try:
        base_path = os.path.splitext(file_path)[0]
        parent_dir = os.path.dirname(file_path)
        base_name = os.path.basename(base_path)
        
        # Look for files with same base name but different extensions
        pattern = os.path.join(parent_dir, f"{base_name}.*")
        similar_files = glob(pattern)
        
        if similar_files:
            # Return the first match that's not the original file
            for similar in similar_files:
                if similar != file_path:
                    return similar
        
        return None
    except Exception:
        return None