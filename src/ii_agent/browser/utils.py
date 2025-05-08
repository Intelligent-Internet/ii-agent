import base64
import logging
import requests
from io import BytesIO
from pathlib import Path
from typing import List
from urllib.parse import urlparse
from PIL import Image, ImageDraw, ImageFont

from ii_agent.browser.models import InteractiveElement, Rect

logger = logging.getLogger(__name__)


def put_highlight_elements_on_screenshot(
    elements: dict[int, InteractiveElement], screenshot_b64: str
) -> str:
    """Highlight elements using Pillow instead of OpenCV"""
    try:
        # Decode base64 to PIL Image
        image_data = base64.b64decode(screenshot_b64)
        image = Image.open(BytesIO(image_data))
        draw = ImageDraw.Draw(image)

        # Colors (RGB format for PIL)
        base_colors = [
            (204, 0, 0),
            (0, 136, 0),
            (0, 0, 204),
            (204, 112, 0),
            (102, 0, 102),
            (0, 102, 102),
            (204, 51, 153),
            (44, 0, 102),
            (204, 35, 0),
            (28, 102, 66),
            (170, 0, 0),
            (36, 82, 123),
        ]
        placed_labels = []

        def generate_unique_color(base_color, element_idx):
            """Generate a unique color variation based on element index"""
            r, g, b = base_color
            # Use prime numbers to create deterministic but non-repeating patterns
            offset_r = (element_idx * 17) % 31 - 15  # Range: -15 to 15
            offset_g = (element_idx * 23) % 29 - 14  # Range: -14 to 14
            offset_b = (element_idx * 13) % 27 - 13  # Range: -13 to 13

            # Ensure RGB values stay within 0-255 range
            r = max(0, min(255, r + offset_r))
            g = max(0, min(255, g + offset_g))
            b = max(0, min(255, b + offset_b))

            return (r, g, b)

        # Load custom font from the package
        try:
            # Path to your packaged font
            font_path = Path(__file__).parent / "fonts" / "OpenSans-Medium.ttf"
            font = ImageFont.truetype(str(font_path), 11)
        except Exception as e:
            logger.warning(f"Could not load custom font: {e}, falling back to default")
            font = ImageFont.load_default()

        for idx, element in elements.items():
            # don't draw sheets elements
            if element.browser_agent_id.startswith(
                "row_"
            ) or element.browser_agent_id.startswith("column_"):
                continue

            base_color = base_colors[idx % len(base_colors)]
            color = generate_unique_color(base_color, idx)

            rect = element.rect

            # Draw rectangle
            draw.rectangle(
                [(rect.left, rect.top), (rect.right, rect.bottom)],
                outline=color,
                width=2,
            )

            # Prepare label
            text = str(idx)

            # Get precise text dimensions for proper centering
            text_bbox = draw.textbbox((0, 0), text, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]

            # Make label size exactly proportional for better aesthetics
            label_width = text_width + 4
            label_height = text_height + 4

            # Positioning logic
            if label_width > rect.width or label_height > rect.height:
                label_x = rect.left + rect.width
                label_y = rect.top
            else:
                label_x = rect.left + rect.width - label_width
                label_y = rect.top

            # Check for overlaps with existing labels
            label_rect = {
                "left": label_x,
                "top": label_y,
                "right": label_x + label_width,
                "bottom": label_y + label_height,
            }

            for existing in placed_labels:
                if not (
                    label_rect["right"] < existing["left"]
                    or label_rect["left"] > existing["right"]
                    or label_rect["bottom"] < existing["top"]
                    or label_rect["top"] > existing["bottom"]
                ):
                    label_y = existing["bottom"] + 2
                    label_rect["top"] = label_y
                    label_rect["bottom"] = label_y + label_height
                    break

            # Ensure label is visible within image boundaries
            img_width, img_height = image.size
            if label_x < 0:
                label_x = 0
            elif label_x + label_width >= img_width:
                label_x = img_width - label_width - 1

            if label_y < 0:
                label_y = 0
            elif label_y + label_height >= img_height:
                label_y = img_height - label_height - 1

            # Draw label background
            draw.rectangle(
                [(label_x, label_y), (label_x + label_width, label_y + label_height)],
                fill=color,
            )

            # magic numbers to center the text
            text_x = label_x + 3
            text_y = label_y - 1

            # Draw text
            draw.text((text_x, text_y), text, fill=(255, 255, 255), font=font)

            placed_labels.append(label_rect)

        # Convert back to base64
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        new_image_base64 = base64.b64encode(buffer.getvalue()).decode()

        return new_image_base64

    except Exception as e:
        logger.error(f"Failed to add highlights to screenshot: {str(e)}")
        return screenshot_b64


