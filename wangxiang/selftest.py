"""离线自检：不碰网络，验证「解析结果没跑偏」。

跑法：``python3 -m wangxiang selftest``

会做三件事：
1. 按 config.yaml 重新解析所有来源，和 ``tests/baseline.json`` 的行数/商品数对比；
2. 检查货盘 PDF 的「打勾判断」是否仍然干净（每个格子要么一堆绿色像素、
   要么一个都没有，不该出现模棱两可的中间值）；
3. 检查 ``config/product_map.csv`` 能不能正常读取、有没有重复键。
"""
from __future__ import annotations

import collections
import json
from pathlib import Path

from . import config as cfgmod
from .console import err as _err, ok as _ok
from .extract_pdf import MARK_RENDER_DPI, PageIndex, _columns_in, find_sections, split_blocks
from .matching import load_mapping, occurrence_keys, parse_size_map
from .models import InventoryRow
from .unify import extract_one_source
from .util import availability_from_quantity, normalize_size, normalize_sku, sku_match_keys

BASELINE_PATH = cfgmod.ROOT / "tests" / "baseline.json"


def _check_sources(cfg, baseline, verbose=True):
    problems = []
    expected = baseline.get("sources", {})
    total = 0
    for source in cfg.get("sources", []):
        sid = source["id"]
        rows, stats, _ = extract_one_source(source, cfg)
        total += stats["rows"]
        exp = expected.get(sid)
        if exp is None:
            if verbose:
                print(f"  [跳过] {sid}：基线里没有它的记录（{stats['rows']} 行 / {stats['products']} 商品）")
            continue
        ok_rows = stats["rows"] == exp["rows"]
        ok_prods = stats["products"] == exp["products"]
        flag = "ok  " if (ok_rows and ok_prods) else "!!  "
        if not (ok_rows and ok_prods):
            problems.append(f"{sid}: {stats['rows']} 行 / {stats['products']} 商品，"
                            f"基线是 {exp['rows']} 行 / {exp['products']} 商品")
        if verbose or not (ok_rows and ok_prods):
            print(f"  {flag}[{sid}] {stats['rows']:>4} 行 / {stats['products']:>3} 商品")
        if stats.get("orphan_skus"):
            problems.append(f"{sid}: 有 SKU 没被分配到商品块 -> {stats['orphan_skus']}")
    if "total_rows" in baseline and total != baseline["total_rows"]:
        problems.append(f"总行数 {total}，基线是 {baseline['total_rows']}")
    return problems, total


def _check_pdf_marks(cfg, verbose=True):
    """货盘的绿点检测应该「非 0 即大」，不该有模棱两可的格子。"""
    import pdfplumber

    problems = []
    for source in cfg.get("sources", []):
        if source.get("adapter") != "pdf_pallet":
            continue
        path = cfgmod.resolve_path(cfg, source["file"])
        with pdfplumber.open(path) as pdf:
            pg = PageIndex(pdf.pages[int(source.get("options", {}).get("page", 1)) - 1])
            counts = []
            for sec in find_sections(pg):
                for col in _columns_in(pg, sec["top"], sec["bottom"]):
                    for block in split_blocks(col["size_words"]):
                        if len(block) < 3:
                            continue
                        for item in block:
                            mid = item.get("mid", item["top"] + 5.0)
                            counts.append(col["mask"].green_count(mid - 11.5, mid + 11.5))
        zero = sum(1 for c in counts if c == 0)
        marked = sum(1 for c in counts if c >= 60)
        ambiguous = len(counts) - zero - marked
        if verbose:
            print(f"  {_ok()} [{source['id']}] 打勾格 {len(counts)} 个：{marked} 个有勾 / {zero} 个无勾 / "
                  f"{ambiguous} 个临界")
        if ambiguous:
            problems.append(f"{source['id']}: 有 {ambiguous} 个格子的绿点数量落在灰区，"
                            f"说明打勾判断不可靠，请检查 MARK_GREEN_MIN / 渲染精度")
    return problems


