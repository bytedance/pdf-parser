from pydantic import BaseModel


class PyMuPDFParserConfig(BaseModel):
    """Configuration for PDF parser."""

    extract_images: bool = True
    extract_tables: bool = True
    max_pages: int = 0  # 0 means no limit
    skip_header_footer: bool = True
