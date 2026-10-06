"""把来源商品匹配到 WooCommerce 商品 / 变体。"""
from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

from .util import (digits_of, levenshtein, name_tokens, normalize_name, normalize_size,
                   normalize_sku, raw_size_key, size_equals, sku_match_keys, split_sku_field)

MAPPING_HEADER = ["source", "category", "source_product", "parent_sku", "size_map", "note"]


def load_mapping(path) -> dict[tuple[str, str], dict]:
    """读取 product_map.csv。

    键 = (source, category, source_product)，值 = {"parent_sku", "size_map", "note"}。
    ``source`` / ``category`` 支持 ``*`` 通配（匹配所有来源 / 所有分区）。
    """
    path = Path(path)
    mapping: dict[tuple[str, str, str], dict] = {}
    if not path.exists():
        return mapping
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            src = (row.get("source") or "").strip()
            cat = (row.get("category") or "*").strip() or "*"
            prod = (row.get("source_product") or "").strip()
            if not prod:
                continue
            mapping[(src, cat, prod)] = {
                "parent_sku": (row.get("parent_sku") or "").strip(),
                "size_map": (row.get("size_map") or "").strip(),
                "note": (row.get("note") or "").strip(),
            }
    return mapping


def save_mapping(path, rows: list[dict]):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=MAPPING_HEADER)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in MAPPING_HEADER})
    return path


def parse_size_map(text: str) -> dict[str, str]:
    """``XXL:2XL;L:XL`` -> {"XXL": "2XL", "L": "XL"}"""
    out = {}
    for chunk in (text or "").replace("；", ";").split(";"):
        if ":" in chunk:
            a, b = chunk.split(":", 1)
            if a.strip() and b.strip():
                # 源尺码用标准化的键，目标尺码保留原始写法（网店怎么写就怎么写）
                out[normalize_size(a)] = b.strip()
    return out


def occurrence_keys(rows) -> list[str]:
    """给「同一来源同一分区里重名」的商品加上 ``#2``、``#3`` 后缀。

    货盘 PDF 的同一个分区里可能出现两个都叫 ``Brown`` 的商品（例如
    ``Sp5der Web Sweatpants/Brown`` 与 ``Sp5der Beluga Sweatpants/Brown``），
    加序号后才能分别映射到不同的 parent_sku。

    注意：同一商品的多个尺码行是**连续**的，这里按「连续块」计数，
    因此同一个商品的所有尺码会拿到同一个键。
    """
    base_of = lambda r: (r.source, r.category, r.source_product)
    blocks = []
    for i, r in enumerate(rows):
        if i == 0 or base_of(rows[i - 1]) != base_of(r):
            blocks.append(base_of(r))
    totals = Counter(blocks)

    keys, running, prev, cur = [], {}, None, None
    for r in rows:
        base = base_of(r)
        if base != prev:
            prev = base
            running[base] = running.get(base, 0) + 1
            cur = r.source_product if totals[base] == 1 else f"{r.source_product}#{running[base]}"
        keys.append(cur)
    return keys


def build_index(catalog: dict):
    """为匹配建立索引。"""
    products = catalog.get("products", [])
    by_sku: dict[str, int] = {}
    by_combo: dict[str, int] = {}
    by_name: dict[str, int] = {}
    for p in products:
        for key in sku_match_keys(p.get("sku")):
            by_sku.setdefault(key, p["id"])
        for tok in split_sku_field(p.get("sku")):
            if len(split_sku_field(p.get("sku"))) < 2:
                continue
            for key in sku_match_keys(tok):
                by_combo.setdefault(key, p["id"])
        nk = normalize_name(p.get("name"))
        if nk:
            by_name.setdefault(nk, p["id"])
    return {
        "products": {p["id"]: p for p in products},
        "by_sku": by_sku,
        "by_combo": by_combo,
        "by_name": by_name,
        "by_id": {p["id"]: p for p in products},
    }


def find_variation(catalog: dict, product_id: int, size: str, size_map: dict | None = None):
    """在某个商品的变体里按尺码找变体。"""
    want = (size_map or {}).get(normalize_size(size), size)
    variations = catalog.get("variations", {}).get(str(product_id), [])
    for v in variations:
        for attr in v.get("attributes", []) or []:
            if size_equals(attr.get("option"), want):
                return v
    return None


