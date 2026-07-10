# kz_media crawler

Crawler pipeline for Kazakhstani media sources. The project lists article URLs, downloads articles with an async runner, and writes one SQL output file from the template at `~/Desktop/kz_media.sql`.

This is a breaking public schema release. New outputs include `rowdata`, the full raw HTML fetched for each article page.

## Setup

Use Python 3.11+.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirement.txt
```

Runtime output is controlled by `.env`:

```dotenv
KZ_MEDIA_OUTPUT_MODE=sql
KZ_MEDIA_OUTPUT_PATH=./new_data_v2.py
KZ_MEDIA_SQL_TEMPLATE=~/Desktop/kz_media.sql
KZ_MEDIA_PSQL_USERNAME=
KZ_MEDIA_PSQL_PASSWORD=
KZ_MEDIA_PSQL_HOST=localhost
KZ_MEDIA_PSQL_PORT=5432
KZ_MEDIA_PSQL_DB_NAME=
KZ_MEDIA_PSQL_SSLMODE=prefer
KZ_MEDIA_PSQL_SCHEMA=
KZ_MEDIA_PLATFORMS_TABLE=platforms
KZ_MEDIA_ARTICLES_TABLE=articles
```

Modes:

- `sql`: generate one SQL file at `KZ_MEDIA_OUTPUT_PATH`.
- `psql`: generate the same SQL file, then import it with `psql -h "$KZ_MEDIA_PSQL_HOST" -p "$KZ_MEDIA_PSQL_PORT" -U "$KZ_MEDIA_PSQL_USERNAME" -d "$KZ_MEDIA_PSQL_DB_NAME" -f "$KZ_MEDIA_OUTPUT_PATH"`.
- `sqlite`: legacy compatibility mode for the older per-source SQLite output.

## Commands

Update existing output by inserting new rows and preserving existing rows:

```bash
python3 script/update_db.py --newspaper tengri --lang ru --db-root /path/to/data
```

Rebuild one source/lang from scratch:

```bash
python3 script/rebuild.py --newspaper tengri --lang ru --db-root /path/to/data
```

With the default `.env`, both commands write `./new_data_v2.py`. `--db-root` only affects legacy `sqlite` mode.

Limit a run for smoke validation:

```bash
python3 script/update_db.py --newspaper tengri --lang ru --limit 100 --db-root /home/martin/Desktop/kz_media/data_v2
```

Run every configured source/lang by scripting over `script/list_sources.py`; do not rely on `--all` when you need per-pair evidence.

Check generated SQLite files in legacy mode:

```bash
python3 script/error_check.py /home/martin/Desktop/kz_media/data_v2 --output /home/martin/Desktop/kz_media/data_v2/error_report.json
```

`script/error_check.py` exits with:

- `0`: scan completed and no data errors were found.
- `1`: scan completed and data errors were reported.
- `2`: CLI, config, or root-open failure prevented a valid scan.

## Data Layout

The default output is one SQL file:

```text
new_data_v2.py
```

The file starts with the template from `KZ_MEDIA_SQL_TEMPLATE`, then appends `INSERT` statements for `KZ_MEDIA_PLATFORMS_TABLE` and `KZ_MEDIA_ARTICLES_TABLE`. If `KZ_MEDIA_PSQL_SCHEMA` is set, generated inserts use `"schema"."table"`.

In legacy `sqlite` mode, output is written as `<db-root>/<newspaper>_<lang>.sqlite`.

## Row Schema

Crawler rows use this canonical internal order:

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

The SQL template stores article text in `article_body`. `rowdata` remains available internally and in legacy SQLite output, but the current `~/Desktop/kz_media.sql` template has no `rowdata` column.

Akorda crawler modules are still selected by their folder names such as `akorda_addresses`, but SQL output stores them as `newspaper='akorda'` and places the suffix (`addresses`, `events`, `legal_acts`, `speeches`) in `category`.

## Supported Sources

| Source | Languages |
| --- | --- |
| `akorda_addresses` | `ru`, `en`, `kz` |
| `akorda_events` | `ru`, `en`, `kz` |
| `akorda_legal_acts` | `ru`, `en`, `kz` |
| `akorda_speeches` | `ru`, `en`, `kz` |
| `anatili` | `kz`, `qazaq` |
| `egemen` | `kz`, `qazaq`, `ru`, `en` |
| `kazpravda` | `ru`, `en`, `qaz` |
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

Run one configured source/lang with `--limit 100` into the `.env` output file:

```bash
python3 script/update_db.py --newspaper <source> --lang <lang> --limit 100
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
