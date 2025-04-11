#!/usr/bin/env python3
"""
Merge multiple JSONL files into a single JSONL file.

Usage:
    python merge_shards.py --input file1.jsonl file2.jsonl ... --output merged.jsonl
"""

import argparse
import json
import sys
from pathlib import Path


def merge_jsonl_files(input_files, output_file):
    """
    Merge multiple JSONL files into a single JSONL file.

    Args:
        input_files (list): List of paths to input JSONL files
        output_file (str): Path to the output JSONL file
    """
    # Create output directory if it doesn't exist
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Count total lines for reporting
    total_lines = 0

    with open(output_file, "w") as outfile:
        for input_file in input_files:
            try:
                with open(input_file, "r") as infile:
                    for line in infile:
                        line = line.strip()
                        if not line:  # Skip empty lines
                            continue

                        # Verify it's valid JSON before writing
                        try:
                            json.loads(line)
                            outfile.write(
                                line + "\n"
                            )  # Ensure each JSON object is on its own line
                            total_lines += 1
                        except json.JSONDecodeError:
                            print(
                                f"Warning: Skipping invalid JSON line in {input_file}",
                                file=sys.stderr,
                            )
                print(f"Processed: {input_file}")
            except FileNotFoundError:
                print(f"Error: File not found: {input_file}", file=sys.stderr)
                continue

    print(
        f"Merged {len(input_files)} files with {total_lines} total records into {output_file}"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Merge multiple JSONL files into a single JSONL file"
    )
    parser.add_argument(
        "--input", "-i", nargs="+", required=True, help="Input JSONL files to merge"
    )
    parser.add_argument("--output", "-o", required=True, help="Output JSONL file path")

    args = parser.parse_args()

    merge_jsonl_files(args.input, args.output)


if __name__ == "__main__":
    main()
