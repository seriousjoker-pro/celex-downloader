from __future__ import annotations

import argparse
from pathlib import Path

from .downloader import DEFAULT_FORMATS, DocumentFormat, run_download


def main() -> int:
    parser = argparse.ArgumentParser(description="Download English EUR-Lex HTML documents found by CELEX number.")
    parser.add_argument("source", type=Path, help="Folder to scan recursively for CELEX numbers")
    parser.add_argument("--output", type=Path, default=Path("downloaded_html"), help="Directory for HTML files and manifest.json")
    parser.add_argument("--force", action="store_true", help="Re-download files already present")
    parser.add_argument("--formats", default=",".join(DEFAULT_FORMATS), help="Comma-separated formats: html,pdf,xml")
    parser.add_argument("--headless", action="store_true", help="Run Chrome headless (not recommended: EUR-Lex WAF may reject it)")
    arguments = parser.parse_args()
    formats = tuple(part.strip().lower() for part in arguments.formats.split(",") if part.strip())
    if not formats or any(part not in DEFAULT_FORMATS for part in formats):
        parser.error("--formats must contain one or more of: html,pdf,xml")
    return run_download(arguments.source, arguments.output, formats=formats, force=arguments.force, headless=arguments.headless)


if __name__ == "__main__":
    raise SystemExit(main())
