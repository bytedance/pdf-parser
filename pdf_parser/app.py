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

import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware

from .config import PyMuPDFParserConfig
from .datamodel import HealthCheckResponse, ParseRequest, ParseResponse
from .parser import PyMuPDFParser

_logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    parser = PyMuPDFParser(PyMuPDFParserConfig())
    app = FastAPI(
        title="PDF Parser Serve",
    )

    app.add_middleware(GZipMiddleware, minimum_size=5 * 1024, compresslevel=5)

    @app.get("/health")
    def health() -> HealthCheckResponse:
        return HealthCheckResponse()

    @app.post("/parse")
    def parse(request: ParseRequest):
        try:
            blocks, metadata = parser.parse(
                request.file,
                password=request.password,
                extract_images=request.extract_images,
                extract_tables=request.extract_tables,
            )
        except PermissionError as e:
            raise HTTPException(
                status_code=400, detail=f"Can not open encrypted file: {e}"
            )
        except FileNotFoundError:
            raise HTTPException(
                status_code=404, detail=f"File not found: {request.file}"
            )
        except Exception as e:
            _logger.exception(f"Parse file fail: {request.file}")
            raise HTTPException(status_code=500, detail=f"Parse extraction: {e}")
        return ParseResponse(blocks=blocks, metadata=metadata)

    return app
