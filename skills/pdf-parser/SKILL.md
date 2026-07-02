---
name: pdf-parser
description: Parse PDF files into Markdown plus images/manifest fully offline via the pdf-parser CLI (pymupdf-only, no docling/OCR/VLM). Invoke when the user needs to extract or convert a PDF's text/content to Markdown in an offline environment.
---

# pdf-parser — Offline PDF Parsing CLI

Parse PDF files into clean Markdown plus extracted images and a structured manifest, using the installed `pdf-parser` CLI. This is a lightweight, fully offline tool.

Use this skill whenever a task involves extracting the **content** of a PDF in an offline setting — e.g. "parse this PDF offline", "convert this PDF to markdown without network", "extract the text from this PDF locally".

## Prerequisites

This skill assumes the `pdf-parser` command is already installed and on `PATH`
(it is the console-script entry point bundled in the `pdf-parser` Python package).

**Step 0 — always verify the command exists first:**

```bash
pdf-parser --help
```

If that succeeds, proceed. If it fails, stop and show the user the install
guidance below instead of guessing paths.

### If `pdf-parser: command not found`

The package is not installed in the active environment. Use the bundled
`pdf-parser` package from Git. This requires `uv` and network access to
`github.com`.

```bash
uv tool install --force "git+https://github.com/bytedance/pdf-parser.git"
```

To pin a branch, tag, or commit:

```bash
uv tool install --force "git+https://github.com/bytedance/pdf-parser.git@<ref>"
```

If `uv` is not installed, install it first:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Command shape

Global flags (`-v`, `-vv`, `--quiet`) go **before** the subcommand, git/docker-style:

```bash
pdf-parser [-v|-vv|--quiet] parse <file.pdf> [options]
pdf-parser [-v|-vv|--quiet] batch <file.pdf>... [options]
pdf-parser batch --from-file <list.txt> [options]
```

- `parse` — exactly one PDF; prints one JSON envelope to stdout.
- `batch` — many PDFs (positional, or `--from-file`); prints NDJSON (one envelope per line), in input order. Sequential, keep-going by default; add `--abort-on-error` to stop at the first failure.

### Common options

| Option | Meaning |
|--------|---------|
| `--out DIR` | Output root (default `./out`). Each file goes to `<out>/<stem>/`. |
| `--pages SPEC` / `-p` | Single page `5`, continuous range `1-20`, or continuous comma `3,4`. Non-continuous (`1,5,9`), reversed, or `0`/negative are rejected (exit 2). |
| `--format markdown` | Output format; only `markdown` is supported. |
| `--out-naming stem` | Output naming strategy; only `stem` is supported. |
| `--from-file FILE` | (batch only) Manifest file, one path per line; mutually exclusive with positional files. |
| `--abort-on-error` | (batch only) Stop at the first failure. |

## Output layout

Each document produces `<out>/<stem>/`:

```
<out>/<stem>/
  document.md          # parsed Markdown (read this for content)
  manifest.json        # status, mode_used, outputs, assets, stats, warnings
  images/              # page-{page:03d}-figure-{idx:03d}.png (figures, if any)
  logs/
    profiling.json
    stderr.log
```

After parsing, read `document.md` for the content and `manifest.json` for metadata (e.g. extracted `assets`, `stats`, `warnings`).

## Stdout envelope

Both success and error use the same JSON shape; branch on `status`.

Success:
```json
{"status":"success","input":"...","out":"out/<stem>","mode":"local","mode_used":"local","fallback_reason":null,"outputs":{"markdown":"document.md"},"stats":{"pages":7,"duration_ms":1234},"warnings":[]}
```

Error:
```json
{"status":"error","input":"...","error_type":"INPUT_CORRUPT","message":"...","exit_code":10,"hint":"..."}
```

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | success |
| 1 | uncaught internal error |
| 2 | CLI usage error (bad flags or `--pages` spec) |
| 10 | input problem: `INPUT_NOT_FOUND`, `INPUT_FORMAT_UNSUPPORTED`, `PAGE_RANGE_OUT_OF_BOUNDS`, `INPUT_CORRUPT` (encrypted PDF) |
| 40 | `OUTPUT_WRITE_FAILURE` |

For `batch`: all-success → 0; partial failure → 1; all-failed → first failure's code; `--abort-on-error` → the triggering code.

## Examples

```bash
# Parse a single PDF, default output to ./out/<stem>/
pdf-parser parse report.pdf

# Specific page range, verbose
pdf-parser -v parse report.pdf --pages 2-4 --out ./out

# Batch, keep going, NDJSON to stdout
pdf-parser batch a.pdf b.pdf --out ./out

# Batch from a manifest file, stop at first error
pdf-parser batch --from-file files.txt --abort-on-error --out ./out
```

## Gotchas

- pdf-parser only supports **PDF** for `parse`/`batch`. A non-PDF input → exit 10 `INPUT_FORMAT_UNSUPPORTED`; it does no OCR/Office/image conversion, so use a tool that supports those formats instead.
- It is **text-extraction only** (no OCR). A scanned PDF with no text layer yields little/no text and a `local_mode_empty_text` warning — there is no offline OCR fallback.
- Global flags must precede the subcommand: `pdf-parser -v parse x.pdf`, **not** `pdf-parser parse x.pdf -v` (the latter errors with "unrecognized arguments").
- Encrypted PDFs → exit 10 `INPUT_CORRUPT` (decrypt with qpdf/pdftk first). 0-byte or otherwise corrupt PDFs that PyMuPDF can't open → also exit 10 `INPUT_CORRUPT`.
- `batch` rejects two inputs sharing the same stem (output dir collision) and rejects mixing positional files with `--from-file`.
