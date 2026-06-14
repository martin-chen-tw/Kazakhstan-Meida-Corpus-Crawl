# kz_media crawler

Crawler pipeline for Kazakhstani media sources. The project lists article URLs, downloads articles, and writes each source/language pair directly to a final SQLite file.

This is a breaking public schema release. New outputs include `rowdata`, the full raw HTML fetched for each article page.

## Setup

Use Python 3.11+.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirement.txt
```

Configuration lives in `config.yaml`. The default output root is `./output`; every command below can override it with `--db-root`.

## Commands

Update existing output by inserting new rows and preserving existing rows:

```bash
python3 script/update_db.py --newspaper tengri --lang ru --db-root /path/to/data
```

Rebuild one source/lang from scratch:

```bash
python3 script/rebuild.py --newspaper tengri --lang ru --db-root /path/to/data
```

Limit a run for smoke validation:

```bash
python3 script/update_db.py --newspaper tengri --lang ru --limit 100 --db-root /home/martin/Desktop/kz_media/data_v2
```

Run every configured source/lang by scripting over `script/list_sources.py`; do not rely on `--all` when you need per-pair evidence.

Check generated SQLite files:

```bash
python3 script/error_check.py /home/martin/Desktop/kz_media/data_v2 --output /home/martin/Desktop/kz_media/data_v2/error_report.json
```

`script/error_check.py` exits with:

- `0`: scan completed and no data errors were found.
- `1`: scan completed and data errors were reported.
- `2`: CLI, config, or root-open failure prevented a valid scan.

## Data Layout

For a root such as `/home/martin/Desktop/kz_media/data_v2`, output is written as:

```text
data_v2/
  tengri_ru.sqlite
```

`update_db.py` and `rebuild.py` read and write the matching final `<newspaper>_<lang>.sqlite` file in the selected root. The configured `save_path` is not used for final SQLite placement.

## Row Schema

Every newly written row uses this canonical column order:

```text
newspaper, url, title, date, time, author, body, rowdata
```

Field meanings:

- `newspaper`: source identifier, for example `tengri`.
- `url`: article URL.
- `title`: parsed article title.
- `date`: article date in `YYYY-MM-DD` when available.
- `time`: article time when available.
- `author`: article author when available.
- `body`: cleaned article text.
- `rowdata`: full raw HTML fetched for the article page.

Legacy non-SQLite exports are no longer supported as an output or validation format. Provenance-complete exports require rebuilding or updating rows so the raw HTML is fetched and stored in final SQLite.

## Supported Sources

| Source | Languages |
| --- | --- |
| `akorda_addresses` | `ru`, `en`, `kz` |
| `akorda_events` | `ru`, `en`, `kz` |
| `akorda_legal_acts` | `ru`, `en`, `kz` |
| `akorda_speeches` | `ru`, `en`, `kz` |
| `anatili` | `kz`, `qazaq` |
| `egemen` | `kz`, `qazaq`, `ru`, `en` |
| `kazpravda` | `ru` |
| `khabar` | `ru`, `kz` |
| `kursiv` | `ru`, `kz`, `en` |
| `nur` | `ru`, `kz` |
| `orda` | `ru`, `en`, `kz` |
| `sputnik` | `ru`, `kz` |
| `tengri` | `ru`, `en`, `kz` |
| `vlast` | `ru`, `kz`, `en` |
| `zakon` | `ru`, `kz` |

## Validation Workflow

Run unit tests:

```bash
python3 -m unittest discover -s tests
```

Run each configured source/lang with `--limit 100` into an isolated validation root:

```bash
python3 script/update_db.py --newspaper <source> --lang <lang> --limit 100 --db-root /home/martin/Desktop/kz_media/data_v2
```

Then scan the generated files:

```bash
python3 script/error_check.py /home/martin/Desktop/kz_media/data_v2 --output /home/martin/Desktop/kz_media/data_v2/error_report.json
```

For release validation, keep a manifest at:

```text
.omx/reports/ralplan-20260530-1-public-release/validation-manifest.json
```

The manifest should record the source, language, command, status, timestamps, output paths, row count, and `rowdata` evidence such as length/hash or a short escaped prefix.

## Raw HTML Tradeoff

This release intentionally stores full raw HTML in `rowdata` inside final SQLite files.

A future release may move raw HTML to sidecar files or compressed archives with stable row references. That alternative is not used here because the current public contract requires provenance in the final row format.

## Development Notes

- Reusable behavior belongs under `Basement/`.
- Source-specific crawler logic belongs under `Crawling/<source>/`.
- `script/` should stay thin; public command wrappers should delegate to `Basement`.
