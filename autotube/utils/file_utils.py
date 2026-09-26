"""File handling and naming utilities."""

import re
import unicodedata
from pathlib import Path


def slugify(value: str, allow_unicode: bool = False) -> str:
    """Convert string to safe file slug."""
    value = str(value)
    if allow_unicode:
        value = unicodedata.normalize("NFKC", value)
    else:
        value = (
            unicodedata.normalize("NFKD", value)
            .encode("ascii", "ignore")
            .decode("ascii")
        )
    value = re.sub(r"[^\w\s-]", "", value.lower())
    return re.sub(r"[-\s]+", "_", value).strip("-_")


def sanitize_filename(filename: str, max_length: int = 60) -> str:
    """Sanitize a filename and limit length."""
    slug = slugify(filename)
    if not slug:
        slug = "untitled"
    return slug[:max_length]
