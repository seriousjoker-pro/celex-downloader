from __future__ import annotations

import argparse
from pathlib import Path

from .downloader import DEFAULT_FORMATS, DocumentFormat, run_download


def main() -> int:
    parser = argparse.ArgumentParser(description="Download official English EUR-Lex representations by CELEX number.")
    parser.add_argument("source", type=Path, nargs="?", help="Folder to scan recursively for CELEX numbers")
    parser.add_argument("--celex-file", type=Path, help="Explicit text catalogue of CELEX identifiers")
    parser.add_argument("--output", type=Path, default=Path("downloaded_html"), help="Directory for HTML files and manifest.json")
    parser.add_argument("--force", action="store_true", help="Re-download files already present")
    parser.add_argument("--workers", type=int, default=8, help="Maximum concurrent requests (default: 8)")
    parser.add_argument("--formats", default=",".join(DEFAULT_FORMATS), help="Comma-separated formats: html,pdf,xml")
    arguments = parser.parse_args()
    if (arguments.source is None) == (arguments.celex_file is None):
        parser.error("provide exactly one of SOURCE or --celex-file")
    formats = tuple(part.strip().lower() for part in arguments.formats.split(",") if part.strip())
    if not formats or any(part not in DEFAULT_FORMATS for part in formats):
        parser.error("--formats must contain one or more of: html,pdf,xml")
    return run_download(arguments.source, arguments.output, celex_file=arguments.celex_file, formats=formats, force=arguments.force, workers=arguments.workers)


if __name__ == "__main__":
    raise SystemExit(main())
