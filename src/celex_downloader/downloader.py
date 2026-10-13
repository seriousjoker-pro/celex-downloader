from __future__ import annotations

import asyncio
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from urllib.parse import quote


CELEX_PATTERN = re.compile(
    r"(?<![A-Z0-9])(?:0\d{4}[A-Z]\d{4}-\d{8}|[0-9]\d{4}[A-Z]\d{4}(?:R\(\d{2}\))?)(?![A-Z0-9])"
)
TEXT_FILE_LIMIT_BYTES = 20 * 1024 * 1024


class BrowserPage(Protocol):
    async def goto(self, url: str, **kwargs: object) -> object: ...

    async def content(self) -> str: ...


class DownloadError(RuntimeError):
    """EUR-Lex did not deliver a usable HTML document."""


@dataclass(frozen=True)
class DownloadResult:
    celex: str
    url: str
    path: Path
    bytes_written: int
    downloaded_at: str


def build_html_url(celex: str) -> str:
    return "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=" + quote(
        f"CELEX:{celex}", safe=""
    )


def output_filename(celex: str) -> str:
    return f"CELEX_{celex}_EN.html"


def discover_celex(source: Path) -> list[str]:
    """Find CELEX numbers in path names and readable text files beneath *source*."""
    found: set[str] = set()
    for path in source.rglob("*"):
        found.update(CELEX_PATTERN.findall(path.name.upper()))
        if not path.is_file() or path.stat().st_size > TEXT_FILE_LIMIT_BYTES:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        found.update(CELEX_PATTERN.findall(text.upper()))
    return sorted(found)


async def download_one(page: BrowserPage, celex: str, output_dir: Path) -> DownloadResult:
    """Navigate to the EUR-Lex HTML view and persist the unmodified document."""
    url = build_html_url(celex)
    await page.goto(url, wait_until="networkidle", timeout=90_000)
    html = await page.content()
    if "<html" not in html.lower():
        raise DownloadError(f"EUR-Lex did not return HTML for {celex}")

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / output_filename(celex)
    path.write_text(html, encoding="utf-8")
    return DownloadResult(
        celex=celex,
        url=url,
        path=path,
        bytes_written=path.stat().st_size,
        downloaded_at=datetime.now(UTC).isoformat(),
    )


async def download_all(
    celex_numbers: list[str], output_dir: Path, *, force: bool = False, headless: bool = False
) -> list[dict[str, object]]:
    """Download every CELEX with Chrome, recording each outcome in a manifest."""
    try:
        from playwright.async_api import async_playwright
    except ImportError as error:
        raise RuntimeError(
            "Playwright is required. Run: python -m pip install -e . and playwright install chrome"
        ) from error

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    records: list[dict[str, object]] = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel="chrome", headless=headless)
        page = await browser.new_page()
        try:
            for celex in celex_numbers:
                destination = output_dir / output_filename(celex)
                if destination.exists() and not force:
                    records.append({"celex": celex, "status": "skipped", "path": str(destination)})
                    continue
                try:
                    result = await download_one(page, celex, output_dir)
                    records.append({"status": "downloaded", **asdict(result), "path": str(result.path)})
                except Exception as error:  # record one failure and continue with the corpus
                    records.append({"celex": celex, "status": "failed", "error": str(error)})
        finally:
            await browser.close()

    manifest_path.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    return records


def run_download(source: Path, output_dir: Path, *, force: bool, headless: bool) -> int:
    celex_numbers = discover_celex(source)
    if not celex_numbers:
        print(f"No CELEX numbers found under {source}")
        return 2
    records = asyncio.run(download_all(celex_numbers, output_dir, force=force, headless=headless))
    failures = sum(record["status"] == "failed" for record in records)
    print(f"Processed {len(records)} CELEX numbers; {failures} failed. Manifest: {output_dir / 'manifest.json'}")
    return 1 if failures else 0
