from __future__ import annotations

import asyncio
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import quote
from urllib.request import Request, urlopen


CELEX_PATTERN = re.compile(
    r"(?<![A-Z0-9])(?:0\d{4}[A-Z]{1,2}\d{4}-\d{8}|[0-9]\d{4}[A-Z]{1,2}\d{4}(?:R\(\d{2}\))?)(?![A-Z0-9])"
)
TEXT_FILE_LIMIT_BYTES = 20 * 1024 * 1024
CELLAR_TIMEOUT_SECONDS = 30
DocumentFormat = Literal["html", "pdf", "xml"]
DEFAULT_FORMATS: tuple[DocumentFormat, ...] = ("html", "pdf", "xml")


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


def read_celex_file(path: Path) -> list[str]:
    """Read an explicit CELEX catalogue, ignoring duplicate identifiers."""
    return sorted(set(CELEX_PATTERN.findall(path.read_text(encoding="utf-8").upper())))


async def _read_cellar(celex: str, accept: str) -> tuple[str, bytes]:
    url = build_cellar_pdf_url(celex)
    request = Request(url, headers={"Accept": accept, "Accept-Language": "eng"})
    content = await asyncio.to_thread(lambda: urlopen(request, timeout=CELLAR_TIMEOUT_SECONDS).read())
    return url, content


async def download_one(celex: str, document_format: DocumentFormat, output_dir: Path) -> DownloadResult:
    """Persist an official English representation of one CELEX document."""
    url = build_document_url(celex, document_format)
    if document_format in {"html", "pdf", "xml"}:
        accept = {
            "html": "application/xhtml+xml",
            "pdf": "application/pdf",
            "xml": "application/xml;notice=tree",
        }[document_format]
        url, content = await _read_cellar(celex, accept)
        if document_format == "pdf" and not content.startswith(b"%PDF-"):
            raise DownloadError(f"Cellar did not return a PDF for {celex}")
        if document_format == "html" and b"<html" not in content.lower():
            raise DownloadError(f"Cellar did not return XHTML for {celex}")
        if document_format == "xml" and not content.lstrip().startswith(b"<"):
            raise DownloadError(f"Cellar did not return XML for {celex}")
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / output_filename(celex, document_format)
        path.write_bytes(content)
        return DownloadResult(celex, url, path, path.stat().st_size, datetime.now(UTC).isoformat())
    raise AssertionError(f"Unsupported document format: {document_format}")


async def download_all(
    celex_numbers: list[str], output_dir: Path, *, formats: tuple[DocumentFormat, ...] = DEFAULT_FORMATS,
    force: bool = False, workers: int = 8
) -> list[dict[str, object]]:
    """Download every CELEX, recording each outcome in a manifest."""
    if workers < 1:
        raise ValueError("workers must be at least 1")
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    semaphore = asyncio.Semaphore(workers)

    async def download_record(celex: str, document_format: DocumentFormat) -> dict[str, object]:
        destination = output_dir / output_filename(celex, document_format)
        if destination.exists() and not force:
            return {"celex": celex, "format": document_format, "status": "skipped", "path": str(destination)}
        async with semaphore:
            try:
                result = await download_one(celex, document_format, output_dir)
                return {"format": document_format, "status": "downloaded", **asdict(result), "path": str(result.path)}
            except Exception as error:  # record one failure and continue with the corpus
                return {"celex": celex, "format": document_format, "status": "failed", "error": str(error)}

    records = list(await asyncio.gather(*(
        download_record(celex, document_format)
        for celex in celex_numbers
        for document_format in formats
    )))

    manifest_path.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    return records


def run_download(source: Path | None, output_dir: Path, *, celex_file: Path | None = None,
                 formats: tuple[DocumentFormat, ...] = DEFAULT_FORMATS, force: bool,
                 workers: int = 8) -> int:
    if celex_file is not None:
        celex_numbers = read_celex_file(celex_file)
    elif source is not None:
        celex_numbers = discover_celex(source, exclude=output_dir)
    else:
        raise ValueError("source or celex_file is required")
    if not celex_numbers:
        print(f"No CELEX numbers found under {source}")
        return 2
    records = asyncio.run(download_all(celex_numbers, output_dir, formats=formats, force=force, workers=workers))
    failures = sum(record["status"] == "failed" for record in records)
    print(f"Processed {len(records)} CELEX numbers; {failures} failed. Manifest: {output_dir / 'manifest.json'}")
    return 1 if failures else 0
