# PDF Parser

A HTTP server converting PDF file to text blocks.

This project uses [PyMuPDF](https://pymupdf.readthedocs.io/en/latest/) and complies with its open-source licensing obligations.

## Installation

To use PDF Parser, simply install `hi-pdf-parser` from your package manager, e.g. pip:

```bash
pip install hi-pdf-parser
```

## Developing

### Prepare

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```bash
uv sync --all-groups
```

### Coding Style Guidelines

To run the checks on-demand repeatedly until it passes. If you see mypy errors you might need to provide typing hints where requested.

```bash
uv run pre-commit run --all-files
```
