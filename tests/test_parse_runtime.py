from __future__ import annotations

import unittest

from hi_pdf_parser.parse_runtime import ParseRuntimeOptions


class ParseRuntimeOptionsTest(unittest.TestCase):
    def test_to_kwargs_omits_unspecified_options(self) -> None:
        self.assertEqual(ParseRuntimeOptions().to_kwargs(), {})

    def test_to_kwargs_keeps_false_boolean_overrides(self) -> None:
        options = ParseRuntimeOptions(extract_images=False, extract_tables=False)

        self.assertEqual(
            options.to_kwargs(),
            {"extract_images": False, "extract_tables": False},
        )

    def test_to_kwargs_keeps_password_and_page_range(self) -> None:
        options = ParseRuntimeOptions(password="secret", page_range=(2, 4))

        self.assertEqual(
            options.to_kwargs(),
            {"password": "secret", "page_range": (2, 4)},
        )


if __name__ == "__main__":
    unittest.main()
