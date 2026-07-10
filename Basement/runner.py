from __future__ import annotations
import argparse, asyncio, importlib, os
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from .config import db_root_path, get_root_config, get_source_config, list_newspapers, load_source_configs, output_mode, output_path
from .final_sql_db import SqlAppender, count_rows as count_sql_rows, db_read_urls, ensure_sql_file, import_with_psql, read_urls as read_sql_urls
from .final_sqlite_db import append_rows, count_rows, ensure_final_db, existing_files, read_urls, reset_final_db
from .models import ArticleMeta
from .parsing import date_from_url, slug_title

def _parse_date(s: str | None) -> date | None:
    return date.fromisoformat(s) if s else None

def _site_module(newspaper: str, mod: str):
    return importlib.import_module(f'Crawling.{newspaper}.{mod}')


def _metadata_title_should_replace(existing: str) -> bool:
    return not existing or "<>" in existing or "\n<>" in existing

def _download_row(newspaper: str, meta: ArticleMeta) -> dict[str, str]:
    article = _site_module(newspaper, 'crawling_article')
    try:
        result = article.crawling_article(meta.url, with_metadata=True)
    except TypeError:
        result = article.crawling_article(meta.url)
    if isinstance(result, dict):
        if result.get('author') and not meta.author:
            meta.author = result['author']
        if result.get('title') and _metadata_title_should_replace(meta.title):
            meta.title = result['title']
        if result.get('date') and not meta.date:
            meta.date = result['date']
        if result.get('time') and not meta.time:
            meta.time = result['time']
        if not meta.title:
            meta.title = slug_title(meta.url)
        if not meta.date:
            meta.date = date_from_url(meta.url)
        body = str(result.get('body', '') or '').strip() or meta.title
        rowdata = str(result.get('rowdata', '') or '')
        return meta.row(body, rowdata)
    if not meta.title:
        meta.title = slug_title(meta.url)
    if not meta.date:
        meta.date = date_from_url(meta.url)
    return meta.row(str(result or '').strip() or meta.title)

def _download_to_queue(newspaper: str, meta: ArticleMeta, pending_queue) -> dict[str, str]:
    row = _download_row(newspaper, meta)
    pending_queue.put(row)
    return row

async def _download_to_queue_async(newspaper: str, meta: ArticleMeta, pending_queue) -> dict[str, str]:
    row = await asyncio.to_thread(_download_row, newspaper, meta)
    pending_queue.put(row)
    return row

def _write_pending_rows(cfg, rebuild: bool, db_root: Path | None, flush_rows: int, pending_queue, result_queue) -> None:
    try:
        output_path = reset_final_db(cfg, db_root) if rebuild else ensure_final_db(cfg, db_root)
        seen_urls = set() if rebuild else read_urls(output_path)
        buffer = []
        consumed = 0
        inserted = 0
        flushes = 0

        def flush_buffer() -> None:
            nonlocal buffer, flushes, inserted
            if not buffer:
                return
            inserted += append_rows(output_path, buffer)
            buffer = []
            flushes += 1

        while True:
            row = pending_queue.get()
            if row is None:
                break
            consumed += 1
            url = str(row.get("url", "") or "")
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            buffer.append(row)
            if len(buffer) >= flush_rows:
                flush_buffer()
        flush_buffer()
        result_queue.put({
            'consumed': consumed,
            'inserted': inserted,
            'rows': len(seen_urls),
            'flushes': flushes,
            'output_db': str(output_path),
            'written': [str(output_path)],
        })
    except Exception as exc:
        result_queue.put({'error': repr(exc)})

