ARG BASE_IMAGE=python:3.11-slim-bookworm

FROM ${BASE_IMAGE}

USER 0

WORKDIR /app

ADD pyproject.toml .

RUN pip install . && pip uninstall -y pdf-parser

COPY pdf_parser ./pdf_parser

CMD ["python3", "-m", "pdf_parser"]
