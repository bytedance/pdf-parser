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