def _write_pending_sql_rows(cfg, rebuild: bool, sql_path: Path, flush_rows: int, pending_queue, result_queue) -> None:
    try:
        output_path = ensure_sql_file(sql_path, rebuild=rebuild)
        seen_urls = set() if rebuild else (db_read_urls(cfg) or read_sql_urls(output_path))
        buffer = []
        consumed = 0
        inserted = 0
        flushes = 0

        appender = SqlAppender(output_path, cfg)

        def flush_buffer() -> None:
            nonlocal buffer, flushes, inserted
            if not buffer:
                return
            inserted += appender.append(buffer)
            buffer = []
            flushes += 1

        with appender:
            while True:
                row = pending_queue.get()
                if row is None:
                    break
                consumed += 1
                url = str(row.get("url", "") or "")
                if url and url in seen_urls:
                    continue
                if url:
                    seen_urls.add(url)
                buffer.append(row)
                if len(buffer) >= flush_rows:
                    flush_buffer()
            flush_buffer()
        result_queue.put({
            'consumed': consumed,
            'inserted': inserted,
            'rows': count_sql_rows(output_path),
            'flushes': flushes,
            'output_sql': str(output_path),
            'written': [str(output_path)],
        })
    except Exception as exc:
        result_queue.put({'error': repr(exc)})

def run_source(newspaper: str, lang: str, mode: str, start_date: date | None, end_date: date | None,
               limit: int | None, dry_run: bool, threads: int, root_override: str | None) -> dict[str, object]:
    return asyncio.run(run_source_async(newspaper, lang, mode, start_date, end_date, limit, dry_run, threads, root_override))

async def run_source_async(newspaper: str, lang: str, mode: str, start_date: date | None, end_date: date | None,
                           limit: int | None, dry_run: bool, threads: int, root_override: str | None) -> dict[str, object]:
    cfg = get_source_config(newspaper, lang)
    table = _site_module(newspaper, 'crawling_table')
    root = db_root_path(root_override) if root_override else None
    mode_name = output_mode()
    sql_output = output_path() if mode_name in ("sql", "psql") else None
    output_db = None if dry_run or mode == 'rebuild' or sql_output is not None else ensure_final_db(cfg, root)
    existing_path = sql_output if sql_output is not None else output_db
    old_limit = os.environ.get("NCCU_CRAWL_LIMIT")
    old_output_db = os.environ.get("NCCU_OUTPUT_URL_DB")
    if limit: os.environ["NCCU_CRAWL_LIMIT"] = str(limit)
    if existing_path is not None:
        os.environ["NCCU_OUTPUT_URL_DB"] = str(existing_path)
    try:
        listed = table.crawling_table(lang, start_date, end_date)
        metas = [ArticleMeta.from_any(x, cfg.newspaper, lang) for x in listed]
        for meta in metas:
            meta.newspaper = cfg.newspaper
    finally:
        if old_limit is None: os.environ.pop("NCCU_CRAWL_LIMIT", None)
        else: os.environ["NCCU_CRAWL_LIMIT"] = old_limit
        if old_output_db is None: os.environ.pop("NCCU_OUTPUT_URL_DB", None)
        else: os.environ["NCCU_OUTPUT_URL_DB"] = old_output_db
    if limit: metas = metas[:limit]
    if dry_run:
        return {'newspaper': newspaper, 'lang': lang, 'listed': len(metas), 'written': [], 'dry_run': True}
    flush_rows = max(1, int(get_root_config('extracting', 'pending_flush_rows', default=50) or 50))
    if sql_output is not None:
        output_target = ensure_sql_file(sql_output, rebuild=mode == 'rebuild')
        existing_urls = set() if mode == 'rebuild' else (db_read_urls(cfg) or read_sql_urls(output_target))
    elif mode != 'rebuild':
        output_db = output_db or ensure_final_db(cfg, root)
        existing_urls = read_urls(output_db)
    else:
        existing_urls = set()
    if mode != 'rebuild':
        if existing_urls:
            metas = [meta for meta in metas if not meta.url or meta.url not in existing_urls]
    pending_queue = Queue()
    result_queue = Queue()
    writer_target = _write_pending_sql_rows if sql_output is not None else _write_pending_rows
    writer_args = (cfg, mode == 'rebuild', sql_output, flush_rows, pending_queue, result_queue) if sql_output is not None else (cfg, mode == 'rebuild', root, flush_rows, pending_queue, result_queue)
    writer = Thread(target=writer_target, args=writer_args)
    writer.start()
    rows = 0
    semaphore = asyncio.Semaphore(max(1, threads))

    async def download(meta: ArticleMeta) -> None:
        nonlocal rows
        async with semaphore:
            try:
                await _download_to_queue_async(newspaper, meta, pending_queue)
                rows += 1
            except Exception as e:
                print(f'[WARN] article failed: {e}')

    tasks = [asyncio.create_task(download(meta)) for meta in metas]
    if tasks:
        await asyncio.gather(*tasks)
    pending_queue.put(None)
    writer.join(30)
    if writer.is_alive():
        raise RuntimeError("writer timed out")
    try:
        result = result_queue.get(timeout=5)
    except Empty:
        result = {'written': [str(p) for _, p in existing_files(cfg, root)]}
    if result.get('error'):
        raise RuntimeError(f"writer failed: {result['error']}")
    return {'newspaper': newspaper, 'lang': lang, 'listed': len(metas), 'rows': rows,
            'inserted': result.get('inserted', 0), 'flushes': result.get('flushes', 0),
            'output_db': result.get('output_db', ''), 'output_sql': result.get('output_sql', ''),
            'written': result.get('written', [])}

