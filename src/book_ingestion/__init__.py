"""book_ingestion — turn a book into a JSON IR."""

from book_ingestion.api import extract_chapter, extract_metadata, survey
from book_ingestion.ir import (
    SCHEMA_VERSION,
    BookSurvey,
    ChapterContent,
)
from book_ingestion.metadata import BookMetadata

__version__ = "0.1.0"

__all__ = [
    "SCHEMA_VERSION",
    "BookMetadata",
    "BookSurvey",
    "ChapterContent",
    "__version__",
    "extract_chapter",
    "extract_metadata",
    "survey",
]
