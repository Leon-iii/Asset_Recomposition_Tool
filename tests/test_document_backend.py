from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from psd_decomposer.document_backend import (
    DocumentBackendError,
    DocumentFormat,
    is_aseprite_document,
    is_supported_document,
    load_document,
)


class DocumentBackendTests(unittest.TestCase):
    def test_psd_extension_routes_to_psd_document(self) -> None:
        with patch("psd_decomposer.psd_backend.PsdDocument", autospec=True) as document_class:
            document = load_document(Path("sample.psd"))

        document_class.assert_called_once_with(Path("sample.psd"))
        self.assertIs(document, document_class.return_value)

    def test_aseprite_extension_is_recognized_but_not_implemented_yet(self) -> None:
        with self.assertRaises(DocumentBackendError):
            load_document(Path("sample.aseprite"))

    def test_supported_document_extension_helpers(self) -> None:
        self.assertTrue(is_supported_document(Path("sample.psd")))
        self.assertTrue(is_supported_document(Path("sample.ase")))
        self.assertTrue(is_supported_document(Path("sample.aseprite")))
        self.assertFalse(is_supported_document(Path("sample.png")))

    def test_aseprite_extension_helper(self) -> None:
        self.assertTrue(is_aseprite_document(Path("sample.ase")))
        self.assertTrue(is_aseprite_document(Path("sample.aseprite")))
        self.assertFalse(is_aseprite_document(Path("sample.psd")))

    def test_document_format_values(self) -> None:
        self.assertEqual(DocumentFormat.PSD.value, "psd")
        self.assertEqual(DocumentFormat.ASEPRITE.value, "aseprite")


if __name__ == "__main__":
    unittest.main()
