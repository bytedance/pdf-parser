"""Per-call parser runtime options."""

from __future__ import annotations

from dataclasses import dataclass

ParseRuntimeValue = bool | str | tuple[int, int]


@dataclass(frozen=True)
class ParseRuntimeOptions:
    """Options that may differ for each parser.parse invocation."""

    extract_images: bool | None = None
    extract_tables: bool | None = None
    password: str | None = None
    page_range: tuple[int, int] | None = None

    def to_kwargs(self) -> dict[str, ParseRuntimeValue]:
        values: dict[str, ParseRuntimeValue | None] = {
            "extract_images": self.extract_images,
            "extract_tables": self.extract_tables,
            "password": self.password,
            "page_range": self.page_range,
        }
        return {key: value for key, value in values.items() if value is not None}
