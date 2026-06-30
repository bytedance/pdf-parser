"""Output contract writer for the docparser CLI.

Produces the normalized per-document layout::

    <out>/<stem>/
      document.md
      manifest.json
      images/
        page-001-figure-001.png
      logs/
        profiling.json
        stderr.log

Used by the ``local`` parsing path: the local parser writes its own already-named
PNGs directly into ``images/`` and supplies the asset list, so only
manifest/markdown writing is needed.

This module contains **zero imports** of ``docling`` or ``docling_pipeline`` and
is safe for use in the lightweight ``litepdf`` CLI path.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from typing import TYPE_CHECKING, Any

from .errors import OutputWriteError

if TYPE_CHECKING:
    from pathlib import Path


def prepare_output_dir(out_root: Path, stem: str) -> Path:
    """Create ``<out>/<stem>/`` (overwriting if it exists) and return it.

    Also creates the ``images/`` and ``logs/`` subdirectories. Any write error
    is surfaced as :class:`OutputWriteError` (exit code 40).
    """
    try:
        out_root.mkdir(parents=True, exist_ok=True)
        stem_dir = out_root / stem
        # 防御路径遍历：stem 来源于用户输入文件名的 ``Path.stem``，诸如
        # ``...pdf`` 会得到 ``..``、``..pdf`` 会得到 ``.``，直接拼接后对
        # ``out_root/..`` 执行 rmtree 会误删输出根目录的父级/同级内容。
        # 仅接受恰好位于 out_root 之内一层的目录。
        if stem_dir.resolve().parent != out_root.resolve():
            raise OutputWriteError(f"非法的输出子目录名: {stem!r}")
        if stem_dir.exists():
            shutil.rmtree(stem_dir)
        (stem_dir / "images").mkdir(parents=True, exist_ok=True)
        (stem_dir / "logs").mkdir(parents=True, exist_ok=True)
        return stem_dir
    except OSError as exc:
        raise OutputWriteError(f"无法创建输出目录 {out_root / stem}: {exc}") from exc


def images_dir(stem_dir: Path) -> Path:
    return stem_dir / "images"


def logs_dir(stem_dir: Path) -> Path:
    return stem_dir / "logs"


def stderr_log_path(stem_dir: Path) -> Path:
    return logs_dir(stem_dir) / "stderr.log"


def write_document(stem_dir: Path, markdown: str) -> str:
    """Write ``document.md`` and return its relative name."""
    try:
        (stem_dir / "document.md").write_text(markdown, encoding="utf-8")
    except OSError as exc:
        raise OutputWriteError(f"无法写入 document.md: {exc}") from exc
    return "document.md"


def write_manifest(stem_dir: Path, manifest: dict[str, Any]) -> None:
    try:
        (stem_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        raise OutputWriteError(f"无法写入 manifest.json: {exc}") from exc


def write_profiling(stem_dir: Path, profiling: dict[str, Any]) -> None:
    try:
        (logs_dir(stem_dir) / "profiling.json").write_text(
            json.dumps(profiling, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        raise OutputWriteError(f"无法写入 profiling.json: {exc}") from exc


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


# Matches inline LaTeX formulas: ``$ ... $``, no cross-line, no block ``$$...$$``.
# Used by the docling post-processor (defined here so this module stays docling-free).
_INLINE_MATH_RE = re.compile(r"(?<!\\)\$(?!\$)([^\n$]+?)(?<!\\)\$(?!\$)")


def _restore_inline_math_underscores(markdown: str) -> str:
    r"""还原 docling Markdown 序列化器对 inline 公式内 ``_`` 的错误转义。

    docling 的 ``escape_underscores=True`` 会对 TEXT 节点全文执行转义，
    但不会识别 ``$...$`` 内的 LaTeX 公式区间，导致 ``$\theta_{1}$`` 被错误
    输出为 ``$\theta\_{1}$``。本函数仅将 inline math 区间内的 ``\_`` 还原为 ``_``，
    不影响正文中的正常转义。

    在 ``export_to_markdown()`` 返回值上调用，影响面极小。
    """
    if "$" not in markdown or r"\_" not in markdown:
        return markdown

    def _restore(match: re.Match[str]) -> str:
        body = match.group(1)
        restored = body.replace(r"\_", "_")
        return f"${restored}$"

    return _INLINE_MATH_RE.sub(_restore, markdown)


def build_manifest(
    input_path: str,
    mode: str,
    mode_used: str,
    status: str,
    assets: list[dict[str, Any]],
    stats: dict[str, Any],
    warnings: list[str],
    fallback_reason: str | None,
) -> dict[str, Any]:
    return {
        "input": input_path,
        "mode": mode,
        "mode_used": mode_used,
        "fallback_reason": fallback_reason,
        "status": status,
        "outputs": {"markdown": "document.md"},
        "assets": assets,
        "stats": stats,
        "warnings": warnings,
    }