def match_product(row, mapping: dict, index: dict, catalog: dict, threshold: float = 0.86,
                  product_key: str | None = None, allow_combo: bool = False):
    """返回 ``(product_id, method, mapped_sku)``；匹配不到返回 ``(None, "unmatched", "")``。"""
    prod = product_key if product_key is not None else row.source_product
    rule = None
    for key in ((row.source, row.category, prod),
                ("*", row.category, prod),
                (row.source, "*", prod),
                ("*", "*", prod),
                (row.source, row.category, row.source_product),
                ("*", "*", row.source_product)):
        if key in mapping:
            rule = mapping[key]
            break
    if rule and rule.get("parent_sku"):
        wanted = normalize_sku(rule["parent_sku"])
        pid = index["by_sku"].get(wanted) or index["by_sku"].get(wanted.rstrip("F"))
        if pid:
            return pid, "人工映射", rule["parent_sku"]
        return None, "映射的 SKU 在本店不存在", rule["parent_sku"]

    # 1) 直接按 SKU（来源里的 SKU 就是商品主 SKU）
    for cand in sorted(sku_match_keys(row.source_product)):
        if cand in index["by_sku"]:
            return index["by_sku"][cand], "SKU 相同", ""

    # 1b) SKU 只是某个「组合商品」里的一半
    if allow_combo:
        for cand in sorted(sku_match_keys(row.source_product)):
            if cand in index.get("by_combo", {}):
                return index["by_combo"][cand], "组合商品 SKU 命中", ""

    # 2) 名称完全相同
    nk = normalize_name(row.source_product)
    if nk and nk in index["by_name"]:
        return index["by_name"][nk], "商品名相同", ""

    # 3) 词元相似度（用 Jaccard：交集 / 并集）
    #    用并集做分母，才不会出现 "Black" 命中 "Sp5der Sweatpants/Black" 这种
    #    「来源是网店名字的一小部分」的误配。
    tokens = name_tokens(row.source_product)
    if len(tokens) >= 2:
        best, best_score = None, 0.0
        for pid, prod in index["products"].items():
            other = name_tokens(prod.get("name"))
            if len(other) < 2:
                continue
            inter = len(tokens & other)
            union = len(tokens | other)
            score = inter / union if union else 0.0
            if score > best_score:
                best, best_score = pid, score
        if best and best_score >= threshold:
            return best, f"名称相似度 {best_score:.2f}", ""
    return None, "未匹配", ""


def nearest_sku(source_key: str, index: dict, catalog: dict, *, max_distance: int = 2,
                limit: int = 3):
    """给一个匹配不上的来源货号，找店里最像的货号。

    只有在「编辑距离 <= max_distance」或「数字部分完全相同」时才算建议，
    否则宁可返回空列表，避免又制造一批错配。
    """
    want = normalize_sku(source_key)
    if not want:
        return []
    want_digits = digits_of(source_key)
    scored = []
    # 先看普通货号；组合商品的货号（一个字段里两个货号）也一起找，
    # 因为不少单件在店里只以「组合款」出售。
    pools = [index.get("by_sku", {}), index.get("by_combo", {})]
    for pool_i, pool in enumerate(pools):
        for key, pid in pool.items():
            if not key:
                continue
            d = levenshtein(want, key)
            same_digits = bool(want_digits) and digits_of(key) == want_digits
            if d <= max_distance or same_digits:
                scored.append((0 if d == 0 else d, pool_i, 0 if same_digits else 1, pid))
    scored.sort(key=lambda x: (x[0], x[1], x[2]))
    out, seen = [], set()
    for _, pool_i, _, pid in scored:
        if pid in seen:
            continue
        seen.add(pid)
        prod = index["by_id"].get(pid, {})
        sku = prod.get("sku", "")
        out.append({"product_id": pid, "sku": sku, "name": prod.get("name", ""),
                    "combo": pool_i == 1,
                    "distance": levenshtein(want, normalize_sku(source_key))})
        if len(out) >= limit:
            break
    for item in out:
        item["distance"] = min(levenshtein(want, normalize_sku(tok))
                               for tok in split_sku_field(item["sku"])) if item["sku"] else 99
    return out


def suggest_mapping_rows(rows, mapping, index, catalog, threshold=0.86, allow_combo=False):
    """为「没有人工映射」的来源商品生成建议行（去重）。"""
    seen, out = set(), []
    for row, key in zip(rows, occurrence_keys(rows)):
        if (row.source, row.category, key) in seen:
            continue
        seen.add((row.source, row.category, key))
        pid, method, mapped = match_product(row, mapping, index, catalog, threshold, key,
                                            allow_combo=allow_combo)
        parent = ""
        if pid:
            parent = catalog["products"] and index["by_id"][pid].get("sku", "")
        out.append({
            "source": row.source,
            "category": row.category,
            "source_product": key,
            "parent_sku": parent or (mapped or ""),
            "size_map": "",
            "note": method if pid else "⚠ 需要人工填写 parent_sku",
        })
    return out
