from enum import StrEnum

from pydantic import BaseModel


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
