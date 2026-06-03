from __future__ import annotations
import json, os
from datetime import date
from pathlib import Path
from typing import Any
from .models import SourceConfig

ROOT_PATH = Path(__file__).resolve().parent.parent
COLAB_ENV = "COLAB_RELEASE_TAG" in os.environ

def _parse_scalar(v: str) -> Any:
    v = v.strip().strip('"').strip("'")
    if v in ("", "null", "None", "~"):
        return ""
    if v.lower() in ("true", "false"):
        return v.lower() == "true"
    try:
        return int(v)
    except ValueError:
        return v

def _mini_yaml(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}; stack = [(0, data)]
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith('#'):
            continue
        indent = len(raw) - len(raw.lstrip(' ')); line = raw.strip()
        while stack and indent < stack[-1][0]: stack.pop()
        parent = stack[-1][1]
        if ':' not in line: continue
        k, v = line.split(':', 1); k = k.strip(); v = v.strip()
        if v == "":
            parent[k] = {}; stack.append((indent + 2, parent[k]))
        else:
            parent[k] = _parse_scalar(v)
    return data

def read_config_file(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml
        return yaml.safe_load(text) or {}
    except Exception:
        try:
            return json.loads(text)
        except Exception:
            return _mini_yaml(text)

def get_root_config(*keys: str, default: Any = None) -> Any:
    value: Any = read_config_file(ROOT_PATH / "config.yaml")
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            return default
        value = value[key]
    return value

def db_root_path(override: str | None = None) -> Path:
    raw = override or get_root_config("db_root_path", default="./output")
    return (ROOT_PATH / raw).resolve() if not Path(raw).is_absolute() else Path(raw)

def site_config_path(newspaper: str) -> Path:
    return ROOT_PATH / "Crawling" / newspaper / "config.yaml"

def list_newspapers() -> list[str]:
    base = ROOT_PATH / "Crawling"
    return sorted(p.name for p in base.iterdir() if p.is_dir() and not p.name.startswith('.'))

def load_source_configs(newspaper: str) -> list[SourceConfig]:
    raw = read_config_file(site_config_path(newspaper))
    items = raw.get("metadata", raw if isinstance(raw, list) else [])
    out: list[SourceConfig] = []
    for item in items:
        sitemaps = item.get("sitemaps") or []
        if isinstance(sitemaps, str): sitemaps = [sitemaps]
        out.append(SourceConfig(
            newspaper=item.get("newspaper", newspaper), lang=item["lang"],
            save_path=Path(item["save_path"]), base_filename=item["base_filename"],
            base_url=item.get("base_url", ""), article_base_url=item.get("article_base_url", ""),
            default_start_date=date.fromisoformat(item.get("default_start_date", "2000-01-01")),
            sitemaps=sitemaps, extra={k: v for k, v in item.items() if k not in {
                "newspaper", "lang", "save_path", "base_filename", "base_url", "article_base_url",
                "default_start_date", "sitemaps"}},
        ))
    return out

def get_source_config(newspaper: str, lang: str) -> SourceConfig:
    for cfg in load_source_configs(newspaper):
        if cfg.lang == lang:
            return cfg
    raise KeyError(f"unknown source: {newspaper}/{lang}")
