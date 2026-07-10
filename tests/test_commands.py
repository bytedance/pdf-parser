from __future__ import annotations

import io
import json
import logging
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from hi_pdf_parser import logging_setup
from hi_pdf_parser.__main__ import main

FIXTURES = Path(__file__).parent / "fixtures"


class CommandTest(unittest.TestCase):
    def tearDown(self) -> None:
        logger = logging.getLogger(logging_setup.PACKAGE_LOGGER_NAME)
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()
        logger.setLevel(logging.NOTSET)
        logger.propagate = True
        logging_setup._stderr_handler = None

    def _run_command(self, argv: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_parse_writes_single_success_envelope_and_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir) / "out"

            code, stdout, _stderr = self._run_command(
                ["parse", str(FIXTURES / "normal.pdf"), "--out", str(out_dir)]
            )

            envelope = json.loads(stdout)
            self.assertEqual(code, 0)
            self.assertEqual(envelope["status"], "success")
            self.assertEqual(len(stdout.splitlines()), 1)
            self.assertTrue((out_dir / "normal" / "document.md").exists())
            manifest_path = out_dir / "normal" / "manifest.json"
            self.assertTrue(manifest_path.exists())
            self.assertTrue((out_dir / "normal" / "logs" / "stderr.log").exists())

    def test_parse_pages_limits_reported_page_count(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir) / "out"

            code, stdout, _stderr = self._run_command(
                [
                    "parse",
                    str(FIXTURES / "multipage.pdf"),
                    "--pages",
                    "1",
                    "--out",
                    str(out_dir),
                ]
            )

            envelope = json.loads(stdout)
            self.assertEqual(code, 0)
            self.assertEqual(envelope["status"], "success")
            self.assertEqual(envelope["stats"]["pages"], 1)

    def test_parse_pages_accepts_continuous_comma_range(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir) / "out"

            code, stdout, _stderr = self._run_command(
                [
                    "parse",
                    str(FIXTURES / "multipage.pdf"),
                    "--pages",
                    "1,2",
                    "--out",
                    str(out_dir),
                ]
            )

            envelope = json.loads(stdout)
            self.assertEqual(code, 0)
            self.assertEqual(envelope["status"], "success")
            self.assertEqual(envelope["stats"]["pages"], 2)

    def test_parse_pages_rejects_non_continuous_comma_range(self) -> None:
        code, stdout, stderr = self._run_command(
            [
                "parse",
                str(FIXTURES / "multipage.pdf"),
                "--pages",
                "1,3",
            ]
        )

        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("Invalid --pages value", stderr)

    def test_parse_multiple_emits_ndjson_and_returns_partial_failure_code(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir) / "out"

            code, stdout, _stderr = self._run_command(
                [
                    "parse",
                    str(FIXTURES / "normal.pdf"),
                    str(FIXTURES / "not-a-pdf.jpeg"),
                    "--out",
                    str(out_dir),
                ]
            )

            envelopes = [json.loads(line) for line in stdout.splitlines()]
            self.assertEqual(code, 1)
            self.assertEqual(
                [item["status"] for item in envelopes], ["success", "error"]
            )
            self.assertEqual(envelopes[1]["error_type"], "INPUT_FORMAT_UNSUPPORTED")
            self.assertTrue((out_dir / "normal" / "document.md").exists())

    def test_parse_requires_at_least_one_input(self) -> None:
        code, stdout, stderr = self._run_command(["parse"])

        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("parse requires at least one file", stderr)


if __name__ == "__main__":
    unittest.main()
