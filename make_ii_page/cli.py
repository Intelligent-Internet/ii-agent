"""
Command-line interface for make_ii_page.
"""

import argparse
import sys
import json
import datetime
from typing import List, Optional

from .make_ii_page import make_ii_page, save_ii_page
from .exceptions import MDXFileNotFoundError, MDXParsingError, IIPageCreationError


def main(args: Optional[List[str]] = None) -> int:
    """
    Main entry point for the CLI.

    Args:
        args (Optional[List[str]]): Command line arguments. Defaults to sys.argv[1:].

    Returns:
        int: Exit code (0 for success, non-zero for errors)
    """
    parser = argparse.ArgumentParser(description="Make II Page from MDX file")
    parser.add_argument("mdx_file_path", help="Absolute path of the source MDX file")
    parser.add_argument(
        "-o", "--output", 
        help="Output path for the II Page. If not provided, a default path will be used."
    )
    parser.add_argument(
        "--print", action="store_true", 
        help="Print the II Page content to stdout"
    )

    parsed_args = parser.parse_args(args if args is not None else sys.argv[1:])

    try:
        # Make II Page
        ii_page = make_ii_page(parsed_args.mdx_file_path)
        
        # Custom JSON encoder for printing and saving
        class CustomJSONEncoder(json.JSONEncoder):
            def default(self, obj):
                if isinstance(obj, (datetime.date, datetime.datetime)):
                    return obj.isoformat()
                return super().default(obj)
        
        # Print if requested
        if parsed_args.print:
            print(json.dumps(ii_page, indent=2, cls=CustomJSONEncoder))
        
        # Save to file
        output_path = save_ii_page(ii_page, parsed_args.output)
        print(f"II Page saved to: {output_path}")
        
        return 0
    except (MDXFileNotFoundError, MDXParsingError, IIPageCreationError) as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {str(e)}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())