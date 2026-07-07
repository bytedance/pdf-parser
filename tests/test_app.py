from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from hi_pdf_parser.app import create_app


class AppTest(unittest.TestCase):
    def test_parse_passes_request_runtime_options_to_parser(self) -> None:
        parser = Mock()
        parser.parse.return_value = ([], {"page_count": 0})

        with patch("hi_pdf_parser.app.create_parser", return_value=parser):
            client = TestClient(create_app())
            response = client.post(
                "/parse",
                json={
                    "file": "/tmp/sample.pdf",
                    "password": "secret",
                    "extract_images": False,
                    "extract_tables": False,
                    "page_range": [2, 4],
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"blocks": [], "metadata": {"page_count": 0}})
        parser.parse.assert_called_once_with(
            "/tmp/sample.pdf",
            password="secret",
            extract_images=False,
            extract_tables=False,
            page_range=(2, 4),
        )

    def test_parse_rejects_invalid_page_range(self) -> None:
        parser = Mock()

        with patch("hi_pdf_parser.app.create_parser", return_value=parser):
            client = TestClient(create_app())
            response = client.post(
                "/parse",
                json={
                    "file": "/tmp/sample.pdf",
                    "page_range": [4, 2],
                },
            )

        self.assertEqual(response.status_code, 422)
        parser.parse.assert_not_called()


if __name__ == "__main__":
    unittest.main()
