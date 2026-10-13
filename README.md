# CELEX Downloader

`celex-downloader` finds CELEX identifiers in a local folder and saves the official English HTML, PDF, and XML notice published by EUR-Lex. It preserves each retrieved source as received: it does not convert, summarize, or alter legal text.

## Specification

### Goal

Provide a repeatable local command for collecting the English HTML source documents corresponding to every CELEX identifier found recursively in a corpus folder.

### Inputs

- One required source folder, scanned recursively.
- CELEX identifiers found in readable UTF-8 text and in file or directory names.
- Both ordinary identifiers such as `32016R0399` and consolidated-version identifiers such as `02009R0810-20240628`.

### Outputs

- Up to three source files per successfully retrieved identifier: `CELEX_<identifier>_EN.html`, `.pdf`, and `.xml`.
- `manifest.json`, recording every downloaded, skipped, and failed identifier by format.
- Existing HTML files are skipped by default, so interrupted runs can safely resume. Use `--force` to replace them.

### Retrieval method and constraints

EUR-Lex serves the requested document from its official English HTML endpoint:

`https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:<identifier>`

Direct HTTP clients are challenged by EUR-Lex’s AWS WAF (HTTP `202` in the observed test). The downloader therefore controls a normal installed Chrome browser through Playwright. It runs Chrome visibly by default so the site can execute its ordinary JavaScript challenge. The downloader does not solve CAPTCHAs, bypass access controls, or submit data to EUR-Lex.

Some CELEX entries do not have an HTML edition. The downloader records them as failures and continues with the remaining identifiers.

### Non-goals

- No Markdown conversion, PDF extraction, legal interpretation, or content normalization.
- No automatic monitoring for new EUR-Lex editions.
- No upload, publishing, or transmission of the downloaded corpus.

## Install

Use Python 3.11 or newer. From this repository:

```powershell
py -3 -m pip install -e .
py -3 -m playwright install chrome
```

## Use

```powershell
celex-download "C:\Users\mapaleari\Downloads\CELEX" --output .\downloaded_sources
```

Or, without installing the command entry point:

```powershell
$env:PYTHONPATH = "src"
py -3 -m celex_downloader.cli "C:\Users\mapaleari\Downloads\da benny" --output .\downloaded_html
```

Use `--formats html,pdf,xml` to select formats; this is also the default. Keep the Chrome window open while a run is active. `--headless` is available for controlled environments, but it is not recommended because EUR-Lex may challenge headless browsers.

## Test

```powershell
$env:PYTHONPATH = "src"
py -3 -m unittest discover -s tests -v
```

The unit suite does not contact EUR-Lex. A real-browser test was performed against `32016R0399`: EUR-Lex delivered English `text/html` containing Regulation (EU) 2016/399.
