from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from celex_downloader.downloader import (
    DownloadError,
    build_document_url,
    discover_celex,
    download_one,
    output_filename,
    read_celex_file,
)


class FakePdfStream:
    def read(self) -> bytes:
        return b"%PDF-1.7 fake pdf"


class FakeHtmlStream:
    def read(self) -> bytes:
        return b"<html><body>REGULATION (EU) 2016/399</body></html>"


class FakeXmlStream:
    def read(self) -> bytes:
        return b"<?xml version='1.0'?><NOTICE/>"


class CelexDiscoveryTests(unittest.TestCase):
    def test_finds_unique_celex_in_file_names_and_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "32016R0399.pdf").write_bytes(b"not parsed")
            nested = root / "nested"
            nested.mkdir()
            (nested / "notes.md").write_text(
                "Acts: 32016R0399, 02009R0810-20240628, and 32017R2226.",
                encoding="utf-8",
            )

            self.assertEqual(
                discover_celex(root),
                ["02009R0810-20240628", "32016R0399", "32017R2226"],
            )

    def test_finds_two_letter_descriptors_and_excludes_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "CELEX_52022DC0303_EN_TXT.pdf").write_bytes(b"pdf")
            (root / "CELEX_52020IP0378_EN_TXT.pdf").write_bytes(b"pdf")
            output = root / "downloaded_html"
            output.mkdir()
            (output / "CELEX_32006D0896_EN.html").write_text("<html>reference</html>")

            self.assertEqual(
                discover_celex(root, exclude=output),
                ["52020IP0378", "52022DC0303"],
            )

    def test_builds_english_document_urls(self) -> None:
        self.assertEqual(
            build_document_url("32016R0399", "html"),
            "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX%3A32016R0399",
        )
        self.assertEqual(
            build_document_url("32016R0399", "pdf"),
            "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX%3A32016R0399",
        )
        self.assertEqual(
            build_document_url("32016R0399", "xml"),
            "https://eur-lex.europa.eu/legal-content/EN/TXT/XML/?uri=CELEX%3A32016R0399",
        )

    def test_reads_explicit_catalogue_without_expanding_references(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            catalogue = Path(directory) / "celex.txt"
            catalogue.write_text("32016R0399\n32016R0399\nReference: 52022DC0303", encoding="utf-8")
            self.assertEqual(read_celex_file(catalogue), ["32016R0399", "52022DC0303"])

    def test_output_name_is_safe_for_consolidated_celex(self) -> None:
        self.assertEqual(
            output_filename("02009R0810-20240628", "pdf"),
            "CELEX_02009R0810-20240628_EN.pdf",
        )


class DownloadTests(unittest.TestCase):
    def test_download_one_saves_cellar_html(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch("celex_downloader.downloader.urlopen", return_value=FakeHtmlStream()):
                result = asyncio.run(download_one("32016R0399", "html", Path(directory)))

            saved = Path(directory) / "CELEX_32016R0399_EN.html"
            self.assertEqual(result.path, saved)
            self.assertTrue(saved.exists())
            self.assertIn("2016/399", saved.read_text(encoding="utf-8"))

    def test_download_one_saves_pdf_response_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch("celex_downloader.downloader.urlopen", return_value=FakePdfStream()):
                result = asyncio.run(download_one("32016R0399", "pdf", Path(directory)))

            saved = Path(directory) / "CELEX_32016R0399_EN.pdf"
            self.assertEqual(result.path, saved)
            self.assertEqual(saved.read_bytes(), b"%PDF-1.7 fake pdf")

    def test_download_one_rejects_non_html_response(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch("celex_downloader.downloader.urlopen", return_value=FakePdfStream()):
                with self.assertRaises(DownloadError):
                    asyncio.run(download_one("32016R0399", "html", Path(directory)))

    def test_download_one_saves_cellar_xml(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch("celex_downloader.downloader.urlopen", return_value=FakeXmlStream()):
                result = asyncio.run(download_one("32016R0399", "xml", Path(directory)))

            saved = Path(directory) / "CELEX_32016R0399_EN.xml"
            self.assertEqual(result.path, saved)
            self.assertEqual(saved.read_bytes(), b"<?xml version='1.0'?><NOTICE/>")