def _check_mapping(cfg, verbose=True):
    problems = []
    path = cfgmod.mapping_path(cfg)
    if not path.exists():
        if verbose:
            print(f"  --  {path.name} 不存在（还没生成过映射表，属正常）")
        return problems
    mapping = load_mapping(path)
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        import csv
        raw = list(csv.DictReader(fh))
    keys = [(r.get("source", "").strip(), (r.get("category") or "*").strip(),
             (r.get("source_product") or "").strip()) for r in raw
            if (r.get("source_product") or "").strip()]
    dupes = [k for k, n in collections.Counter(keys).items() if n > 1]
    filled = sum(1 for r in raw if (r.get("parent_sku") or "").strip())
    if verbose:
        flag = "!!  " if dupes else f"{_ok()} "
        print(f"  {flag}映射表 {len(raw)} 行，已填 parent_sku {filled} 行")
    if dupes:
        problems.append(f"映射表里有重复键（后者会覆盖前者）：{dupes[:5]}")
    return problems


def _check_helpers(verbose=True):
    """把容易写错的规范化逻辑钉死。"""
    cases = [
        ("SKU 去符号", normalize_sku("192SU-22-4410"), "192SU224410"),
        ("SKU 保留字母", normalize_sku("SP5-H-BROWN-BBV2/XS"), "SP5HBROWNBBV2XS"),
        ("尾字母 F 兼容", "192SU224410" in sku_match_keys("192SU224410F"), True),
        ("尺码 2XL->XXL", normalize_size("2XL"), "XXL"),
        ("尺码 全角", normalize_size(" ｘｌ "), "XL"),
        ("数量->有货", availability_from_quantity(5), "instock"),
        ("数量0->缺货", availability_from_quantity(0), "outofstock"),
        ("size_map 保留网店原写法", parse_size_map("XXL:2XL; L:XL; XL:Extra Large"),
         {"XXL": "2XL", "L": "XL", "XL": "Extra Large"}),
    ]
    def _row(product, size):
        return InventoryRow(source="S", category="c", source_product=product, size=size)

    rows = [_row("A", "M"), _row("A", "L"), _row("B", "M"), _row("A", "M")]
    keys = occurrence_keys(rows)
    cases.append(("重名商品加 #1/#2", keys, ["A#1", "A#1", "B", "A#2"]))

    problems = []
    for name, got, want in cases:
        ok = got == want
        if verbose:
            print(f"  {'ok  ' if ok else '!!  '}{name}: {got!r}")
        if not ok:
            problems.append(f"{name}：实际 {got!r}，期望 {want!r}")
    return problems


