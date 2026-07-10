from __future__ import annotations
import json, os
from datetime import date
from pathlib import Path
from typing import Any
from .models import SourceConfig

ROOT_PATH = Path(__file__).resolve().parent.parent
COLAB_ENV = "COLAB_RELEASE_TAG" in os.environ
ENV_PATH = ROOT_PATH / ".env"

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

def load_env(path: Path = ENV_PATH) -> dict[str, str]:
    if not path.exists():
        return {}
    env: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env

def env_value(key: str, default: str = "") -> str:
    return os.environ[key] if key in os.environ else load_env().get(key, default)

def output_mode() -> str:
    return env_value("KZ_MEDIA_OUTPUT_MODE", "sql").strip().lower()

def output_path(override: str | None = None) -> Path:
    raw = override or env_value("KZ_MEDIA_OUTPUT_PATH", "./new_data_v2.py")
    path = Path(raw).expanduser()
    return (ROOT_PATH / path).resolve() if not path.is_absolute() else path

def sql_template_path() -> Path:
    raw = env_value("KZ_MEDIA_SQL_TEMPLATE", "~/Desktop/kz_media.sql")
    return Path(raw).expanduser()

def psql_settings() -> dict[str, str]:
    return {
        "username": env_value("KZ_MEDIA_PSQL_USERNAME", ""),
        "password": env_value("KZ_MEDIA_PSQL_PASSWORD", ""),
        "host": env_value("KZ_MEDIA_PSQL_HOST", "localhost"),
        "port": env_value("KZ_MEDIA_PSQL_PORT", "5432"),
        "db_name": env_value("KZ_MEDIA_PSQL_DB_NAME", ""),
        "sslmode": env_value("KZ_MEDIA_PSQL_SSLMODE", "prefer"),
        "schema": env_value("KZ_MEDIA_PSQL_SCHEMA", ""),
    }

def sql_table_names() -> tuple[str, str]:
    return (
        env_value("KZ_MEDIA_PLATFORMS_TABLE", "platforms"),
        env_value("KZ_MEDIA_ARTICLES_TABLE", "articles"),
    )

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
        source_name = item.get("newspaper", newspaper)
        extra = {k: v for k, v in item.items() if k not in {
            "newspaper", "lang", "save_path", "base_filename", "base_url", "article_base_url",
            "default_start_date", "sitemaps"}}
        if source_name.startswith("akorda_"):
            extra.setdefault("category", source_name.removeprefix("akorda_"))
            source_name = "akorda"
        out.append(SourceConfig(
            newspaper=source_name, lang=item["lang"],
            save_path=Path(item["save_path"]), base_filename=item["base_filename"],
            base_url=item.get("base_url", ""), article_base_url=item.get("article_base_url", ""),
            default_start_date=date.fromisoformat(item.get("default_start_date", "2000-01-01")),
            sitemaps=sitemaps, extra=extra,
        ))
    return out

def get_source_config(newspaper: str, lang: str) -> SourceConfig:
    for cfg in load_source_configs(newspaper):
        if cfg.lang == lang:
            return cfg
    raise KeyError(f"unknown source: {newspaper}/{lang}")
