# Make II Page

A utility for converting MDX files to II Pages.

## Installation

Make sure you have the required dependencies:

```bash
pip install pyyaml
```

## Usage

### As a Python Module

```python
from make_ii_page import make_ii_page, save_ii_page

# Convert MDX to II Page
ii_page = make_ii_page("/path/to/your/file.mdx")

# Save the II Page
output_path = save_ii_page(ii_page, "/path/to/output.ii.json")
print(f"II Page saved to: {output_path}")
```

### From Command Line

```bash
python -m make_ii_page.cli /path/to/your/file.mdx --output /path/to/output.ii.json
```

Options:
- `-o, --output`: Specify the output file path (optional)
- `--print`: Print the II Page content to stdout

## Function Description

```
make_ii_page(mdx_file_path: str) -> Dict[str, Any]
```

- **Description**: Make a II Page from a local MDX file.
- **Parameters**:
  - `mdx_file_path` (str): Absolute path of the source MDX file
- **Returns**: A dictionary containing the II Page content with metadata

## II Page Format

The II Page is returned as a dictionary with the following structure:

```json
{
  "metadata": {
    // Frontmatter metadata from the MDX file
  },
  "content": "The main content of the MDX file",
  "source": {
    "path": "/path/to/original.mdx",
    "type": "mdx",
    "lastModified": 1234567890.123
  }
}
```

## Error Handling

The module provides specific exceptions for different error cases:

- `MDXFileNotFoundError`: When the MDX file is not found
- `MDXParsingError`: When there's an error parsing the MDX content
- `IIPageCreationError`: When there's an error creating the II Page