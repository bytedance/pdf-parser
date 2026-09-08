ARG BASE_IMAGE=python:3.11-slim-bookworm

FROM ${BASE_IMAGE} AS exporter

USER root

RUN command -v uv >/dev/null || python3 -m pip install --no-cache-dir uv

WORKDIR /app

ADD pyproject.toml uv.lock .

RUN uv export --extra server --no-hashes --no-dev --no-emit-project -o requirements.txt

FROM ${BASE_IMAGE}

USER root

COPY --from=exporter /app/requirements.txt .

RUN pip install -r requirements.txt

USER 65534:65534

WORKDIR /app

COPY hi_pdf_parser ./hi_pdf_parser

CMD ["python3", "-m", "hi_pdf_parser", "serve"]
