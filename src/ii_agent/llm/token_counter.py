import json
import base64
from typing import Any, Union
from PIL import Image
import io


class TokenCounter:
    def count_tokens(self, prompt_chars: Union[str, list[dict[str, Any]]]) -> int:
        if isinstance(prompt_chars, str):
            return len(prompt_chars) // 3
        elif isinstance(prompt_chars, list):
            total_tokens = 0
            for item in prompt_chars:
                if item.get("type") == "image" and "source" in item:
                    # For images, calculate tokens based on image dimensions
                    try:
                        # Decode base64 image data
                        image_data = base64.b64decode(item["source"]["data"])
                        # Open image to get dimensions
                        with Image.open(io.BytesIO(image_data)) as img:
                            width, height = img.size
                            # Calculate tokens using official formula: (width * height)/750
                            image_tokens = int((width * height) / 750)
                            total_tokens += image_tokens
                    except Exception as e:
                        # If we can't decode the image, use a conservative estimate
                        print(
                            f"Warning: Could not decode image for token counting: {e}"
                        )
                        total_tokens += (
                            1500  # Conservative estimate for unknown image size
                        )
                elif item.get("type") == "text":
                    total_tokens += len(item["text"]) // 3
                else:
                    # For regular text/dict items, convert to JSON and count
                    json_str = json.dumps(item)
                    total_tokens += len(json_str) // 3
            return total_tokens
        else:
            raise ValueError(
                f"Unsupported type for token counting: {type(prompt_chars)}"
            )
