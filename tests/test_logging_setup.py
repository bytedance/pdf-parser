from __future__ import annotations

import logging
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from hi_pdf_parser import logging_setup


class LoggingSetupTest(unittest.TestCase):
    def tearDown(self) -> None:
        logger = logging.getLogger(logging_setup.PACKAGE_LOGGER_NAME)
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()
        logger.setLevel(logging.NOTSET)
        logger.propagate = True
        logging_setup._stderr_handler = None

    def test_file_handler_captures_package_child_loggers(self) -> None:
        logging_setup.configure_logging(level=logging.INFO)

        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "stderr.log"
            handler = logging_setup.attach_file_handler(log_path)
            try:
                logging.getLogger("hi_pdf_parser.parser").info(
                    "parser_event input=%s", "sample.pdf"
                )
            finally:
                logging_setup.detach_file_handler(handler)

            self.assertIn("parser_event input=sample.pdf", log_path.read_text())

    def test_quiet_applies_to_package_child_loggers(self) -> None:
        logging_setup.configure_logging(level=logging.DEBUG, quiet=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "stderr.log"
            handler = logging_setup.attach_file_handler(log_path)
            try:
                child_logger = logging.getLogger("hi_pdf_parser.parser")
                child_logger.info("hidden_info")
                child_logger.warning("visible_warning")
            finally:
                logging_setup.detach_file_handler(handler)

            content = log_path.read_text()
            self.assertNotIn("hidden_info", content)
            self.assertIn("visible_warning", content)

    def test_app_import_does_not_configure_root_logging(self) -> None:
        script = (
            "import logging\n"
            "assert not logging.getLogger().handlers\n"
            "import hi_pdf_parser.app\n"
            "print(len(logging.getLogger().handlers))\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.stdout.strip(), "0")


if __name__ == "__main__":
    unittest.main()
