from __future__ import annotations
import argparse, importlib, os
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from datetime import date
from multiprocessing import Process, Queue
from pathlib import Path
from queue import Empty
from .config import db_root_path, get_root_config, get_source_config, list_newspapers, load_source_configs
from .excel_db import existing_files, merge_rows, read_rows, rewrite_rows
from .models import ArticleMeta
from .sql_tmp_db import append_tmp_rows, ensure_tmp_db, read_tmp_rows, read_tmp_urls

def _parse_date(s: str | None) -> date | None:
    return date.fromisoformat(s) if s else None

def _site_module(newspaper: str, mod: str):
    return importlib.import_module(f'Crawling.{newspaper}.{mod}')

def _download_row(newspaper: str, meta: ArticleMeta) -> dict[str, str]:
    article = _site_module(newspaper, 'crawling_article')
    try:
        result = article.crawling_article(meta.url, with_metadata=True)
    except TypeError:
        result = article.crawling_article(meta.url)
    if isinstance(result, dict):
        if result.get('author') and not meta.author:
            meta.author = result['author']
        if result.get('title') and not meta.title:
            meta.title = result['title']
        if result.get('date') and not meta.date:
            meta.date = result['date']
        if result.get('time') and not meta.time:
            meta.time = result['time']
        return meta.row(str(result.get('body', '')))
    return meta.row(str(result))

def _download_to_queue(newspaper: str, meta: ArticleMeta, pending_queue) -> dict[str, str]:
    row = _download_row(newspaper, meta)
    pending_queue.put(row)
    return row

def _write_pending_rows(cfg, rebuild: bool, db_root: Path | None, flush_rows: int, pending_queue, result_queue) -> None:
    tmp_path = ensure_tmp_db(cfg, db_root)
    paths = [p for _, p in existing_files(cfg, db_root)]
    buffer = []
    consumed = 0
    flushes = 0
    while True:
        row = pending_queue.get()
        if row is None:
            break
        buffer.append(row)
        consumed += 1
        if len(buffer) >= flush_rows:
            append_tmp_rows(tmp_path, buffer)
            buffer = []
            flushes += 1
    if buffer:
        append_tmp_rows(tmp_path, buffer)
        flushes += 1
    new_rows = read_tmp_rows(tmp_path)
    old_rows = [] if rebuild else read_rows(cfg, db_root)
    rows = merge_rows(old_rows, new_rows, rebuild=rebuild)
    if new_rows or rebuild or not paths:
        paths = rewrite_rows(cfg, rows, db_root)
    result_queue.put({
        'consumed': consumed,
        'rows': len(rows),
        'flushes': flushes,
        'tmp_db': str(tmp_path),
        'written': [str(p) for p in paths],
    })

