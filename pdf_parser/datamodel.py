from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class HealthCheckResponse(BaseModel):
    status: str = "ok"


class ContentType(StrEnum):
    image = "image"
    text = "text"
    table = "table"


class BlockArea(BaseModel):
    rect: tuple[float, float, float, float]
    page_num: int


class Block(BaseModel):
    type: ContentType
    areas: list[BlockArea]
    content: str
    font_sizes: list[float] = []


class ParseRequest(BaseModel):
    file: str = Field(description="file path", examples=["/path/my.pdf"])
    password: str | None = Field(None, description="file password")
    extract_images: bool = Field(True, description="enable image extraction")
    extract_tables: bool = Field(True, description="enable table extraction")


class ParseResponse(BaseModel):
    blocks: list[Block]
    metadata: dict[str, Any]
