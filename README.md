# PDF Parser

A HTTP server converting PDF file to text blocks.

This project uses [PyMuPDF](https://pymupdf.readthedocs.io/en/latest/) and complies with its open-source licensing obligations.

## Developing

### Install

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), and then install pre-commit:

```bash
uv tool install pre-commit --with pre-commit-uv --force-reinstall
```

### Coding Style Guidelines

To run the checks on-demand repeatedly until it passes. If you see mypy errors you might need to provide typing hints where requested.

```bash
uv run pre-commit run --all-files
```
