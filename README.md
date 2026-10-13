# CELEX Downloader

`celex-downloader` finds CELEX identifiers in a local folder and saves the official English HTML, PDF, and XML notice published by EUR-Lex. It preserves each retrieved source as received: it does not convert, summarize, or alter legal text.

## Specification

### Goal

Provide a repeatable local command for collecting English HTML/XHTML, PDF, and XML representations corresponding to CELEX identifiers.

### Inputs

- One required source folder, scanned recursively.
- CELEX identifiers found in readable UTF-8 text and in file or directory names.
- Alternatively, an explicit CELEX catalogue passed with `--celex-file`. This prevents downloaded files or cross-references from changing the selected corpus.
- Both ordinary identifiers such as `32016R0399` and consolidated-version identifiers such as `02009R0810-20240628`.

### Outputs

- Up to three source files per successfully retrieved identifier: `CELEX_<identifier>_EN.html`, `.pdf`, and `.xml`.
- `manifest.json`, recording every downloaded, skipped, and failed identifier by format.
- Existing files are skipped by default, so interrupted runs can safely resume. Use `--force` to replace them.

### Retrieval method and constraints

HTML/XHTML and PDF are obtained directly from the Publications Office's official Cellar representation of the CELEX resource, with an English content negotiation header. This avoids the AWS WAF challenge applied to automated requests to the EUR-Lex display endpoints.

`https://publications.europa.eu/resource/celex/<identifier>?language=eng`

XML notices are obtained from Cellar's official `application/xml;notice=tree` representation. The downloader uses ordinary HTTP content negotiation only; it does not solve CAPTCHAs, bypass access controls, or submit data to EUR-Lex.

Some CELEX entries do not have an HTML edition. The downloader records them as failures and continues with the remaining identifiers.

### Non-goals

- No Markdown conversion, PDF extraction, legal interpretation, or content normalization.
- No automatic monitoring for new EUR-Lex editions.
- No upload, publishing, or transmission of the downloaded corpus.

## Install

Use Python 3.11 or newer. From this repository:

```powershell
py -3 -m pip install -e .
```

## Use

```powershell
celex-download "C:\Users\mapaleari\Downloads\CELEX" --output .\downloaded_sources
```

For a stable selection, use the included ORION catalogue:

```powershell
celex-download --celex-file .\catalogues\orion-celex.txt --output "C:\Users\mapaleari\Downloads\CELEX\official_sources"
```

Or, without installing the command entry point:

```powershell
$env:PYTHONPATH = "src"
py -3 -m celex_downloader.cli "C:\Users\mapaleari\Downloads\da benny" --output .\downloaded_html
```

Use `--formats html,pdf,xml` to select formats; this is also the default. No browser is required. `--workers 8` is the default concurrency limit; lower it if Cellar is under unusual load.

## Test

```powershell
$env:PYTHONPATH = "src"
py -3 -m unittest discover -s tests -v
```

The unit suite does not contact EUR-Lex. A real-browser test was performed against `32016R0399`: EUR-Lex delivered English `text/html` containing Regulation (EU) 2016/399.