def scale_b64_image(image_b64: str, scale_factor: float) -> str:
    """
    Scale down a base64 encoded image using Pillow.

    Args:
        image_b64: Base64 encoded image string
        scale_factor: Factor to scale the image by (0.5 = half size)

    Returns:
        Base64 encoded scaled image
    """
    try:
        # Decode base64 to PIL Image
        image_data = base64.b64decode(image_b64)
        image = Image.open(BytesIO(image_data))

        if image is None:
            return image_b64

        # Get original dimensions
        width, height = image.size

        # Calculate new dimensions
        new_width = int(width * scale_factor)
        new_height = int(height * scale_factor)

        # Resize the image using high quality resampling
        resized_image = image.resize((new_width, new_height), Image.LANCZOS)

        # Convert back to base64
        buffer = BytesIO()
        resized_image.save(buffer, format="PNG")
        resized_image_b64 = base64.b64encode(buffer.getvalue()).decode()

        return resized_image_b64

    except Exception:
        return image_b64


def calculate_iou(rect1: Rect, rect2: Rect) -> float:
    """
    Calculate Intersection over Union between two rectangles.

    Args:
        rect1: First rectangle with left, top, right, bottom keys
        rect2: Second rectangle with left, top, right, bottom keys

    Returns:
        IoU value
    """
    # Calculate intersection
    intersect_left = max(rect1.left, rect2.left)
    intersect_top = max(rect1.top, rect2.top)
    intersect_right = min(rect1.right, rect2.right)
    intersect_bottom = min(rect1.bottom, rect2.bottom)

    # Check if intersection exists
    if intersect_right < intersect_left or intersect_bottom < intersect_top:
        return 0.0  # No intersection

    # Calculate area of each rectangle
    area1 = (rect1.right - rect1.left) * (rect1.bottom - rect1.top)
    area2 = (rect2.right - rect2.left) * (rect2.bottom - rect2.top)

    # Calculate area of intersection
    intersection_area = (intersect_right - intersect_left) * (
        intersect_bottom - intersect_top
    )

    # Calculate union area
    union_area = area1 + area2 - intersection_area

    # Calculate IoU
    return intersection_area / union_area if union_area > 0 else 0.0


def is_fully_contained(rect1: Rect, rect2: Rect) -> bool:
    """
    Check if rect1 is fully contained within rect2.

    Args:
        rect1: First rectangle with left, top, right, bottom keys
        rect2: Second rectangle with left, top, right, bottom keys

    Returns:
        True if rect1 is fully contained within rect2
    """
    return (
        rect1.left >= rect2.left
        and rect1.right <= rect2.right
        and rect1.top >= rect2.top
        and rect1.bottom <= rect2.bottom
    )


