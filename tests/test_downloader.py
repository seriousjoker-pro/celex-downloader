from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from celex_downloader.downloader import (
    DownloadError,
    build_html_url,
    discover_celex,
    download_one,
    output_filename,
)


class FakePage:
    def __init__(self, html: str) -> None:
        self.html = html
        self.urls: list[str] = []

    async def goto(self, url: str, **_: object) -> None:
        self.urls.append(url)

    async def content(self) -> str:
        return self.html


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

    def test_builds_english_html_url(self) -> None:
        self.assertEqual(
            build_html_url("32016R0399"),
            "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX%3A32016R0399",
        )

    def test_output_name_is_safe_for_consolidated_celex(self) -> None:
        self.assertEqual(
            output_filename("02009R0810-20240628"),
            "CELEX_02009R0810-20240628_EN.html",
        )


class DownloadTests(unittest.TestCase):
    def test_download_one_saves_browser_html(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            page = FakePage("<html><body>REGULATION (EU) 2016/399</body></html>")
            result = asyncio.run(download_one(page, "32016R0399", Path(directory)))

            saved = Path(directory) / "CELEX_32016R0399_EN.html"
            self.assertEqual(result.path, saved)
            self.assertTrue(saved.exists())
            self.assertIn("2016/399", saved.read_text(encoding="utf-8"))
            self.assertEqual(page.urls, [build_html_url("32016R0399")])

    def test_download_one_rejects_non_html_response(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            page = FakePage("Access denied")

            with self.assertRaises(DownloadError):
                asyncio.run(download_one(page, "32016R0399", Path(directory)))
