from __future__ import annotations

import unittest

from hi_pdf_parser.config import PyMuPDFParserConfig
from hi_pdf_parser.parser_factory import build_parser_config, create_parser


class ParserFactoryTest(unittest.TestCase):
    def test_build_parser_config_matches_direct_defaults(self) -> None:
        self.assertEqual(
            build_parser_config().model_dump(),
            PyMuPDFParserConfig().model_dump(),
        )

    def test_build_parser_config_applies_only_explicit_overrides(self) -> None:
        config = build_parser_config(extract_images=False, max_pages=7)

        self.assertFalse(config.extract_images)
        self.assertTrue(config.extract_tables)
        self.assertEqual(config.max_pages, 7)
        self.assertTrue(config.skip_header_footer)

    def test_create_parser_uses_supplied_config(self) -> None:
        config = PyMuPDFParserConfig(extract_images=False)

        parser = create_parser(config)

        self.assertIs(parser.config, config)

    def test_create_parser_uses_shared_defaults(self) -> None:
        parser = create_parser()

        self.assertEqual(
            parser.config.model_dump(),
            PyMuPDFParserConfig().model_dump(),
        )


if __name__ == "__main__":
    unittest.main()
