import os
import base64
import requests

from glob import glob


def encode_image(image_path: str):
    """Fetch/Read an image to base64."""

    if image_path.startswith("http"):
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0"
        request_kwargs = {
            "headers": {"User-Agent": user_agent},
            "stream": True,
        }

        # Send a HTTP request to the URL
        response = requests.get(image_path, **request_kwargs)
        response.raise_for_status()

        # Read image data directly from response content
        image_data = response.content
        return base64.b64encode(image_data).decode("utf-8")

    # For local files, read directly into memory
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
        similar_files = glob.glob(pattern)
        
        if similar_files:
            # Return the first match that's not the original file
            for similar in similar_files:
                if similar != file_path:
                    return similar
        
        return None
    except Exception:
        return None