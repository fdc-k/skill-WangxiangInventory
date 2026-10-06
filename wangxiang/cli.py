"""命令行入口：python3 -m wangxiang <命令>"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from . import __version__, config as cfgmod
from .console import arrow, err, ok, setup as setup_console, warn
from . import runtime
from .diff import S_CHANGE, build_diff, summarize
from .matching import build_index, load_mapping, save_mapping, suggest_mapping_rows
from .report import console_preview, write_markdown, write_report_html, write_report_xlsx
from .selftest import run as run_selftest
from .sync import (apply_updates, rollback as run_rollback, select_changes,
                   write_snapshot, write_sync_log)
from .unify import run_extract
from .woo import WooClient, WooError

SOURCES_HELP = "只处理指定来源 id（逗号分隔），默认全部"


def _client(cfg) -> WooClient:
    store = cfg["store"]
    return WooClient(
        store["base_url"], store["consumer_key"], store["consumer_secret"],
        verify_ssl=bool(store.get("verify_ssl", True)),
        timeout=int(store.get("timeout", 60)),
        per_page=int(store.get("per_page", 100)),
        api_version=store.get("api_version", "wc/v3"),
        cache_dir=cfgmod.output_dir(cfg) / ".cache",
    )


def _print_header(cfg):
    print(f"祥旺库存工具 v{__version__}")
    print(f"  店铺：{cfg['store']['base_url']}")
    print(f"  输出目录：{cfgmod.output_dir(cfg)}")


# ------------------------------------------------------------------ 命令

def cmd_check(args):
    cfg = cfgmod.load_config(args.config)
    _print_header(cfg)

    print("\n[1/3] 检查依赖")
    missing = []
    for mod in ("openpyxl", "pdfplumber", "numpy", "requests", "yaml"):
        try:
            __import__(mod)
            print(f"  {ok()}  {mod}")
        except ImportError:
            missing.append(mod)
            print(f"  缺少 {mod}")
    if missing:
        print("\n请先安装依赖：先跑一次安装脚本（bin/setup.command 或 bin\\setup.bat，"
              "或在项目目录执行 python tools\\bootstrap.py）")
        return 2

    print("\n[2/3] 检查来源文件")
    all_ok = True
    for src in cfg.get("sources", []):
        path = cfgmod.resolve_path(cfg, src["file"])
        exists = path.exists()
        all_ok = all_ok and exists
        print(f"  {ok() if exists else '找不到'} [{src['id']}] {path}")
    if not cfg.get("sources"):
        print("  （配置文件里还没有写 sources）")

    print("\n[3/3] 测试 WooCommerce 连接")
    try:
        client = _client(cfg)
        data = client.get("products", per_page=1)
        print(f"  {ok()}  连接成功，店铺返回了 {len(data)} 条商品样本")
    except Exception as exc:  # noqa: BLE001
        all_ok = False
        print(f"  {err()} 连接失败：{exc}")

    print("\n------ 运行环境 ------")
    for k, v in runtime.describe_environment().items():
        print(f"  {k}：{v}")
    return 0 if all_ok else 1


def cmd_extract(args):
    cfg = cfgmod.load_config(args.config)
    _print_header(cfg)
    only = args.sources.split(",") if args.sources else None
    print("\n开始读取来源文件并生成统一格式库存……")
    res = run_extract(cfg, only=only, verbose=True)
    print(f"\n完成：共 {len(res['rows'])} 行库存。")
    print(f"输出目录：{res['dir']}")
    for sid, info in res["sources"].items():
        print(f"  - {info['file']}")
    return 0


def cmd_selftest(args):
    cfg = cfgmod.load_config(args.config)
    _print_header(cfg)
    return run_selftest(cfg)


def _load_rows_from_unified(cfg):
    """重新读取统一格式的 Excel（= 需求里的「再次读取」）。"""
    import openpyxl

    from .models import InventoryRow

    unified_dir = cfgmod.output_dir(cfg) / "unified"
    files = sorted(unified_dir.glob("*_统一库存.xlsx"))
    files = [f for f in files if f.name != "全部库存_合并.xlsx"]
    if not files:
        raise FileNotFoundError(
            f"{unified_dir} 下没有统一格式库存文件，请先运行：python3 -m wangxiang extract")
    rows = []
    for f in files:
        wb = openpyxl.load_workbook(f, data_only=True)
        ws = wb.worksheets[0]
        header = [c.value for c in ws[1]]
        for r in ws.iter_rows(min_row=2, values_only=True):
            d = dict(zip(header, r))
            if not d.get("source_product") and not d.get("size"):
                continue
            rows.append(InventoryRow(
                source=str(d.get("source") or ""), category=str(d.get("category") or ""),
                source_product=str(d.get("source_product") or ""), size=str(d.get("size") or ""),
                quantity=(int(d["quantity"]) if str(d.get("quantity") or "").strip() not in ("", "None") else None),
                availability=str(d.get("availability") or "instock"),
                source_ref=str(d.get("source_ref") or ""),
            ))
        wb.close()
    return rows, [f.name for f in files]


def cmd_diff(args):
    cfg = cfgmod.load_config(args.config)
    if getattr(args, "combo", False):
        cfg.setdefault("options", {})["include_combo_skus"] = True
    _print_header(cfg)
    rows, files = _load_rows_from_unified(cfg)
    print(f"\n读取统一格式文件 {len(files)} 个，共 {len(rows)} 行库存。")
    client = _client(cfg)
    catalog = client.fetch_catalog(refresh=args.refresh, verbose=True)

    cfg["_mapping_path"] = cfgmod.mapping_path(cfg)
    if not cfg["_mapping_path"].exists():
        print("  未找到映射表，正在生成建议映射表 config/product_map.csv ……")
        idx = build_index(catalog)
        save_mapping(cfg["_mapping_path"], suggest_mapping_rows(rows, {}, idx, catalog))
    mapping = load_mapping(cfg["_mapping_path"])
    print(f"  已加载人工映射 {len(mapping)} 条。")

    index = build_index(catalog)
    diffs = build_diff(rows, catalog, cfg)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = cfgmod.output_dir(cfg) / "diff"
    out.mkdir(parents=True, exist_ok=True)
    meta = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "store": cfg["store"]["base_url"],
        "sources": "、".join(files),
    }
    xlsx = out / f"库存差异_{stamp}.xlsx"
    md = out / f"库存差异_{stamp}.md"
    write_report_xlsx(diffs, xlsx, meta, index=index, catalog=catalog)
    write_markdown(diffs, md, meta)
    html = out / f"库存差异_{stamp}.html"
    write_report_html(diffs, html, meta, index=index, catalog=catalog)

    s = summarize(diffs)
    print("\n===== 比对结果 =====")
    for k in ("total", S_CHANGE, "一致", "本店无此商品", "本店无此尺码", "未能匹配"):
        print(f"  {k}: {s.get(k, 0)}")
    print(f"\n  彩色报表（Excel）：{xlsx}")
    print(f"  彩色报表（网页，双击即可看）：{html}")
    print(f"  Markdown：{md}")
    print("\n" + console_preview(diffs, limit=args.limit))
    if args.json:
        Path(args.json).write_text(
            json.dumps([d.__dict__ for d in diffs], ensure_ascii=False, indent=2, default=str),
            encoding="utf-8")
        print(f"\n已写出 JSON：{args.json}")
    print(f"\n如确认无误，运行：python3 -m wangxiang sync --yes")
    return 0


def cmd_sync(args):
    cfg = cfgmod.load_config(args.config)
    if getattr(args, "combo", False):
        cfg.setdefault("options", {})["include_combo_skus"] = True
    _print_header(cfg)
    rows, files = _load_rows_from_unified(cfg)
    client = _client(cfg)
    catalog = client.fetch_catalog(refresh=args.refresh, verbose=True)
    cfg["_mapping_path"] = cfgmod.mapping_path(cfg)
    diffs = build_diff(rows, catalog, cfg)
    changes = select_changes(diffs, only_sku=args.only_sku, only_source=args.only_source)
    total_change = sum(1 for d in diffs if d.status == S_CHANGE)
    if args.only_sku or args.only_source:
        print(f"\n按条件筛选：全部有差异 {total_change} 条 → 本次只处理 {len(changes)} 条。")
    else:
        print(f"\n待更新 {len(changes)} 条。")
    if not changes:
        print("没有需要更新的内容。")
        return 0
    dry = not args.yes
    if dry:
        print("当前为演练模式（不会改动线上数据）。")
        if not args.ask:
            print("确认要真正更新时请加 --yes。")
    if args.ask:
        if not changes:
            return 0
        print("\n" + "=" * 58)
        print("  上面是【演练】结果，网店还没有任何改动。")
        print("=" * 58)
        try:
            answer = input("确认要真正更新网店吗？输入 YES 再按回车（其它任何输入=取消）：").strip()
        except (EOFError, KeyboardInterrupt):
            answer = ""
        if answer.upper() != "YES":
            print("\n已取消，网店数据没有任何改动。")
            return 0
        print("\n开始真正更新……")
        dry = False
    results, stats = apply_updates(diffs, catalog, cfg, client, dry_run=dry, verbose=True,
                                   subset=changes)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = cfgmod.output_dir(cfg) / "sync"
    out.mkdir(parents=True, exist_ok=True)
    log = out / f"同步结果_{stamp}.xlsx"
    snapshot = write_snapshot(results, out / f"回滚快照_{stamp}.json",
                              {"generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                               "store": cfg["store"]["base_url"], "dry_run": dry})
    write_sync_log(results, stats, log, {"generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                        "store": cfg["store"]["base_url"]})
    print("\n===== 同步汇总 =====")
    print(f"  计划 {stats['total']} 条，成功 {stats['success']}，失败 {stats['failed']}，"
          f"跳过/演练 {stats['skipped']}")
    print(f"  明细日志：{log}")
    if stats["success"] or (dry and stats["skipped"]):
        print(f"  回滚快照：{snapshot}   （真要撤回时跑： wangxiang rollback \"{snapshot}\" --yes）")
    if not dry and stats["success"]:
        # 线上数据已经变了，作废本地缓存，避免下次 diff 用旧数据
        cache = cfgmod.output_dir(cfg) / ".cache" / "woo_catalog.json"
        if cache.exists():
            cache.unlink()
            print("  已作废本地商品缓存，下次 diff 会重新拉取最新数据。")
    return 0 if stats["failed"] == 0 else 1


def cmd_rollback(args):
    cfg = cfgmod.load_config(args.config)
    _print_header(cfg)
    client = _client(cfg)
    dry = not args.yes
    if dry:
        print("\n演练模式：只显示会还原成什么，不提交。要真正还原请加 --yes。")
    results, stats = run_rollback(args.snapshot, client, dry_run=dry, verbose=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = cfgmod.output_dir(cfg) / "sync"
    out.mkdir(parents=True, exist_ok=True)
    log = out / f"回滚结果_{stamp}.xlsx"
    write_sync_log(results, stats, log, {"generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                        "store": cfg["store"]["base_url"]})
    print(f"\n===== 回滚汇总 =====\n  共 {stats['total']} 条，成功 {stats['success']}，"
          f"失败 {stats['failed']}，演练 {stats['skipped']}")
    print(f"  明细：{log}")
    return 0 if stats["failed"] == 0 else 1


def cmd_map(args):
    cfg = cfgmod.load_config(args.config)
    rows, _ = _load_rows_from_unified(cfg)
    client = _client(cfg)
    catalog = client.fetch_catalog(refresh=args.refresh, verbose=True)
    mapping = {} if args.overwrite else load_mapping(cfgmod.mapping_path(cfg))
    idx = build_index(catalog)
    allow_combo = bool(cfg.get("options", {}).get("include_combo_skus", False))
    suggests = suggest_mapping_rows(rows, mapping, idx, catalog, allow_combo=allow_combo)
    path = cfgmod.mapping_path(cfg)
    if args.write:
        save_mapping(path, suggests)
        print(f"已写出映射表：{path}")
    else:
        print(f"{'来源':<10}{'来源商品':<40}{'建议 parent_sku':<22}说明")
        for r in suggests:
            print(f"{r['source']:<10}{r['source_product'][:38]:<40}"
                  f"{r['parent_sku'][:20]:<22}{r['note']}")
        print(f"\n加 --write 可写回 {path}")
    return 0


# ------------------------------------------------------------------ 入口

def build_parser():
    p = argparse.ArgumentParser(prog="python3 -m wangxiang",
                                description="祥旺库存工具：多来源库存 -> 统一格式 -> WooCommerce 同步")
    p.add_argument("--config", help="配置文件路径（默认 config/config.yaml）")
    p.add_argument("--version", action="version", version=f"wangxiang-inventory {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("check", help="环境与连接自检")
    sp.set_defaults(func=cmd_check)

    sp = sub.add_parser("selftest", help="离线自检：解析结果是否还和基线一致（不访问网络）")
    sp.set_defaults(func=cmd_selftest)

    sp = sub.add_parser("extract", help="读取来源文件并生成统一格式库存 Excel")
    sp.add_argument("--sources", help=SOURCES_HELP)
    sp.set_defaults(func=cmd_extract)

    sp = sub.add_parser("diff", help="与线上库存比对并生成彩色差异报表")
    sp.add_argument("--refresh", action="store_true", help="强制重新拉取 WooCommerce 数据")
    sp.add_argument("--limit", type=int, default=25, help="控制台预览行数")
    sp.add_argument("--json", help="额外输出 JSON 文件路径")
    sp.add_argument("--combo", action="store_true",
                    help="允许用「组合商品」的货号匹配（结果仅供参考，默认关闭）")
    sp.set_defaults(func=cmd_diff)

    sp = sub.add_parser("sync", help="把差异写回 WooCommerce（不加 --yes 只演练）")
    sp.add_argument("--yes", action="store_true", help="确认执行真实更新")
    sp.add_argument("--refresh", action="store_true", help="强制重新拉取 WooCommerce 数据")
    sp.add_argument("--combo", action="store_true", help="允许用「组合商品」的货号匹配")
    sp.add_argument("--only-sku", metavar="关键词",
                    help="只同步货号/商品名/来源商品里含这个关键词的条目")
    sp.add_argument("--only-source", action="append", metavar="来源ID",
                    help="只同步指定来源（可重复，如 --only-source SP5 --only-source PALLET）")
    sp.add_argument("--ask", action="store_true",
                    help="先演练，然后问我一次「要不要真的更新」（适合双击运行）")
    sp.set_defaults(func=cmd_sync)

    sp = sub.add_parser("rollback", help="按同步时生成的快照把库存还原回去")
    sp.add_argument("snapshot", help="回滚快照 JSON 的路径（在 output/sync/ 里）")
    sp.add_argument("--yes", action="store_true", help="确认执行真实还原")
    sp.set_defaults(func=cmd_rollback)

    sp = sub.add_parser("map", help="生成商品映射表建议")
    sp.add_argument("--write", action="store_true", help="写回 config/product_map.csv")
    sp.add_argument("--overwrite", action="store_true", help="忽略已有映射重新生成")
    sp.add_argument("--refresh", action="store_true", help="强制重新拉取 WooCommerce 数据")
    sp.set_defaults(func=cmd_map)
    return p


def main(argv=None):
    setup_console()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, WooError, ValueError) as exc:
        print(f"\n[错误] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
