ARG BASE_IMAGE=python:3.11-slim-bookworm

FROM ${BASE_IMAGE} AS exporter

RUN curl -LsSf https://astral.sh/uv/install.sh | sh

WORKDIR /app

ADD pyproject.toml uv.lock .

RUN /root/.local/bin/uv export --extra server --no-hashes --no-dev -o requirements.txt

FROM ${BASE_IMAGE}

COPY --from=exporter --chown=nobody:nogroup /app/requirements.txt .

RUN pip install -r requirements.txt

USER nobody:nogroup

WORKDIR /app

COPY hi_pdf_parser ./hi_pdf_parser

CMD ["python3", "-m", "hi_pdf_parser", "serve"]