def filter_overlapping_elements(
    elements: List[InteractiveElement], iou_threshold: float = 0.7
) -> List[InteractiveElement]:
    """
    Filter overlapping elements using weight and IoU.

    Args:
        elements: Elements to filter
        iou_threshold: Threshold for considering elements as overlapping

    Returns:
        Filtered elements
    """
    if not elements:
        return []

    # Sort by area (descending), then by weight (descending)
    elements.sort(
        key=lambda e: (
            -(e.rect.width * e.rect.height),  # Negative area for descending sort
            -e.weight,  # Negative weight for descending sort
        )
    )

    filtered_elements: List[InteractiveElement] = []

    # Add elements one by one, checking against already added elements
    for current in elements:
        should_add = True

        # For each element already in our filtered list
        for existing in filtered_elements:
            # Check overlap with IoU
            iou = calculate_iou(current.rect, existing.rect)
            if iou > iou_threshold:
                should_add = False
                break

            # Check if current element is fully contained within an existing element with higher weight
            if is_fully_contained(current.rect, existing.rect):
                if (
                    existing.weight >= current.weight
                    and existing.z_index == current.z_index
                ):
                    should_add = False
                    break
                else:
                    # If current element has higher weight and is more than 50% of the size of the existing element, remove the existing element
                    if (
                        current.rect.width * current.rect.height
                        >= existing.rect.width * existing.rect.height * 0.5
                    ):
                        filtered_elements.remove(existing)
                        break

        if should_add:
            filtered_elements.append(current)

    return filtered_elements


def sort_elements_by_position(
    elements: List[InteractiveElement],
) -> List[InteractiveElement]:
    """
    Sort elements by position (top to bottom, left to right).

    Args:
        elements: Elements to sort

    Returns:
        Sorted elements
    """
    if not elements:
        return []

    # Define what "same row" means
    ROW_THRESHOLD = 20  # pixels

    # First, group elements into rows based on Y position
    rows = []
    current_row = []

    # Copy and sort elements by Y position
    sorted_by_y = sorted(elements, key=lambda e: e.rect.top)

    # Group into rows
    for element in sorted_by_y:
        if not current_row:
            # Start a new row
            current_row.append(element)
        else:
            # Check if this element is in the same row as the previous ones
            last_element = current_row[-1]
            if abs(element.rect.top - last_element.rect.top) <= ROW_THRESHOLD:
                # Same row
                current_row.append(element)
            else:
                # New row
                rows.append(list(current_row))
                current_row = [element]

    # Add the last row if not empty
    if current_row:
        rows.append(current_row)

    # Sort each row by X position (left to right)
    for row in rows:
        row.sort(key=lambda e: e.rect.left)

    # Flatten the rows back into a single array
    elements = [element for row in rows for element in row]

    for i, element in enumerate(elements):
        element.index = i

    return elements


def filter_elements(
    elements: List[InteractiveElement], iou_threshold: float = 0.7
) -> List[InteractiveElement]:
    """
    Combine interactive elements from multiple detection methods and filter duplicates.

    Args:
        elements: Interactive elements from multiple detection methods
        iou_threshold: Threshold for considering elements as overlapping

    Returns:
        Combined and filtered elements
    """
    # Filter overlapping elements
    filtered = filter_overlapping_elements(elements, iou_threshold)

    # Sort elements by position
    sorted_elements = sort_elements_by_position(filtered)

    return sorted_elements


def is_pdf_url(url: str, timeout: float = 5.0) -> bool:
    """
    Checks if a given URL points to a PDF file.

    Args:
        url (str): The URL to check.
        timeout (float): Timeout for HTTP requests.

    Returns:
        bool: True if the URL points to a PDF, False otherwise.
    """
    try:
        # Quick extension check
        parsed = urlparse(url)
        if parsed.path.lower().endswith(".pdf"):
            return True

        # Try HEAD request to get Content-Type
        head = requests.head(url, allow_redirects=True, timeout=timeout)
        content_type = head.headers.get("Content-Type", "").lower()
        if "application/pdf" in content_type:
            return True

        # Fallback: Try a minimal GET request
        get = requests.get(url, stream=True, timeout=timeout)
        content_type = get.headers.get("Content-Type", "").lower()
        return "application/pdf" in content_type

    except requests.RequestException:
        # Log or handle as needed in real prod code
        return False
