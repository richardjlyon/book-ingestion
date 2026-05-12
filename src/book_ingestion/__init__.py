"""book_ingestion — turn a book into a JSON IR."""

from book_ingestion.api import extract_chapter, survey
from book_ingestion.ir import (
    SCHEMA_VERSION,
    BookSurvey,
    ChapterContent,
)

__version__ = "0.1.0"

__all__ = [
    "SCHEMA_VERSION",
    "BookSurvey",
    "ChapterContent",
    "__version__",
    "extract_chapter",
    "survey",
]
