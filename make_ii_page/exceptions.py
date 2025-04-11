"""
Exceptions for the make_ii_page module.
"""


class MDXFileNotFoundError(FileNotFoundError):
    """Raised when the MDX file is not found."""
    pass


class MDXParsingError(Exception):
    """Raised when there's an error parsing the MDX content."""
    pass


class IIPageCreationError(Exception):
    """Raised when there's an error creating the II Page."""
    pass