def run_source(newspaper: str, lang: str, mode: str, start_date: date | None, end_date: date | None,
               limit: int | None, dry_run: bool, threads: int, root_override: str | None) -> dict[str, object]:
    cfg = get_source_config(newspaper, lang)
    table = _site_module(newspaper, 'crawling_table')
    root = db_root_path(root_override) if root_override else None
    tmp_path = None
    if not dry_run and mode != 'rebuild':
        tmp_path = ensure_tmp_db(cfg, root)
    old_limit = os.environ.get("NCCU_CRAWL_LIMIT")
    old_staged_db = os.environ.get("NCCU_STAGED_URL_DB")
    if limit: os.environ["NCCU_CRAWL_LIMIT"] = str(limit)
    if tmp_path is not None:
        os.environ["NCCU_STAGED_URL_DB"] = str(tmp_path)
    try:
        metas = [ArticleMeta.from_any(x, cfg.newspaper, lang) for x in table.crawling_table(lang, start_date, end_date)]
    finally:
        if old_limit is None: os.environ.pop("NCCU_CRAWL_LIMIT", None)
        else: os.environ["NCCU_CRAWL_LIMIT"] = old_limit
        if old_staged_db is None: os.environ.pop("NCCU_STAGED_URL_DB", None)
        else: os.environ["NCCU_STAGED_URL_DB"] = old_staged_db
    if limit: metas = metas[:limit]
    if dry_run:
        return {'newspaper': newspaper, 'lang': lang, 'listed': len(metas), 'written': [], 'dry_run': True}
    flush_rows = max(1, int(get_root_config('extracting', 'pending_flush_rows', default=50) or 50))
    tmp_path = tmp_path or ensure_tmp_db(cfg, root)
    staged_urls = read_tmp_urls(tmp_path)
    if staged_urls:
        metas = [meta for meta in metas if not meta.url or meta.url not in staged_urls]
    pending_queue = Queue()
    result_queue = Queue()
    writer = Process(target=_write_pending_rows, args=(cfg, mode == 'rebuild', root, flush_rows, pending_queue, result_queue))
    writer.start()
    rows = 0
    with ThreadPoolExecutor(max_workers=threads) as ex:
        futs = [ex.submit(_download_to_queue, newspaper, m, pending_queue) for m in metas]
        for fut in as_completed(futs):
            try:
                fut.result()
                rows += 1
            except Exception as e: print(f'[WARN] article failed: {e}')
    pending_queue.put(None)
    writer.join()
    if writer.exitcode:
        raise RuntimeError(f'writer process failed: exitcode={writer.exitcode}')
    try:
        result = result_queue.get(timeout=5)
    except Empty:
        result = {'written': [str(p) for _, p in existing_files(cfg, root)]}
    return {'newspaper': newspaper, 'lang': lang, 'listed': len(metas), 'rows': rows,
            'flushes': result.get('flushes', 0), 'tmp_db': result.get('tmp_db', ''),
            'written': result.get('written', [])}

def process_newspaper(newspaper: str, args_dict: dict) -> list[dict[str, object]]:
    threads = int(args_dict.get('threads') or get_root_config('concurrency', 'threads_per_newspaper', default=10))
    langs = args_dict.get('langs') or [c.lang for c in load_source_configs(newspaper)]
    print(f'[PROC {os.getpid()}] {newspaper}: {threads} threads, langs={langs}')
    return [run_source(newspaper, lang, args_dict['mode'], args_dict.get('start_date'), args_dict.get('end_date'),
                       args_dict.get('limit'), args_dict.get('dry_run'), threads, args_dict.get('db_root')) for lang in langs]

def run(args: argparse.Namespace) -> list[dict[str, object]]:
    selected = list_newspapers() if args.all else [args.newspaper]
    if not selected or any(x is None for x in selected): raise SystemExit('Use --all or --newspaper NAME')
    args_dict = {'mode': args.mode, 'start_date': _parse_date(args.start_date), 'end_date': _parse_date(args.end_date),
                 'limit': args.limit, 'dry_run': args.dry_run, 'threads': args.threads, 'db_root': args.db_root,
                 'langs': [args.lang] if args.lang else None}
    if args.all:
        print(f'[ALL] multiprocessing: {len(selected)} newspaper processes; each uses {args_dict["threads"] or 10} threads')
        out: list[dict[str, object]] = []
        with ProcessPoolExecutor(max_workers=len(selected)) as ex:
            for fut in as_completed([ex.submit(process_newspaper, n, args_dict) for n in selected]): out.extend(fut.result())
        return out
    return process_newspaper(selected[0], args_dict)

def build_parser(mode: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(); p.set_defaults(mode=mode)
    g = p.add_mutually_exclusive_group(required=True); g.add_argument('--all', action='store_true'); g.add_argument('--newspaper')
    p.add_argument('--lang'); p.add_argument('--start-date'); p.add_argument('--end-date')
    p.add_argument('--limit', type=int); p.add_argument('--threads', type=int); p.add_argument('--db-root')
    p.add_argument('--dry-run', action='store_true')
    return p
