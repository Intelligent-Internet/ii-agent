import requests
import uuid


MIMETYPE_TO_EXTENSION = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp"
}

def is_image_url_available(url: str) -> bool:
    """
    Checks if a URL points to an image that is likely available for embedding or download.

    Args:
        url: The URL of the image to check.

    Returns:
        True if the URL points to an accessible image, False otherwise.
    """
    try:
        # Add browser-like headers to avoid bot detection
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.google.com/",
        }

        # Use a HEAD request to get headers without downloading the full content
        response = requests.head(url, headers=headers, allow_redirects=True, timeout=5)

        # Check for a successful status code (2xx)
        if not response.ok:
            print(f"Error: Received status code {response.status_code}")
            return False, None

        # Check the Content-Type header to ensure it's an image
        content_type = response.headers.get('Content-Type', '').lower()
        if not content_type.startswith('image/'):
            print(f"Error: Content-Type is not an image ({content_type})")
            return False, content_type

        # Extract mime type from content-type header (e.g., "image/jpeg; charset=utf-8" -> "image/jpeg")
        content_type = content_type.split(";")[0].strip().lower()

        if content_type not in MIMETYPE_TO_EXTENSION:
            print(f"Error: Content-Type is not supported ({content_type})")
            return False, content_type

        # Check for headers that might prevent embedding
        # A 'Content-Disposition' header with 'attachment' suggests a download prompt
        if 'attachment' in response.headers.get('Content-Disposition', ''):
            print("Warning: Content-Disposition suggests attachment, might not be embeddable.")

        # 'X-Frame-Options' can prevent embedding in iframes
        if response.headers.get('X-Frame-Options') in ('DENY', 'SAMEORIGIN'):
             print("Warning: X-Frame-Options header might prevent embedding.")

        return True, content_type

    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
        return False, None

def convert_mimetype_to_extension(mimetype: str) -> str:
    """
    Convert a MIME type to a file extension.
    """
    return MIMETYPE_TO_EXTENSION[mimetype]


def generate_unique_image_name(length=12):
    """
    Generates a short, unique hexadecimal name suitable for a filename.

    Args:
        length (int): The desired length of the unique name. Defaults to 12.

    Returns:
        str: A unique hexadecimal string of the specified length.
    """
    # Generate a random UUID and take the first `length` characters of its hex representation
    return uuid.uuid4().hex[:length]


def construct_blob_path(file_name: str):
    return f"image_search/{file_name}"