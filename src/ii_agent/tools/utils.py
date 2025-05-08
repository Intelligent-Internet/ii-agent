import base64
from PIL import Image
from io import BytesIO

MAX_LENGTH_TRUNCATE_CONTENT = 20000


def save_base64_image_png(base64_str: str, path: str) -> None:
    """
    Saves a base64-encoded image to a PNG file.

    Args:
        base64_str (str): Base64-encoded image string.
        path (str): Destination file path (should end with .png).
    """
    # Strip off any data URL prefix
    if "," in base64_str:
        base64_str = base64_str.split(",")[1]

    image_data = base64.b64decode(base64_str)
    image = Image.open(BytesIO(image_data)).convert("RGBA")
    image.save(path, format="PNG")


def truncate_content(
    content: str, max_length: int = MAX_LENGTH_TRUNCATE_CONTENT
) -> str:
    if len(content) <= max_length:
        return content
    else:
        return (
            content[: max_length // 2]
            + f"\n..._This content has been truncated to stay below {max_length} characters_...\n"
            + content[-max_length // 2 :]
        )
