ARG BASE_IMAGE=python:3.11-slim-bookworm

FROM ${BASE_IMAGE} AS exporter

USER root

RUN command -v uv >/dev/null || python3 -m pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN uv export \
    --extra server \
    --frozen \
    --no-dev \
    --no-emit-project \
    --no-hashes \
    --output-file requirements.txt

FROM ${BASE_IMAGE}

USER root

WORKDIR /app

COPY --from=exporter /app/requirements.txt /tmp/requirements.txt
RUN python3 -m pip install \
    --no-cache-dir \
    --only-binary=:all: \
    --requirement /tmp/requirements.txt \
    && rm -f /tmp/requirements.txt

COPY --chown=65534:65534 hi_pdf_parser ./hi_pdf_parser

USER 65534:65534

CMD ["python3", "-m", "hi_pdf_parser", "serve"]
