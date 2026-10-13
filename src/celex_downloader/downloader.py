from __future__ import annotations

import asyncio
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol
from urllib.parse import quote
from urllib.request import Request, urlopen


CELEX_PATTERN = re.compile(
    r"(?<![A-Z0-9])(?:0\d{4}[A-Z]{1,2}\d{4}-\d{8}|[0-9]\d{4}[A-Z]{1,2}\d{4}(?:R\(\d{2}\))?)(?![A-Z0-9])"
)
TEXT_FILE_LIMIT_BYTES = 20 * 1024 * 1024
DocumentFormat = Literal["html", "pdf", "xml"]
DEFAULT_FORMATS: tuple[DocumentFormat, ...] = ("html", "pdf", "xml")


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


def build_document_url(celex: str, document_format: DocumentFormat) -> str:
    endpoint = {"html": "HTML", "pdf": "PDF", "xml": "XML"}[document_format]
    return f"https://eur-lex.europa.eu/legal-content/EN/TXT/{endpoint}/?uri=" + quote(
        f"CELEX:{celex}", safe=""
    )


def build_cellar_pdf_url(celex: str) -> str:
    return f"https://publications.europa.eu/resource/celex/{quote(celex, safe='')}?language=eng"


def output_filename(celex: str, document_format: DocumentFormat) -> str:
    return f"CELEX_{celex}_EN.{document_format}"


def discover_celex(source: Path, *, exclude: Path | None = None) -> list[str]:
    """Find CELEX numbers in path names and readable text files beneath *source*."""
    found: set[str] = set()
    excluded = exclude.resolve() if exclude is not None else None
    for path in source.rglob("*"):
        if excluded is not None and path.resolve().is_relative_to(excluded):
            continue
        found.update(CELEX_PATTERN.findall(path.name.upper()))
        if not path.is_file() or path.stat().st_size > TEXT_FILE_LIMIT_BYTES:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        found.update(CELEX_PATTERN.findall(text.upper()))
    return sorted(found)


async def download_one(
    page: BrowserPage, celex: str, document_format: DocumentFormat, output_dir: Path
) -> DownloadResult:
    """Navigate to the EUR-Lex HTML view and persist the unmodified document."""
    url = build_document_url(celex, document_format)
    if document_format == "pdf":
        url = build_cellar_pdf_url(celex)
        request = Request(url, headers={"Accept": "application/pdf", "Accept-Language": "eng"})
        content = await asyncio.to_thread(lambda: urlopen(request, timeout=90).read())
        if not content.startswith(b"%PDF-"):
            raise DownloadError(f"Cellar did not return a PDF for {celex}")
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / output_filename(celex, document_format)
        path.write_bytes(content)
        return DownloadResult(celex, url, path, path.stat().st_size, datetime.now(UTC).isoformat())
    wait_until = "commit" if document_format == "pdf" else "networkidle"
    response = await page.goto(url, wait_until=wait_until, timeout=90_000)
    if response is None:
        raise DownloadError(f"EUR-Lex did not return a response for {celex} ({document_format})")
    if document_format == "html":
        content: str | bytes = await page.content()
        if "<html" not in content.lower():
            raise DownloadError(f"EUR-Lex did not return HTML for {celex}")
    elif document_format == "pdf":
        content = await response.body()
        if not content.startswith(b"%PDF-"):
            raise DownloadError(f"EUR-Lex did not return a PDF for {celex}")
    else:
        content = await response.text()
        if not content.lstrip().startswith("<"):
            raise DownloadError(f"EUR-Lex did not return XML for {celex}")

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / output_filename(celex, document_format)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return DownloadResult(
        celex=celex,
        url=url,
        path=path,
        bytes_written=path.stat().st_size,
        downloaded_at=datetime.now(UTC).isoformat(),
    )


async def download_all(
    celex_numbers: list[str], output_dir: Path, *, formats: tuple[DocumentFormat, ...] = DEFAULT_FORMATS,
    force: bool = False, headless: bool = False
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
                for document_format in formats:
                    destination = output_dir / output_filename(celex, document_format)
                    if destination.exists() and not force:
                        records.append({"celex": celex, "format": document_format, "status": "skipped", "path": str(destination)})
                        continue
                    try:
                        result = await download_one(page, celex, document_format, output_dir)
                        records.append({"format": document_format, "status": "downloaded", **asdict(result), "path": str(result.path)})
                    except Exception as error:  # record one failure and continue with the corpus
                        records.append({"celex": celex, "format": document_format, "status": "failed", "error": str(error)})
        finally:
            await browser.close()

    manifest_path.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    return records


def run_download(source: Path, output_dir: Path, *, formats: tuple[DocumentFormat, ...] = DEFAULT_FORMATS,
                 force: bool, headless: bool) -> int:
    celex_numbers = discover_celex(source, exclude=output_dir)
    if not celex_numbers:
        print(f"No CELEX numbers found under {source}")
        return 2
    records = asyncio.run(download_all(celex_numbers, output_dir, formats=formats, force=force, headless=headless))
    failures = sum(record["status"] == "failed" for record in records)
    print(f"Processed {len(records)} CELEX numbers; {failures} failed. Manifest: {output_dir / 'manifest.json'}")
    return 1 if failures else 0
