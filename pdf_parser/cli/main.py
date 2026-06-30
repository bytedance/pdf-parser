"""``litepdf`` 命令行入口。

litepdf 是轻量离线 PDF→Markdown 工具，仅做 local 解析（pymupdf），不含
remote / OCR / VLM。全局标志（``-v`` / ``-vv`` / ``--quiet``）置于子命令之前，
与 docparser / git / docker 习惯一致。

``parse`` 解析单文件并打印单行 JSON envelope；``batch`` 解析多文件并打印 NDJSON。
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .errors import EXIT_USAGE
from .page_range import parse_page_spec


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="litepdf",
        description="轻量离线 PDF→Markdown CLI：仅依赖 pymupdf 的本地文本/图片提取。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  litepdf parse report.pdf --out ./out
  litepdf batch a.pdf b.pdf --out ./out
  litepdf batch --from-file files.txt --out ./out
  litepdf -v parse report.pdf --out ./out

查看子命令参数:
  litepdf parse --help
  litepdf batch --help

注意:
  - 全局参数必须放在子命令之前，例如 `litepdf -v parse ...`。
  - litepdf 仅支持 PDF；其他格式请使用 docparser。""",
    )
    parser.add_argument("--quiet", action="store_true", help="关闭进度日志。")
    parser.add_argument(
        "-v", "--verbose", action="count", default=0, help="提升 stderr 日志级别，可叠加。"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    parse_p = subparsers.add_parser("parse", help="解析单个 PDF，stdout 输出单行 JSON envelope。")
    parse_p.add_argument("file", help="待解析的单个 PDF 路径。")
    _add_common_args(parse_p)

    batch_p = subparsers.add_parser("batch", help="批量解析多个 PDF，stdout 输出 NDJSON。")
    batch_p.add_argument("files", nargs="*", help="待解析的多个 PDF 路径。")
    batch_p.add_argument("--from-file", help="每行一个文件路径的清单文件，与位置参数二选一。")
    batch_p.add_argument("--abort-on-error", action="store_true", help="遇到首个失败即停止。")
    _add_common_args(batch_p)

    return parser


def _add_common_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--out", type=Path, default=Path("./out"), help="输出根目录，默认 ./out。")
    p.add_argument("--format", choices=["markdown"], default="markdown", help="输出格式，当前仅支持 markdown。")
    p.add_argument(
        "--pages",
        "-p",
        type=parse_page_spec,
        default=None,
        help="页码范围：单页 n、区间 a-b、连续页 3,4；不支持多段非连续范围。",
    )
    p.add_argument("--out-naming", choices=["stem"], default="stem", help="输出命名策略，当前仅支持 stem。")


def _page_range(args: argparse.Namespace) -> tuple[int, int] | None:
    if args.pages is None:
        return None
    return args.pages[0]


def _collect_batch_inputs(
    args: argparse.Namespace, parser: argparse.ArgumentParser
) -> list[Path]:
    if args.from_file and args.files:
        parser.error("--from-file 与位置参数 files 不能同时提供。")
    if not args.from_file and not args.files:
        parser.error("batch 需要提供至少一个文件，或使用 --from-file。")

    if args.from_file:
        from_file = Path(args.from_file)
        if not from_file.is_file():
            parser.error(f"--from-file 指向的清单不存在: {from_file}")
        lines = from_file.read_text(encoding="utf-8").splitlines()
        inputs = [Path(line.strip()) for line in lines if line.strip()]
    else:
        inputs = [Path(f) for f in args.files]

    seen: dict[str, Path] = {}
    for path in inputs:
        if path.stem in seen:
            parser.error(
                f"stem 冲突: {path} 与 {seen[path.stem]} 共享输出目录名 '{path.stem}'。"
            )
        seen[path.stem] = path

    return inputs


def _make_config(args: argparse.Namespace):
    from .runner import ParseConfig

    return ParseConfig(out=args.out, page_range=_page_range(args))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    from .logging_setup import configure_logging

    level = logging.INFO
    if args.verbose >= 2:
        level = logging.DEBUG
    elif args.verbose == 1:
        level = logging.INFO
    configure_logging(level=level, quiet=args.quiet)

    from . import envelope as env, runner

    if args.command == "parse":
        config = _make_config(args)
        envelope, exit_code = runner.run_parse(Path(args.file), config)
        sys.stdout.write(env.dumps(envelope) + "\n")
        sys.stdout.flush()
        return exit_code

    if args.command == "batch":
        inputs = _collect_batch_inputs(args, parser)
        config = _make_config(args)

        def emit(envelope: dict) -> None:
            sys.stdout.write(env.dumps(envelope) + "\n")
            sys.stdout.flush()

        return runner.run_batch(
            inputs, config, abort_on_error=args.abort_on_error, emit=emit
        )

    parser.error(f"未知命令: {args.command}")  # pragma: no cover
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