def process_newspaper(newspaper: str, args_dict: dict) -> list[dict[str, object]]:
    threads = int(args_dict.get('threads') or get_root_config('concurrency', 'threads_per_newspaper', default=10))
    langs = args_dict.get('langs') or [c.lang for c in load_source_configs(newspaper)]
    print(f'[PROC {os.getpid()}] {newspaper}: {threads} threads, langs={langs}')
    return [run_source(newspaper, lang, args_dict['mode'], args_dict.get('start_date'), args_dict.get('end_date'),
                       args_dict.get('limit'), args_dict.get('dry_run'), threads, args_dict.get('db_root')) for lang in langs]

def run(args: argparse.Namespace) -> list[dict[str, object]]:
    results = asyncio.run(run_async(args))
    if output_mode() == "psql" and not args.dry_run:
        import_with_psql(output_path())
    return results

async def run_async(args: argparse.Namespace) -> list[dict[str, object]]:
    selected = list_newspapers() if args.all else [args.newspaper]
    if not selected or any(x is None for x in selected): raise SystemExit('Use --all or --newspaper NAME')
    args_dict = {'mode': args.mode, 'start_date': _parse_date(args.start_date), 'end_date': _parse_date(args.end_date),
                 'limit': args.limit, 'dry_run': args.dry_run, 'threads': args.threads, 'db_root': args.db_root,
                 'langs': [args.lang] if args.lang else None}
    if args.all:
        if output_mode() in ("sql", "psql"):
            print(f'[ALL] async sequential sources; each uses {args_dict["threads"] or 10} article tasks')
            out: list[dict[str, object]] = []
            for newspaper in selected:
                out.extend(await process_newspaper_async(newspaper, args_dict))
            return out
        print(f'[ALL] multiprocessing: {len(selected)} newspaper processes; each uses {args_dict["threads"] or 10} threads')
        out: list[dict[str, object]] = []
        with ProcessPoolExecutor(max_workers=len(selected)) as ex:
            for fut in as_completed([ex.submit(process_newspaper, n, args_dict) for n in selected]): out.extend(fut.result())
        return out
    return await process_newspaper_async(selected[0], args_dict)

async def process_newspaper_async(newspaper: str, args_dict: dict) -> list[dict[str, object]]:
    threads = int(args_dict.get('threads') or get_root_config('concurrency', 'threads_per_newspaper', default=10))
    langs = args_dict.get('langs') or [c.lang for c in load_source_configs(newspaper)]
    print(f'[ASYNC] {newspaper}: {threads} article tasks, langs={langs}')
    return [await run_source_async(newspaper, lang, args_dict['mode'], args_dict.get('start_date'), args_dict.get('end_date'),
                                   args_dict.get('limit'), args_dict.get('dry_run'), threads, args_dict.get('db_root')) for lang in langs]

def build_parser(mode: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(); p.set_defaults(mode=mode)
    g = p.add_mutually_exclusive_group(required=True); g.add_argument('--all', action='store_true'); g.add_argument('--newspaper')
    p.add_argument('--lang'); p.add_argument('--start-date'); p.add_argument('--end-date')
    p.add_argument('--limit', type=int); p.add_argument('--threads', type=int); p.add_argument('--db-root')
    p.add_argument('--dry-run', action='store_true')
    return p
