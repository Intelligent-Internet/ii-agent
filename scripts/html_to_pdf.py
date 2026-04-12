#!/usr/bin/env python3
"""
HTML to PDF Converter

Converts HTML files (slides, pages, etc.) to a single multi-page PDF using Playwright/Chromium.
Each HTML file becomes exactly one page in the output PDF, with full content capture.

Requirements:
    pip install playwright Pillow
    python3 -m playwright install chromium

Usage:
    # Convert all HTML files in a directory to PDF
    ./html_to_pdf.py /path/to/html/files -o output.pdf

    # Convert specific HTML files
    ./html_to_pdf.py slide_001.html slide_002.html -o slides.pdf

    # Specify custom width (default: 1280px)
    ./html_to_pdf.py /path/to/files -o output.pdf --width 1920

    # Set DPI for output (default: 150)
    ./html_to_pdf.py /path/to/files -o output.pdf --dpi 300
"""

import argparse
import asyncio
import io
import sys
from pathlib import Path

try:
    from playwright.async_api import async_playwright
    from PIL import Image
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("\nInstall requirements with:")
    print("  pip install playwright Pillow")
    print("  python3 -m playwright install chromium")
    sys.exit(1)


async def convert_html_to_pdf(
    html_files: list[Path],
    output_pdf: Path,
    width: int = 1280,
    dpi: float = 150.0,
    verbose: bool = True
) -> None:
    """
    Convert HTML files to a single multi-page PDF.
    
    Args:
        html_files: List of HTML file paths to convert
        output_pdf: Output PDF file path
        width: Viewport width in pixels (default: 1280)
        dpi: Output resolution (default: 150)
        verbose: Print progress messages
    """
    if not html_files:
        raise ValueError("No HTML files provided")
    
    if verbose:
        print(f"Converting {len(html_files)} HTML file(s) to PDF...")
    
    images = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        
        for i, html_file in enumerate(html_files, 1):
            if verbose:
                print(f"  [{i:02d}/{len(html_files)}] {html_file.name}...", end=" ", flush=True)
            
            # Start with tall viewport to measure actual content height
            page = await browser.new_page(viewport={"width": width, "height": 4000})
            await page.goto(f"file://{html_file.absolute()}")
            await page.wait_for_load_state("networkidle")
            
            # Get actual content dimensions
            dimensions = await page.evaluate('''() => {
                // Try to find common slide/content containers
                const selectors = ['.slide', '.page', 'main', 'article', '#content', '.content'];
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el) {
                        const rect = el.getBoundingClientRect();
                        return { width: rect.width, height: rect.height };
                    }
                }
                // Fallback to body dimensions
                return { 
                    width: document.body.scrollWidth, 
                    height: Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)
                };
            }''')
            
            actual_height = max(int(dimensions['height']), 100)  # Minimum 100px
            
            if verbose:
                print(f"({actual_height}px)", end=" ", flush=True)
            
            # Capture full content
            screenshot_bytes = await page.screenshot(
                type="png",
                clip={"x": 0, "y": 0, "width": width, "height": actual_height}
            )
            
            img = Image.open(io.BytesIO(screenshot_bytes))
            images.append(img.convert("RGB"))
            
            await page.close()
            
            if verbose:
                print("done", flush=True)
        
        await browser.close()
    
    # Save all images as a single PDF
    if verbose:
        print(f"\nSaving to {output_pdf}...")
    
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    
    images[0].save(
        str(output_pdf),
        "PDF",
        save_all=True,
        append_images=images[1:],
        resolution=dpi
    )
    
    if verbose:
        size_kb = output_pdf.stat().st_size / 1024
        print(f"✅ Created: {output_pdf}")
        print(f"   Size: {size_kb:.1f} KB")
        print(f"   Pages: {len(images)}")


def find_html_files(path: Path, pattern: str = "*.html") -> list[Path]:
    """Find HTML files in a directory, sorted by name."""
    if path.is_file():
        return [path]
    return sorted(path.glob(pattern))


def main():
    parser = argparse.ArgumentParser(
        description="Convert HTML files to a single multi-page PDF",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "input",
        nargs="+",
        help="HTML file(s) or directory containing HTML files"
    )
    parser.add_argument(
        "-o", "--output",
        required=True,
        help="Output PDF file path"
    )
    parser.add_argument(
        "--width",
        type=int,
        default=1280,
        help="Viewport width in pixels (default: 1280)"
    )
    parser.add_argument(
        "--dpi",
        type=float,
        default=150.0,
        help="Output resolution DPI (default: 150)"
    )
    parser.add_argument(
        "--pattern",
        default="*.html",
        help="Glob pattern for finding HTML files in directories (default: *.html)"
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress progress output"
    )
    
    args = parser.parse_args()
    
    # Collect all HTML files
    html_files = []
    for input_path in args.input:
        path = Path(input_path)
        if not path.exists():
            print(f"Error: {path} does not exist", file=sys.stderr)
            sys.exit(1)
        html_files.extend(find_html_files(path, args.pattern))
    
    if not html_files:
        print("Error: No HTML files found", file=sys.stderr)
        sys.exit(1)
    
    # Remove duplicates and sort
    html_files = sorted(set(html_files))
    
    output_pdf = Path(args.output)
    
    # Run conversion
    asyncio.run(convert_html_to_pdf(
        html_files=html_files,
        output_pdf=output_pdf,
        width=args.width,
        dpi=args.dpi,
        verbose=not args.quiet
    ))


if __name__ == "__main__":
    main()