def _check_launchers(verbose=True):
    """检查各平台的启动脚本是否齐全、格式正确。

    Windows 的 .bat 有两个硬要求，写错了用户就会看到乱码或直接报错：
      * 必须是 CRLF 换行（LF 换行在某些 cmd 版本下会执行异常）
      * 内容必须是纯 ASCII（中文一律由 Python 打印）
    还要检查每个 ``goto X`` 都有对应的 ``:X`` 标签，否则脚本会跑飞。
    """
    bin_dir = cfgmod.ROOT / "bin"
    problems = []

    required = {
        "win": ["setup.bat", "1-提取库存.bat", "2-差异比对.bat",
                "3-同步更新.bat", "4-离线自检.bat"],
        "posix": ["setup.command", "1-提取库存.command", "2-差异比对.command",
                  "3-同步更新.command", "4-离线自检.command"],
        "shell": ["setup.sh", "1-extract.sh", "2-diff.sh", "3-sync.sh", "4-selftest.sh"],
    }
    for kind, names in required.items():
        missing = [n for n in names if not (bin_dir / n).exists()]
        if missing:
            problems.append(f"缺少{kint_name(kind)}启动脚本：{missing}")
        elif verbose:
            print(f"  ok  {kint_name(kind)}启动脚本齐全（{len(names)} 个）")

    for bat in sorted(bin_dir.glob("*.bat")):
        data = bat.read_bytes()
        bad = [b for b in data if b > 127]
        if bad:
            problems.append(f"{bat.name} 含非 ASCII 字节 {len(bad)} 个（中文请交给 Python 打印）")
        if b"\r\n" not in data:
            problems.append(f"{bat.name} 不是 CRLF 换行，Windows 上可能执行异常")
        text = data.decode("ascii", errors="replace")
        labels = {ln.strip()[1:].split()[0].lower()
                  for ln in text.splitlines()
                  if ln.strip().startswith(":") and len(ln.strip()) > 1}
        gotos = {ln.strip()[5:].strip().lower()
                 for ln in text.splitlines()
                 if ln.strip().lower().startswith("goto ")
                 and ln.strip()[5:].strip()}
        dangling = sorted(g for g in gotos if g and g not in labels)
        if dangling:
            problems.append(f"{bat.name} 里的 goto 找不到目标标签：{dangling}")
    if verbose and not problems:
        print(f"  ok  .bat 全部为纯 ASCII + CRLF，goto 标签都能对上")

    for tool in ("tools/bootstrap.py", "tools/banner.py"):
        if not (cfgmod.ROOT / tool).exists():
            problems.append(f"缺少 {tool}（安装脚本依赖它）")
    if verbose and not problems:
        print("  ok  tools/ 下的安装脚本齐全")
    return problems


def _check_docs(verbose=True):
    """检查文档：内部链接有没有断、跨平台命令说明有没有缺。"""
    import re

    root = cfgmod.ROOT
    files = [root / "README.md", root / "SKILL.md"] + sorted((root / "docs").glob("*.md"))
    problems, links = [], 0
    for f in files:
        text = f.read_text(encoding="utf-8")
        for m in re.finditer(r"\]\(([^)#]+\.md)\)", text):
            links += 1
            if not (f.parent / m.group(1)).resolve().exists():
                problems.append(f"{f.name} 里的链接失效：{m.group(1)}")
        # 提到 macOS 专用路径时，必须同时说明 Windows 怎么写
        if ".venv/bin/python" in text and not any(
                k in text for k in ("Scripts", "Windows 用户", "写法对照表")):
            problems.append(f"{f.name} 用了 .venv/bin/python，但没说明 Windows 的写法")
    if verbose:
        flag = "!!  " if problems else "ok  "
        print(f"  {flag}文档 {len(files)} 篇，内部链接 {links} 条")
    return problems


def kint_name(kind):
    return {"win": "Windows", "posix": "macOS 双击", "shell": "终端"}[kind]


def run(cfg, verbose=True) -> int:
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8")) \
        if BASELINE_PATH.exists() else {}
    print(f"祥旺库存工具 自检（离线，不访问网络）")
    print(f"  基线文件：{BASELINE_PATH}")
    problems = []

    print("\n[1/6] 解析来源文件并与基线对比")
    p, total = _check_sources(cfg, baseline, verbose)
    problems += p
    print(f"  合计 {total} 行")

    print("\n[2/6] 检查货盘 PDF 的打勾识别质量")
    problems += _check_pdf_marks(cfg, verbose)

    print("\n[3/6] 检查商品映射表")
    problems += _check_mapping(cfg, verbose)

    print("\n[4/6] 检查规范化逻辑（SKU / 尺码 / 数量 / 重名编号）")
    problems += _check_helpers(verbose)

    print("\n[5/6] 检查各平台启动脚本（Windows / macOS / Linux）")
    problems += _check_launchers(verbose)

    print("\n[6/6] 检查文档（链接 / 跨平台说明）")
    problems += _check_docs(verbose)

    print()
    if problems:
        print(f"{_err()} 自检未通过：")
        for x in problems:
            print(f"   - {x}")
        return 1
    print(f"{_ok()} 自检全部通过。")
    return 0
