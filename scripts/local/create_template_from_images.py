#!/usr/bin/env python3
"""
Create a slide template from reference images.

This script:
1. Uploads the reference images to local storage
2. Creates a slide template with style guidelines based on the images
3. The template can then be selected when creating new presentations

Usage:
    python scripts/local/create_template_from_images.py \
        --name "SEATS Dark Theme" \
        --images "/path/to/dark1.png" "/path/to/dark2.png" ...
"""

import argparse
import asyncio
import os
import sys
import httpx
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))


API_URL = os.environ.get("API_URL", "http://localhost:8000")


async def dev_login() -> str:
    """Get access token via dev login."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{API_URL}/auth/dev/login")
        response.raise_for_status()
        data = response.json()
        return data["access_token"]


async def upload_image(token: str, image_path: str) -> str:
    """Upload an image and return its URL."""
    path = Path(image_path)

    async with httpx.AsyncClient() as client:
        # Read file
        with open(path, "rb") as f:
            content = f.read()

        # Upload
        files = {"file": (path.name, content, "image/png")}
        response = await client.post(
            f"{API_URL}/files/upload", headers={"Authorization": f"Bearer {token}"}, files=files
        )
        response.raise_for_status()
        data = response.json()
        return data.get("url") or data.get("file_url")


async def create_template(token: str, name: str, image_urls: list[str], style_content: str) -> dict:
    """Create a slide template."""
    async with httpx.AsyncClient() as client:
        payload = {
            "slide_template_name": name,
            "slide_content": style_content,
            "slide_template_images": image_urls,
        }

        response = await client.post(
            f"{API_URL}/slide-templates",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
        )
        response.raise_for_status()
        return response.json()


def generate_style_content(name: str, image_count: int) -> str:
    """Generate style guidelines content for the template."""
    return f"""# {name} - Style Template

## Overview
This template is based on {image_count} reference slides that define the visual style and layout preferences.

## Style Guidelines

### Color Scheme
- **Background**: Dark theme (deep navy/charcoal #1a1a2e or similar)
- **Primary Text**: White or light gray (#ffffff, #f0f0f0)
- **Accent Colors**: Use brand colors for highlights and CTAs
- **Gradients**: Subtle dark-to-darker gradients for depth

### Typography
- **Headings**: Large, bold, clean sans-serif (e.g., Inter, Montserrat)
- **Body Text**: Clear, readable, lighter weight
- **Emphasis**: Use color or weight, not italics
- **Size Hierarchy**: Clear distinction between H1, H2, body text

### Layout Principles
- **Alignment**: Left-aligned text with generous margins
- **Whitespace**: Ample padding, don't crowd content
- **Grid**: Content blocks with clear separation
- **Images**: Full-bleed or contained with rounded corners

### Visual Elements
- **Icons**: Simple, line-style or filled solid icons
- **Borders**: Minimal, use spacing instead
- **Cards/Boxes**: Subtle background differentiation, rounded corners
- **Shadows**: Subtle drop shadows for elevation

### Slide Types to Include
1. **Title Slide**: Large centered title, subtitle, minimal elements
2. **Content Slide**: Heading + bullet points or paragraphs
3. **Image + Text**: Split layout with image and supporting text
4. **Data/Stats**: Large numbers with supporting context
5. **Closing Slide**: Call-to-action or contact information

## Implementation Notes
- Canvas size: 1280px × 720px (16:9 aspect ratio)
- Use CSS for all styling (no inline styles where possible)
- Ensure text contrast meets accessibility standards
- Test with actual content before finalizing

## Reference Images
The following images show the desired style:
{chr(10).join(f"- Slide {i + 1}: Reference for layout and visual style" for i in range(image_count))}
"""


async def main():
    parser = argparse.ArgumentParser(description="Create slide template from reference images")
    parser.add_argument("--name", required=True, help="Template name")
    parser.add_argument("--images", nargs="+", required=True, help="Paths to reference images")
    parser.add_argument("--api-url", default=API_URL, help="API URL")

    args = parser.parse_args()

    global API_URL
    API_URL = args.api_url

    print(f"Creating template: {args.name}")
    print(f"Reference images: {len(args.images)}")

    # Login
    print("\n1. Logging in...")
    token = await dev_login()
    print("   ✓ Logged in")

    # Upload images
    print("\n2. Uploading reference images...")
    image_urls = []
    for img_path in args.images:
        if not os.path.exists(img_path):
            print(f"   ✗ File not found: {img_path}")
            continue

        try:
            url = await upload_image(token, img_path)
            image_urls.append(url)
            print(f"   ✓ Uploaded: {os.path.basename(img_path)} -> {url}")
        except Exception as e:
            print(f"   ✗ Failed to upload {img_path}: {e}")

    if not image_urls:
        print("\nError: No images were uploaded successfully")
        return 1

    # Generate style content
    print("\n3. Generating style guidelines...")
    style_content = generate_style_content(args.name, len(image_urls))
    print("   ✓ Style guidelines generated")

    # Create template
    print("\n4. Creating template...")
    try:
        template = await create_template(token, args.name, image_urls, style_content)
        print("   ✓ Template created!")
        print(f"\n   Template ID: {template.get('id')}")
        print(f"   Name: {template.get('slide_template_name')}")
        print(f"   Images: {len(template.get('slide_template_images', []))}")
    except Exception as e:
        print(f"   ✗ Failed to create template: {e}")
        return 1

    print("\n✅ Done! You can now select this template when creating new presentations.")
    print(f"   Template ID: {template.get('id')}")

    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))
