# Copyright (C) 2025 ByteDance Inc
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import base64
import io
import logging
import threading
from typing import Any

import fitz  # type: ignore[import-untyped]
from PIL import Image, UnidentifiedImageError
from pymupdf.table import Table, TableFinder  # type: ignore[import-untyped]

from .config import PyMuPDFParserConfig
from .datamodel import Block, BlockArea, ContentType
from .utils.hash import generate_hash
from .utils.table import table_markdown

_logger = logging.getLogger(__name__)


class PyMuPDFParser:
    """
    PDF document parser based on PyMuPDF (fitz).

    This parser extracts text, images, and tables from PDF documents
    and converts them into TalosDocument objects.
    """

    # Layout and positioning constants
    DEFAULT_PAGE_WIDTH = 612.0
    DEFAULT_PAGE_HEIGHT = 792.0

    # Header/footer detection thresholds
    HEADER_HEIGHT_RATIO = 0.15
    FOOTER_HEIGHT_RATIO = 0.8
    PAGE_MARGIN_RATIO = 0.1
    PAGE_NUMBER_DETECTION_OFFSET = 0.1  # Additional offset for page number detection

    # Similarity detection thresholds
    SIMILARITY_PAGE_THRESHOLD = 0.5  # Block appears in at least 50% of pages
    SIMILARITY_POSITION_THRESHOLD = 0.05  # Position tolerance for similar blocks
    SIMILARITY_NEARBY_THRESHOLD = 0.8  # 80% of occurrences at similar positions

    # Text processing constants
    MAX_RECURRING_TEXT_LENGTH = 50
    VERTICAL_MERGE_THRESHOLD = 50.0  # Maximum vertical gap for merging text blocks
    COLUMN_GAP_THRESHOLD = 30.0  # Minimum gap to detect columns
    SAME_COLUMN_TOLERANCE = 50.0  # Tolerance for determining same column

    # Multi-column layout constants
    COLUMN_DETECTION_MIN_GAP = 50.0  # Minimum horizontal gap to detect columns
    CROSS_COLUMN_MAX_VERTICAL_DISTANCE = (
        200.0  # Maximum vertical distance for cross-column merging
    )
    CROSS_COLUMN_CONTINUATION_MAX_LENGTH = (
        20  # Maximum length for continuation text (like "work.")
    )
    CROSS_COLUMN_MIN_HORIZONTAL_GAP = (
        5.0  # Minimum gap between columns (further reduced to 5.0)
    )

    # Page detection constants
    MIN_PAGES_FOR_PATTERN = 3  # Minimum pages needed to detect patterns

    # Point to pixel conversion factor (72pt → 96dpi)
    POINT_TO_PIXEL_FACTOR = 4.0 / 3.0

    # PDF block type constants (PyMuPDF block types)
    BLOCK_TYPE_TEXT = 0  # Text block containing textual content
    BLOCK_TYPE_IMAGE = 1  # Image block containing embedded images

    # Table processing constants
    TABLE_CROSS_PAGE_MERGE_THRESHOLD = 50.0  # Maximum gap to merge tables across pages
    TABLE_HORIZONTAL_ALIGNMENT_THRESHOLD = (
        30.0  # Threshold for table horizontal alignment
    )
    TABLE_WIDTH_DIFFERENCE_RATIO = (
        0.2  # Maximum width difference ratio for table merging
    )

    def __init__(self, config: PyMuPDFParserConfig):
        self.config = config
        # PyMuPDF is not threadable https://github.com/pymupdf/PyMuPDF/issues/107
        self.pymupdf_lock = threading.Lock()

    def parse(
        self, input: str, **runtime_options: Any
    ) -> tuple[list[Block], dict[str, Any]]:
        """
        Parse a PDF file into a list of TalosDocument objects.

        Args:
            input: Path to the PDF file.
            **runtime_options: Additional runtime options.
                - extract_images: Override config setting for image extraction.
                - extract_tables: Override config setting for table extraction.
                - password: Password for encrypted PDFs.

        Returns:
            List of blocks representing the contents and metadata of the PDF.
        """
        file_path = input
        extract_images = runtime_options.get(
            "extract_images", self.config.extract_images
        )
        extract_tables = runtime_options.get(
            "extract_tables", self.config.extract_tables
        )
        password = runtime_options.get("password")

        _logger.info(f"Parsing PDF file: {file_path}")

        document = self._open_and_authenticate_document(file_path, password)
        _logger.info(f"Successfully opened PDF with {len(document)} pages")

        doc_metadata = self._extract_document_metadata(document)

        similarity_blocks = {}
        if self.config.skip_header_footer:
            similarity_blocks = self._get_similarity_blocks(document)
            _logger.debug(f"Found {len(similarity_blocks)} recurring block patterns")

        all_blocks = self._extract_all_blocks(
            document, similarity_blocks, extract_tables, extract_images
        )
        _logger.info(f"Extracted {len(all_blocks)} total blocks from document")

        processed_blocks = self._post_process_blocks(all_blocks)
        _logger.info(f"Post-processed to {len(processed_blocks)} blocks")

        # Get page dimensions from the first page or use defaults
        page_width = self.DEFAULT_PAGE_WIDTH
        page_height = self.DEFAULT_PAGE_HEIGHT
        if len(document) > 0:
            first_page = document[0]
            doc_metadata["page_width"] = first_page.rect.width
            doc_metadata["page_height"] = first_page.rect.height
            _logger.debug(f"Using page dimensions: {page_width}x{page_height}")

        _logger.info(f"Successfully parsed PDF into {len(processed_blocks)} blocks")
        return processed_blocks, doc_metadata

    def _open_and_authenticate_document(
        self, file_path: str, password: str | None
    ) -> fitz.Document:
        """Open and authenticate a PDF document."""
        try:
            document = fitz.open(file_path)
        except fitz.FileNotFoundError:
            raise FileNotFoundError(f"File not exist: {file_path}")
        except Exception as e:
            raise Exception(f"Cannot open PDF file {file_path}") from e

        if document.is_encrypted:
            if password:
                if not document.authenticate(password):
                    raise PermissionError("Authentication failed for encrypted PDF")
                _logger.info(f"Successfully authenticated encrypted PDF: {file_path}")
            else:
                raise PermissionError("Password required for encrypted PDF")

        if document.page_count == 0:
            _logger.warning(f"PDF file has no pages: {file_path}")

        return document

    def _extract_document_metadata(self, document: fitz.Document) -> dict[str, Any]:
        """Extract metadata from the PDF document."""
        fields = ["title", "author", "subject", "keywords", "creator", "producer"]
        metadata = {}

        if document.metadata:
            metadata.update(
                {
                    # avoid fastapi str.encode('utf-8') raise UnicodeEncodeError
                    key: document.metadata[key].encode("utf-8", "replace").decode()
                    for key in fields
                    if document.metadata.get(key)
                }
            )

        metadata["page_count"] = len(document)

        return metadata

    def _extract_all_blocks(
        self,
        document: fitz.Document,
        similarity_blocks: dict[str, Any],
        extract_tables: bool,
        extract_images: bool,
    ) -> list[Block]:
        """Extract all blocks from all pages of the document."""
        all_blocks: list[Block] = []
        max_pages = self.config.max_pages

        for page_idx, page in enumerate(document):
            if max_pages and page_idx >= max_pages:
                break

            page_num = page_idx + 1  # 1-based page numbering
            page_width = page.rect.width
            page_height = page.rect.height

            # Detect header and footer positions
            header_y, footer_y = self._get_header_footer_positions(
                page, page_width, page_height
            )

            # Extract different types of blocks
            page_blocks = self._extract_page_blocks(
                page,
                header_y,
                footer_y,
                similarity_blocks,
                document,
                page_num,
                extract_tables,
                extract_images,
            )
            all_blocks.extend(page_blocks)

        return all_blocks

    def _extract_page_blocks(
        self,
        page: fitz.Page,
        header_y: float,
        footer_y: float,
        similarity_blocks: dict[str, Any],
        document: fitz.Document,
        page_num: int,
        extract_tables: bool,
        extract_images: bool,
    ) -> list[Block]:
        """Extract all blocks from a single page."""
        page_blocks: list[Block] = []
        # Extract tables if enabled
        table_areas: list[tuple[float, float, float, float]] = []
        if extract_tables:
            table_blocks = self._extract_table_blocks(page, page_num)
            page_blocks.extend(table_blocks)
            # Collect all areas from all table blocks for intersection checking
            table_areas = []
            for table_block in table_blocks:
                table_areas.extend([area.rect for area in table_block.areas])
            _logger.debug(
                f"Extracted {len(table_blocks)} table blocks from page {page_num}"
            )

        # Extract text and image blocks in a single loop
        for block in page.get_text("dict")["blocks"]:
            _logger.debug(f"Extracting block type:{type(block)} {block} ")
            block_results = self._process_single_block(
                block,
                header_y,
                footer_y,
                similarity_blocks,
                table_areas,
                document,
                page_num,
                extract_images,
            )
            page_blocks.extend(block_results)

        return page_blocks

    def _process_text_block_for_similarity(
        self,
        block: dict[str, Any],
        page: fitz.Page,
        document: fitz.Document,
        pre_similarity_blocks: dict[str, list[fitz.Rect]],
    ) -> None:
        """Process a text block to identify potential recurring patterns."""
        bbox = block["bbox"]
        block_text = self._get_block_text(block)[0]

        # Check for page numbers
        if (
            self.is_int(block_text)
            and int(block_text.strip()) <= len(document)
            and bbox[1]
            > page.rect.height
            * (self.FOOTER_HEIGHT_RATIO + self.PAGE_NUMBER_DETECTION_OFFSET)
        ):
            key = "__digit__"
            if key in pre_similarity_blocks:
                pre_similarity_blocks[key].append(bbox)
            else:
                pre_similarity_blocks[key] = [bbox]
        # Check for short recurring text
        elif block_text and len(block_text) < self.MAX_RECURRING_TEXT_LENGTH:
            if block_text in pre_similarity_blocks:
                pre_similarity_blocks[block_text].append(bbox)
            else:
                pre_similarity_blocks[block_text] = [bbox]

    @staticmethod
    def _process_image_block_for_similarity(
        block: dict[str, Any], pre_similarity_blocks: dict[str, list[fitz.Rect]]
    ) -> None:
        """Process an image block to identify potential recurring patterns."""
        bbox = block["bbox"]
        image_hash = generate_hash(block["image"])
        if image_hash in pre_similarity_blocks:
            pre_similarity_blocks[image_hash].append(bbox)
        else:
            pre_similarity_blocks[image_hash] = [bbox]

    def _calculate_similarity_threshold(self, document: fitz.Document) -> float:
        """Calculate the threshold for determining recurring blocks."""
        return len(document) * self.SIMILARITY_PAGE_THRESHOLD

    def _is_recurring_block(
        self, bboxes: list[fitz.Rect], threshold_pages: float
    ) -> tuple[bool, fitz.Rect]:
        """
        Determine if a set of bounding boxes represents a recurring block.

        Returns:
            Tuple of (is_recurring, average_bbox)
        """
        if len(bboxes) <= threshold_pages:
            return False, fitz.Rect(0, 0, 0, 0)

        # Calculate average position more efficiently
        total_x0 = total_y0 = total_x1 = total_y1 = 0.0
        for bbox in bboxes:
            rect = fitz.Rect(bbox) if not isinstance(bbox, fitz.Rect) else bbox
            total_x0 += rect.x0
            total_y0 += rect.y0
            total_x1 += rect.x1
            total_y1 += rect.y1

        count = len(bboxes)
        avg_bbox = fitz.Rect(
            total_x0 / count, total_y0 / count, total_x1 / count, total_y1 / count
        )

        # Count boxes that are near the average position
        nearby_count = sum(
            1 for bbox in bboxes if self._is_rect_similar(bbox, avg_bbox)
        )

        # If enough occurrences are at similar positions, consider it a recurring element
        is_recurring = nearby_count > len(bboxes) * self.SIMILARITY_NEARBY_THRESHOLD
        return is_recurring, avg_bbox

    def _get_similarity_blocks(self, document: fitz.Document) -> dict[str, Any]:
        """
        Identify recurring blocks in the document (headers, footers, page numbers).

        Args:
            document: The PDF document.

        Returns:
            Dictionary mapping content hash to block rect.
        """
        if (
            len(document) < self.MIN_PAGES_FOR_PATTERN
        ):  # Not enough pages to detect patterns
            return {}

        # Track potential recurring blocks
        pre_similarity_blocks: dict[str, list[fitz.Rect]] = {}

        for page in document:
            for block in page.get_text("dict")["blocks"]:
                if block["type"] == self.BLOCK_TYPE_TEXT:
                    self._process_text_block_for_similarity(
                        block, page, document, pre_similarity_blocks
                    )
                elif block["type"] == self.BLOCK_TYPE_IMAGE:
                    self._process_image_block_for_similarity(
                        block, pre_similarity_blocks
                    )

        # Identify blocks that appear on most pages at similar positions
        similarity_blocks = {}
        threshold_pages = self._calculate_similarity_threshold(document)

        for content, bboxes in pre_similarity_blocks.items():
            is_recurring, avg_bbox = self._is_recurring_block(bboxes, threshold_pages)
            if is_recurring:
                similarity_blocks[content] = avg_bbox

        return similarity_blocks

    @staticmethod
    def _create_block(
        content_type: ContentType,
        rect: tuple[float, float, float, float],
        content: str,
        page_num: int,
        font_sizes: list[float] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Block:
        """Create a Block object with common initialization."""
        # Convert single rect to BlockArea
        area = BlockArea(rect=rect, page_num=page_num)
        return Block(
            type=content_type,
            areas=[area],
            content=content,
            font_sizes=font_sizes or [],
            metadata=metadata or {},
        )

    def _should_skip_block_for_similarity(
        self,
        block_text: str,
        bbox: tuple[float, float, float, float],
        similarity_blocks: dict[str, Any],
        document: fitz.Document,
    ) -> bool:
        """Check if a block should be skipped due to similarity patterns."""
        if not similarity_blocks:
            return False

        # Check for page numbers (represented as '__digit__' in similarity_blocks)
        if self.is_int(block_text) and int(block_text) <= len(document):
            recurring_rect = similarity_blocks.get("__digit__")
            if recurring_rect and self._is_rect_similar(recurring_rect, bbox):
                return True

        # Check for short recurring text (headers, footers, etc.)
        elif (
            len(block_text) < self.MAX_RECURRING_TEXT_LENGTH
            and block_text in similarity_blocks
        ):
            recurring_rect = similarity_blocks.get(block_text)
            if recurring_rect and self._is_rect_similar(recurring_rect, bbox):
                return True

        return False

    def _intersects_with_tables(
        self,
        bbox: tuple[float, float, float, float],
        table_areas: list[tuple[float, float, float, float]],
    ) -> bool:
        """Check if a bounding box intersects with any table area."""
        block_rect = fitz.Rect(bbox)
        return any(block_rect.intersects(table_rect) for table_rect in table_areas)

    def _process_text_block(
        self,
        block: dict[str, Any],
        header_y: float,
        footer_y: float,
        similarity_blocks: dict[str, Any],
        table_areas: list[tuple[float, float, float, float]],
        document: fitz.Document,
        page_num: int,
    ) -> list[Block]:
        """
        Process a text block and return Block objects if it passes all filters.

        Args:
            block: PDF text block dictionary from PyMuPDF
            header_y: Y-coordinate of header boundary
            footer_y: Y-coordinate of footer boundary
            similarity_blocks: Dictionary of recurring blocks to exclude
            table_areas: List of table rectangles to exclude
            document: PDF document
            page_num: Page number

        Returns:
            List containing a single Block object if the text block is valid, empty list otherwise
        """
        bbox = block["bbox"]

        # Apply header/footer filtering by checking if block is in content area
        if bbox[1] < header_y or bbox[3] > footer_y:
            return []

        # Skip blocks that intersect with tables
        if self._intersects_with_tables(bbox, table_areas):
            return []

        block_text, font_sizes = self._get_block_text(block)
        if not block_text:
            return []

        # Skip blocks that match recurring patterns (headers/footers)
        if self._should_skip_block_for_similarity(
            block_text, bbox, similarity_blocks, document
        ):
            return []

        return [
            self._create_block(ContentType.text, bbox, block_text, page_num, font_sizes)
        ]

    def _process_image_block(
        self,
        block: dict[str, Any],
        similarity_blocks: dict[str, Any],
        page_num: int,
    ) -> list[Block]:
        """
        Process an image block and return Block objects if it passes all filters.

        Args:
            block: PDF image block dictionary from PyMuPDF
            similarity_blocks: Dictionary of recurring blocks to exclude
            page_num: Page number

        Returns:
            List containing a single Block object if the image block is valid, empty list otherwise
        """
        image_data = block["image"]
        if not self.image_acceptable(image_data):
            return []

        image_hash = generate_hash(image_data)
        if similarity_blocks and image_hash in similarity_blocks:
            return []

        image_content = base64.b64encode(image_data).decode("utf-8")

        # Note: Image blocks use 'rect' key, not 'bbox'
        return [
            self._create_block(
                ContentType.image,
                block["bbox"],
                image_content,
                page_num,
            )
        ]

    @staticmethod
    def image_acceptable(image_data: bytes) -> bool:
        if not image_data or len(image_data) < 100:
            return False
        try:
            with Image.open(io.BytesIO(image_data)) as image:
                w, h = image.size
                return w >= 15 and h >= 15
        except UnidentifiedImageError:  # image corrupted
            return False

    def _process_single_block(
        self,
        block: dict[str, Any],
        header_y: float,
        footer_y: float,
        similarity_blocks: dict[str, Any],
        table_areas: list[tuple[float, float, float, float]],
        document: fitz.Document,
        page_num: int,
        extract_images: bool,
    ) -> list[Block]:
        """
        Process a single PDF block and return the appropriate Block objects.

        This method dispatches to specialized processing methods based on block type.

        Args:
            block: PDF block dictionary from PyMuPDF
            header_y: Y-coordinate of header boundary
            footer_y: Y-coordinate of footer boundary
            similarity_blocks: Dictionary of recurring blocks to exclude
            table_areas: List of table rectangles to exclude
            document: PDF document
            page_num: Page number

        Returns:
            List of Block objects (may be empty if block is filtered out)
        """
        if block["type"] == self.BLOCK_TYPE_TEXT:
            return self._process_text_block(
                block,
                header_y,
                footer_y,
                similarity_blocks,
                table_areas,
                document,
                page_num,
            )
        elif block["type"] == self.BLOCK_TYPE_IMAGE and extract_images:
            return self._process_image_block(block, similarity_blocks, page_num)
        # Unknown block type, skip silently
        return []

    def _get_header_footer_positions(
        self, page: fitz.Page, width: float, height: float
    ) -> tuple[float, float]:
        """
        Detect header and footer positions based on horizontal lines.

        Args:
            page: PDF page
            width: Page width
            height: Page height

        Returns:
            Tuple of (header_y, footer_y) positions
        """
        header_y, footer_y = 0, height

        for drawing in page.get_drawings():
            items = drawing.get("items")
            # Check if it's a horizontal line
            if (
                not items
                or len(items) > 1
                or items[0][0] != "l"
                or items[0][1].y != items[0][2].y
            ):
                continue

            rect = drawing.get("rect")
            # Check if line starts near the left edge
            if rect.x0 > width * self.PAGE_MARGIN_RATIO:
                continue

            # Identify header line
            if (
                not header_y or rect.y0 < header_y
            ) and rect.y0 < height * self.HEADER_HEIGHT_RATIO:
                header_y = rect.y0
            # Identify footer line
            elif (
                footer_y >= height or rect.y0 > footer_y
            ) and rect.y0 > height * self.FOOTER_HEIGHT_RATIO:
                footer_y = rect.y0

        return header_y, footer_y

    def _extract_table_blocks(
        self,
        page: fitz.Page,
        page_num: int,
    ) -> list[Block]:
        result_blocks: list[Block] = []

        with self.pymupdf_lock:
            # multi-threading will cause ValueError("not a textpage of this page")
            # https://github.com/pymupdf/PyMuPDF/issues/3241
            tables: TableFinder = page.find_tables()
        _logger.debug(f"extracted table {tables}")
        if tables:
            for table in tables:
                _logger.debug(f"extracting table {table.bbox}")
                table_content = self._table_to_markdown(table)
                if table_content:
                    table_block = self._create_block(
                        ContentType.table,
                        table.bbox,
                        table_content,
                        page_num,
                    )
                    result_blocks.append(table_block)
        return result_blocks

    def _post_process_blocks(self, blocks: list[Block]) -> list[Block]:
        """
        Post-process blocks with simplified merging logic.

        This method implements a simplified post-processing pipeline:
        1. Merge adjacent text blocks (intra-page and cross-page) based on font size similarity
        2. Merge cross-page table blocks in-place (preserves reading order)

        Args:
            blocks: List of extracted blocks

        Returns:
            List of processed and optimized blocks
        """
        if not blocks:
            return blocks

        _logger.debug(f"Starting post-processing of {len(blocks)} blocks")

        # Step 1: Merge adjacent text blocks (both intra-page and cross-page)
        text_merged_blocks = self._merge_adjacent_text_blocks(blocks)
        _logger.debug(f"Text merging resulted in {len(text_merged_blocks)} blocks")

        # Step 2: Merge cross-page table blocks in-place (preserves reading order)
        final_blocks = self._merge_cross_page_tables(text_merged_blocks)
        _logger.debug(f"Final processing completed with {len(final_blocks)} blocks")

        return final_blocks

    def _merge_adjacent_text_blocks(self, blocks: list[Block]) -> list[Block]:
        """
        Merge adjacent text blocks both within pages and across pages.

        This unified approach handles:
        - Adjacent text blocks on the same page with small vertical gaps
        - Text blocks that continue across page boundaries
        - Text blocks that continue across columns

        Args:
            blocks: List of blocks sorted in reading order

        Returns:
            List with adjacent text blocks merged
        """
        if not blocks:
            return blocks

        merged_blocks = []
        current_text_block = None

        for block in blocks:
            if block.type != ContentType.text:
                # Non-text block: finalize current text block and add the non-text block
                if current_text_block:
                    merged_blocks.append(current_text_block)
                    current_text_block = None
                merged_blocks.append(block)
                continue

            if current_text_block is None:
                # First text block or starting new text sequence
                current_text_block = block
                continue

            # Determine if current text block should be merged with the new block
            should_merge = self._should_merge_text_blocks_unified(
                current_text_block, block
            )

            if should_merge:
                # Merge the blocks
                current_text_block = self._merge_two_blocks(current_text_block, block)
            else:
                # Cannot merge: finalize current block and start new sequence
                merged_blocks.append(current_text_block)
                current_text_block = block

        # Don't forget the last text block
        if current_text_block:
            merged_blocks.append(current_text_block)

        return merged_blocks

    def _should_merge_text_blocks_unified(self, block1: Block, block2: Block) -> bool:
        """
        Determine if two text blocks should be merged using simplified criteria.

        Enhanced rule:
        - Only merge if font sizes are the same and blocks are adjacent
        - OR if block1 is a section header for block2
        - BUT never merge if block2 is a standalone section header UNLESS block1 is also a header

        Args:
            block1: First text block
            block2: Second text block

        Returns:
            True if blocks should be merged
        """
        # Get primary page numbers from first areas
        block1_page = block1.areas[0].page_num if block1.areas else 0
        block2_page = block2.areas[0].page_num if block2.areas else 0

        # Same page merging criteria
        if block1_page == block2_page:
            return self._should_merge_text_blocks_same_page(block1, block2)

        # Cross-page merging criteria
        elif block2_page == block1_page + 1:
            return self._should_merge_text_blocks_cross_page(block1, block2)

        # Too many pages apart
        return False

    def _is_cross_column_continuation(self, block1: Block, block2: Block) -> bool:
        """
        Determine if block2 is a cross-column continuation of block1.

        This handles cases where text flows from one column to another on the same page.
        Common in academic papers with multi-column layouts.

        Args:
            block1: First text block (potentially in left column)
            block2: Second text block (potentially in right column)

        Returns:
            True if block2 continues block1 across columns
        """
        content1 = block1.content.strip()
        content2 = block2.content.strip()

        if not content1 or not content2:
            _logger.debug("Cross-column: Empty content")
            return False

        # Get the rectangles for position analysis
        block1_rect = block1.areas[-1].rect  # Use last area of block1
        block2_rect = block2.areas[0].rect  # Use first area of block2

        _logger.debug(f"Block1 rect: {block1_rect}, Block2 rect: {block2_rect}")

        # Check if blocks are horizontally separated (different columns)
        # Must have a clear horizontal gap indicating different columns
        horizontal_gap = (
            block2_rect[0] - block1_rect[2]
        )  # gap between right edge of block1 and left edge of block2

        _logger.debug(
            f"Horizontal gap: {horizontal_gap:.2f} (min required: {self.CROSS_COLUMN_MIN_HORIZONTAL_GAP})"
        )

        if horizontal_gap < self.CROSS_COLUMN_MIN_HORIZONTAL_GAP:
            _logger.debug("Cross-column: Insufficient horizontal gap")
            return False

        # Check if block1 ends without proper sentence termination (incomplete)
        ends_incomplete = not content1.endswith((".", "!", "?", ":", ";"))
        _logger.debug(
            f'Block1 ends incomplete: {ends_incomplete} (ends with: "{content1[-5:]}")'
        )

        # Check if block2 starts with lowercase (typical continuation)
        starts_lowercase = content2[0].islower() if content2 else False
        _logger.debug(f"Block2 starts lowercase: {starts_lowercase}")

        # Check if block2 is short (likely continuation word/phrase)
        is_short = len(content2) <= self.CROSS_COLUMN_CONTINUATION_MAX_LENGTH
        _logger.debug(f"Block2 is short: {is_short} (length: {len(content2)})")

        # Improved font size compatibility check for mixed font blocks
        font_compatible = True
        if block1.font_sizes and block2.font_sizes:
            # Use the most common font size from each block
            max_font1 = max(block1.font_sizes)
            max_font2 = max(block2.font_sizes)
            font_compatible = max_font2 < max_font1
            # For blocks with mixed fonts, be more lenient
            # font_ratio = max_font2 / max_font1 if max_font1 > 0 else 1.0
            # font_compatible = abs(font_ratio - 1.0) <= 0.2  # Allow 20% font size difference for mixed-font blocks
            _logger.debug(
                f"Font compatible: {font_compatible} (sizes: {max_font1:.1f} vs {max_font2:.1f})"
            )

        # Simplified cross-column logic:
        # 1. Must have horizontal separation (different columns)
        # 2. Block1 must end incomplete (no sentence terminator)
        # 3. Block2 must start with lowercase OR be very short
        # 4. Fonts must be compatible
        is_continuation = (
            horizontal_gap >= self.CROSS_COLUMN_MIN_HORIZONTAL_GAP
            and ends_incomplete
            and font_compatible
            and (starts_lowercase or is_short)
        )

        _logger.debug(f"Cross-column result: {is_continuation}")

        if is_continuation:
            _logger.debug(
                f'CROSS-COLUMN CONTINUATION DETECTED: "{content1[-20:]}..." -> "{content2}"'
            )

        return is_continuation

    def _should_merge_text_blocks_same_page(self, block1: Block, block2: Block) -> bool:
        """
        Determine if two text blocks on the same page should be merged.

        Simplified rule: Merge if block2's max font size is smaller than block1's max font size,
        and the blocks are reasonably positioned (have horizontal overlap or alignment).
        """
        # Get block rectangles for position checks
        block1_last_rect = block1.areas[-1].rect
        block2_first_rect = block2.areas[0].rect

        _logger.debug(
            f'Same-page merge check: "{block1.content[:30]}..." -> "{block2.content[:30]}..."'
        )

        # Check if both blocks have font size information
        if not (block1.font_sizes and block2.font_sizes):
            _logger.debug("Missing font size information, not merging")
            return False

        # Get maximum font sizes
        block1_max_font = max(block1.font_sizes)
        block1_avg_font = sum(block1.font_sizes) / len(block1.font_sizes)
        block2_max_font = max(block2.font_sizes)

        _logger.debug(
            f"Font sizes: block1={block1_max_font:.1f}, block2={block2_max_font:.1f}"
        )

        # Main rule: Only merge if block2 has smaller font than block1
        if block2_max_font > block1_max_font or block2_max_font > block1_avg_font:
            _logger.debug(
                f"Block2 font not smaller: {block2_max_font:.2f} vs "
                f"max:{block1_max_font:.2f} avg:{block1_avg_font:.2f}, not merging"
            )
            return False

        # Check for cross-column continuation first (special case that bypasses position checks)
        is_cross_column = self._is_cross_column_continuation(block1, block2)
        if is_cross_column:
            _logger.debug("Cross-column continuation detected, merging")
            return True

        # Check vertical gap is reasonable for regular same-column merging
        vertical_gap = abs(block2_first_rect[1] - block1_last_rect[3])
        line_height = min(
            block2_first_rect[3] - block2_first_rect[1],
            block1_last_rect[3] - block1_last_rect[1],
        )
        if vertical_gap > line_height:
            _logger.debug(
                f"Vertical gap too large ({vertical_gap:.2f} > {self.VERTICAL_MERGE_THRESHOLD}), not merging"
            )
            return False

        _logger.debug(
            f"MERGING: block2 font smaller ({block2_max_font:.1f} < {block1_max_font:.1f})"
        )
        return True

    def _should_merge_text_blocks_cross_page(
        self, block1: Block, block2: Block
    ) -> bool:
        """
        Determine if text blocks should be merged across consecutive pages.

        Simple criteria:
        1. Font sizes must be the same
        2. Text should look like continuation (ends incomplete, starts lowercase)
        3. Must be in same column position
        """
        content1 = block1.content.strip()
        content2 = block2.content.strip()

        if not content1 or not content2:
            return False

        # Check font size - must be exactly the same to merge
        if block1.font_sizes and block2.font_sizes:
            max_font1 = max(block1.font_sizes)
            avg_font1 = sum(block1.font_sizes) / len(block1.font_sizes)
            max_font2 = max(block2.font_sizes)

            if max_font2 > max_font1 or max_font2 < avg_font1:
                _logger.debug(
                    f"Cross-page font size difference: {max_font2:.2f} vs "
                    f"max:{avg_font1:.2f} avg:{avg_font1:.2f}, not merging"
                )
                return False

        # Check if first block ends without proper punctuation (incomplete sentence)
        ends_incomplete = not content1.endswith((".", "!", "?", ":", ";"))

        # Check if second block starts with lowercase (continuation)
        starts_continuation = content2[0].islower()

        # Check if blocks are horizontally aligned (same column)
        block1_last_rect = block1.areas[-1].rect
        block2_first_rect = block2.areas[0].rect
        same_column = (
            abs(block1_last_rect[0] - block2_first_rect[0]) < self.SAME_COLUMN_TOLERANCE
        )

        return ends_incomplete and starts_continuation and same_column

    def _merge_cross_page_tables(self, blocks: list[Block]) -> list[Block]:
        """
        Merge table blocks that span across multiple pages in-place, preserving reading order.

        This method identifies table blocks on consecutive pages that likely represent
        a single logical table and merges them directly in the list, maintaining the
        original reading order.

        Args:
            blocks: List of blocks after text merging

        Returns:
            List with cross-page table blocks merged in-place (reading order preserved)
        """
        if not blocks:
            return blocks

        # Track indices that have been merged and should be skipped
        merged_indices: set[int] = set()
        result_blocks = []

        for i, current_block in enumerate(blocks):
            # Skip blocks that have already been merged into another block
            if i in merged_indices:
                continue

            if current_block.type == ContentType.table:
                # Try to find continuation tables in subsequent blocks
                merged_block = current_block

                # Look ahead for continuation tables
                for j in range(i + 1, len(blocks)):
                    # Skip already merged blocks
                    if j in merged_indices:
                        continue

                    next_block = blocks[j]

                    # Only consider tables from consecutive pages
                    if (
                        next_block.type == ContentType.table
                        and self._is_table_continuation(merged_block, next_block)
                    ):
                        # Merge the tables
                        merged_block = self._merge_table_blocks(
                            merged_block, next_block
                        )
                        # Mark this block as merged so we skip it later
                        merged_indices.add(j)

                result_blocks.append(merged_block)
            else:
                # Non-table block, keep as-is
                result_blocks.append(current_block)

        return result_blocks

    def _is_table_continuation(
        self, table_block: Block, candidate_block: Block
    ) -> bool:
        """
        Check if candidate_block is a continuation of table_block.

        Args:
            table_block: The table block to check continuation for
            candidate_block: The potential continuation block

        Returns:
            True if candidate_block continues table_block
        """
        # Must be on consecutive pages (considering multiple areas)
        table_pages = {area.page_num for area in table_block.areas}
        candidate_pages = {area.page_num for area in candidate_block.areas}

        # Check if any candidate page immediately follows any table page
        is_consecutive = any(
            cand_page == table_page + 1
            for table_page in table_pages
            for cand_page in candidate_pages
        )

        if not is_consecutive:
            return False

        # Check horizontal alignment using first areas (main positioning)
        table_rect = table_block.areas[0].rect
        candidate_rect = candidate_block.areas[0].rect

        horizontal_alignment_diff = abs(table_rect[0] - candidate_rect[0])

        if horizontal_alignment_diff < self.TABLE_HORIZONTAL_ALIGNMENT_THRESHOLD:
            # Check if they have similar width (indicating same table structure)
            table_width = table_rect[2] - table_rect[0]
            candidate_width = candidate_rect[2] - candidate_rect[0]
            width_diff_ratio = abs(table_width - candidate_width) / max(
                table_width, candidate_width
            )

            return width_diff_ratio < self.TABLE_WIDTH_DIFFERENCE_RATIO

        return False

    @staticmethod
    def _merge_table_blocks(block1: Block, block2: Block) -> Block:
        """
        Merge two table blocks into a single table block, preserving their separate areas.

        Args:
            block1: First table block
            block2: Second table block

        Returns:
            Merged table block with preserved areas
        """
        # Combine content (assuming both are markdown tables)
        content1 = block1.content.strip()
        content2 = block2.content.strip()

        # Remove header from second table if it's a continuation
        lines1 = content1.split("\n")
        lines2 = content2.split("\n")

        # If second table has header separator, remove header and separator
        if len(lines2) > 2 and "|" in lines2[1] and "-" in lines2[1]:
            # Skip header and separator in continuation
            combined_content = "\n".join(lines1 + lines2[2:])
        else:
            # Simple concatenation
            combined_content = content1 + "\n" + content2

        # Preserve all areas from both blocks instead of merging them
        combined_areas = block1.areas + block2.areas

        return Block(
            type=ContentType.table,
            areas=combined_areas,
            content=combined_content,
            font_sizes=[],
        )

    @staticmethod
    def _merge_two_blocks(block1: Block, block2: Block) -> Block:
        """
        Merge two text blocks into one, preserving their separate areas.
        """
        # Combine content with appropriate spacing
        content1 = block1.content.strip()
        content2 = block2.content.strip()

        combined_content = content1 + " " + content2
        # Preserve all areas from both blocks instead of merging them
        combined_areas = block1.areas + block2.areas

        # Combine font sizes efficiently using set operations
        combined_font_sizes = list(set(block1.font_sizes + block2.font_sizes))

        return Block(
            type=ContentType.text,
            areas=combined_areas,
            content=combined_content,
            font_sizes=combined_font_sizes,
        )

    @staticmethod
    def _get_block_text(block: dict[str, Any]) -> tuple[str, list[float]]:
        """Extract text and font sizes from a text block."""
        if not block.get("lines"):
            return "", []

        lines = []
        font_sizes_set = set()

        for line in block["lines"]:
            spans = line.get("spans", [])
            line_text_parts = []
            for span in spans:
                text = span.get("text", "").strip()
                if text:
                    line_text_parts.append(text)
                    size = span.get("size")
                    if size is not None:
                        font_sizes_set.add(size)

            if line_text_parts:
                lines.append(" ".join(line_text_parts))

        # Convert set to sorted list for consistent ordering
        font_sizes = sorted(font_sizes_set)
        return " ".join(lines), font_sizes

    @staticmethod
    def _table_to_markdown(table: Table) -> str:
        """Convert a PDF table to Markdown format."""
        # Convert table to pandas DataFrame
        table_df = table.to_pandas()
        if table_df.empty:
            return ""

        rows: list[list[str]] = [
            table_df.columns.astype(str).tolist(),
            *table_df.astype(str).values.tolist(),
        ]
        return table_markdown(rows)

    @staticmethod
    def _is_rect_similar(
        rect1: tuple[float, float, float, float] | fitz.Rect,
        rect2: tuple[float, float, float, float] | fitz.Rect,
        tolerance: float | None = None,
    ) -> bool:
        """
        Check if two rectangles are in similar positions.

        Args:
            rect1: First rectangle
            rect2: Second rectangle
            tolerance: Tolerance percentage (defaults to class constant)

        Returns:
            True if similar, False otherwise
        """
        if tolerance is None:
            tolerance = PyMuPDFParser.SIMILARITY_POSITION_THRESHOLD

        r1 = fitz.Rect(rect1) if not isinstance(rect1, fitz.Rect) else rect1
        r2 = fitz.Rect(rect2) if not isinstance(rect2, fitz.Rect) else rect2
        w_ref = max((r1.width + r2.width) / 2.0, 1e-6)
        h_ref = max((r1.height + r2.height) / 2.0, 1e-6)

        # Check if positions are within tolerance
        return bool(
            abs(r1.x0 - r2.x0) < w_ref * tolerance
            and abs(r1.y0 - r2.y0) < h_ref * tolerance
            and abs(r1.x1 - r2.x1) < w_ref * tolerance
            and abs(r1.y1 - r2.y1) < h_ref * tolerance
        )

    @staticmethod
    def is_int(text: str) -> bool:
        text = text.strip()
        if not text:
            return False
        if text[0] in ("-", "+"):
            return text[1:].isdecimal()
        return text.isdecimal()
