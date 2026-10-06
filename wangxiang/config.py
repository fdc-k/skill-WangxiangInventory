"""读取 / 生成配置。"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DEFAULT_CONFIG_PATH = CONFIG_DIR / "config.yaml"
EXAMPLE_CONFIG_PATH = CONFIG_DIR / "config.example.yaml"

_ENV_KEY = "WANGXIANG_CONSUMER_KEY"
_ENV_SECRET = "WANGXIANG_CONSUMER_SECRET"


def _yaml():
    try:
        import yaml  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "缺少 PyYAML。请先运行: python3 -m pip install -r requirements.txt"
        ) from exc
    return yaml


def load_config(path: str | os.PathLike | None = None) -> dict:
    """载入 config.yaml；允许用环境变量覆盖密钥。"""
    yaml = _yaml()
    p = Path(path) if path else DEFAULT_CONFIG_PATH
    if not p.exists():
        # 刚 clone 下来还没建 config.yaml 时的兜底：先用模板跑。
        # 这样 extract / selftest 立刻可用；只有需要联网的命令才必须填密钥。
        if path is None and EXAMPLE_CONFIG_PATH.exists():
            print(f"提示：还没有 {p.name}，这次先用模板 {EXAMPLE_CONFIG_PATH.name} 跑。")
            print("      （读取库存文件和离线自检都不需要密钥；比对网店前请先填好密钥）")
            p = EXAMPLE_CONFIG_PATH
        else:
            raise FileNotFoundError(
                f"找不到配置文件 {p}。请先复制 config/config.example.yaml 为 "
                f"config/config.yaml 并填写信息。"
            )
    with p.open("r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}

    cfg.setdefault("store", {})
    store = cfg["store"]
    store.setdefault("base_url", "")
    store.setdefault("consumer_key", "")
    store.setdefault("consumer_secret", "")
    store.setdefault("verify_ssl", True)
    store.setdefault("timeout", 60)
    store.setdefault("per_page", 100)
    store.setdefault("api_version", "wc/v3")

    if os.environ.get(_ENV_KEY):
        store["consumer_key"] = os.environ[_ENV_KEY]
    if os.environ.get(_ENV_SECRET):
        store["consumer_secret"] = os.environ[_ENV_SECRET]

    cfg.setdefault("paths", {})
    paths = cfg["paths"]
    paths.setdefault("output_dir", "output")
    paths.setdefault("mapping_file", "config/product_map.csv")

    cfg.setdefault("sources", [])
    cfg.setdefault("sync", {})
    sync = cfg["sync"]
    sync.setdefault("mode", "auto")            # auto | status | quantity
    sync.setdefault("update_status", True)
    sync.setdefault("dry_run_default", True)   # 没有 --yes 时永远只做演练
    cfg.setdefault("options", {})
    cfg["options"].setdefault("fuzzy_threshold", 0.86)
    cfg["_root"] = str(ROOT)
    cfg["_path"] = str(p)
    return cfg


def resolve_path(cfg: dict, value: str) -> Path:
    """相对路径按项目根目录解析。"""
    p = Path(value)
    if p.is_absolute():
        return p
    return (ROOT / p).resolve()


def output_dir(cfg: dict) -> Path:
    d = resolve_path(cfg, cfg["paths"]["output_dir"])
    d.mkdir(parents=True, exist_ok=True)
    return d


def mapping_path(cfg: dict) -> Path:
    return resolve_path(cfg, cfg["paths"]["mapping_file"])
