"""来源库存 vs WooCommerce 在线库存 的差异比对。"""
from __future__ import annotations

from dataclasses import dataclass, field

from .matching import (build_index, find_variation, load_mapping, match_product,
                       occurrence_keys, parse_size_map)

DIFF_COLUMNS = [
    "状态", "来源", "分区/品类", "来源商品", "来源尺码",
    "本店 SKU", "本店商品", "变体 ID",
    "来源数量", "在线数量", "数量差",
    "来源库存状态", "在线库存状态",
    "本店是否管理库存", "匹配方式", "将要执行的更新", "备注",
]

# 状态标签
S_CHANGE = "有差异"
S_SAME = "一致"
S_NO_PRODUCT = "本店无此商品"
S_NO_VARIATION = "本店无此尺码"
S_UNMAPPED = "未能匹配"
S_NEED_QTY = "需人工填数量"   # 来源只标「有货」，但网店该变体管理库存且数量为 0

STATUS_LABEL = {"instock": "有货", "outofstock": "缺货"}


@dataclass
class DiffRow:
    status: str
    source: str
    category: str
    source_product: str
    size: str
    parent_sku: str = ""
    product_name: str = ""
    product_id: int | None = None
    variation_id: int | None = None
    src_qty: int | None = None
    woo_qty: int | None = None
    qty_delta: int | None = None
    src_status: str = ""
    woo_status: str = ""
    manages_stock: bool = False
    match_method: str = ""
    action: str = ""
    note: str = ""
    source_ref: str = ""

    def as_list(self):
        return [
            self.status, self.source, self.category, self.source_product, self.size,
            self.parent_sku, self.product_name, self.variation_id if self.variation_id else "",
            "" if self.src_qty is None else self.src_qty,
            "" if self.woo_qty is None else self.woo_qty,
            "" if self.qty_delta is None else self.qty_delta,
            STATUS_LABEL.get(self.src_status, self.src_status),
            STATUS_LABEL.get(self.woo_status, self.woo_status),
            "是" if self.manages_stock else "否",
            self.match_method, self.action, self.note,
        ]


def _payload_for(cfg_sync, diff_row, variation) -> dict:
    """构造要 PUT 给 WooCommerce 的 payload。

    来源有数量 -> 直接写数量；
    来源只有「有货/缺货」但网店变体管理库存 -> 按 ``sync.no_qty_policy`` 处理：
        ``status_and_zero``（默认）：判缺货时把数量一起置 0，判有货时只改状态；
        ``status``：只改状态，数量原样不动。
    """
    mode = cfg_sync.get("mode", "auto")
    policy = cfg_sync.get("no_qty_policy", "status_and_zero")
    payload: dict = {}
    manages = bool(variation.get("manage_stock"))
    if mode == "status":
        manages = False
    elif mode == "quantity":
        manages = True

    if manages:
        payload["manage_stock"] = True
        if diff_row.src_qty is not None:
            payload["stock_quantity"] = int(diff_row.src_qty)
        elif policy == "status_and_zero" and diff_row.src_status == "outofstock":
            payload["stock_quantity"] = 0
    if cfg_sync.get("update_status", True):
        payload["stock_status"] = diff_row.src_status
    return payload


def build_diff(rows, catalog, cfg, *, verbose=False) -> list[DiffRow]:
    index = build_index(catalog)
    mapping = load_mapping(cfg["_mapping_path"])
    threshold = float(cfg.get("options", {}).get("fuzzy_threshold", 0.86))
    allow_combo = bool(cfg.get("options", {}).get("include_combo_skus", False))
    sync_cfg = cfg.get("sync", {})

    out: list[DiffRow] = []
    keys = occurrence_keys(rows)
    for row, pkey in zip(rows, keys):
        rule = {}
        for _k in ((row.source, row.category, pkey),
                   ("*", row.category, pkey),
                   (row.source, "*", pkey),
                   ("*", "*", pkey),
                   (row.source, row.category, row.source_product),
                   ("*", "*", row.source_product)):
            if _k in mapping:
                rule = mapping[_k]
                break
        size_map = parse_size_map(rule.get("size_map", ""))
        pid, method, _ = match_product(row, mapping, index, catalog, threshold, pkey,
                                       allow_combo=allow_combo)

        d = DiffRow(
            status=S_UNMAPPED, source=row.source, category=row.category,
            source_product=row.source_product, size=row.size,
            src_qty=row.quantity, src_status=row.availability,
            match_method=method, source_ref=row.source_ref,
        )
        if not pid:
            d.status = S_NO_PRODUCT if method.startswith("映射") else S_UNMAPPED
            d.action = "需要人工处理"
            if method.startswith("映射"):
                d.note = (f"product_map.csv 里指定的 parent_sku「{method.split('「')[-1] if '「' in method else ''}」"
                          f"在店里不存在，请核对货号") if "不存在" in method else method
            else:
                d.note = ("本店没有找到对应商品。原因通常是：①本店还没上架这个品牌/款式；"
                          "②名称或货号与来源不同。可在 config/product_map.csv 里补 parent_sku，"
                          "或先在 WooCommerce 里建好商品再重跑 diff。")
            out.append(d)
            continue

        prod = index["by_id"][pid]
        d.product_id = pid
        d.parent_sku = prod.get("sku") or ""
        d.product_name = prod.get("name") or ""

        variation = find_variation(catalog, pid, row.size, size_map)
        if not variation:
            d.status = S_NO_VARIATION
            d.action = "需要人工处理"
            d.note = "本店该商品下没有这个尺码的变体"
            out.append(d)
            continue

        d.variation_id = variation.get("id")
        d.manages_stock = bool(variation.get("manage_stock"))
        d.woo_qty = variation.get("stock_quantity")
        d.woo_status = variation.get("stock_status") or ""

        mode = sync_cfg.get("mode", "auto")
        # 来源只标「有货」，但本店这个变体管理库存、数量却是 0（或没填）：
        # 我们无法凭空决定该填多少数量，交给人工处理，避免把网店改成「有货但 0 件」。
        if (mode == "auto" and d.src_qty is None and d.manages_stock
                and d.src_status == "instock" and d.woo_status != "instock"
                and (d.woo_qty in (None, 0))):
            d.status = S_NEED_QTY
            d.action = "需要人工处理"
            d.note = ("来源（货盘）标了「有货」，但本店这个变体开着「管理库存」且数量为 0。"
                      "工具不会凭空猜数量：请人工在网店填上实际数量，"
                      "或把 config.yaml 的 sync.mode 改成 status 后重跑。")
            out.append(d)
            continue
        if mode == "quantity":
            compare_qty = True
        elif mode == "status":
            compare_qty = False
        else:
            compare_qty = d.manages_stock

        qty_same = True
        if compare_qty and d.src_qty is not None and d.woo_qty is not None:
            d.qty_delta = int(d.src_qty) - int(d.woo_qty)
            qty_same = d.qty_delta == 0
        elif compare_qty and d.src_qty is not None and d.woo_qty is None:
            d.qty_delta = None
            qty_same = False

        status_same = (not sync_cfg.get("update_status", True)) or (d.src_status == d.woo_status)

        if qty_same and status_same:
            d.status = S_SAME
            d.action = "无需更新"
            if compare_qty:
                d.note = "数量与状态都一致"
            else:
                d.note = "库存状态一致（本店该变体不管理具体数量）"
            out.append(d)
            continue

        d.status = S_CHANGE
        payload = _payload_for(sync_cfg, d, variation)
        if d.src_qty is None and "stock_quantity" not in payload and compare_qty:
            d.note = "来源只提供「有货/缺货」（没有数量），本次只同步状态，不改动库存数字"
        elif d.src_qty is None and not compare_qty:
            d.note = "来源只提供「有货/缺货」，且本店该变体不管理具体数量"
        pieces = []
        if "stock_quantity" in payload:
            pieces.append(f"数量 {d.woo_qty} → {payload['stock_quantity']}")
        if "stock_status" in payload:
            pieces.append(
                f"状态 {STATUS_LABEL.get(d.woo_status, d.woo_status)} → "
                f"{STATUS_LABEL.get(payload['stock_status'], payload['stock_status'])}")
        if not pieces:
            pieces.append("（无字段需要更新）")
        d.action = "；".join(pieces)
        out.append(d)
    return out


def summarize(diffs: list[DiffRow]) -> dict:
    s = {"total": len(diffs), S_CHANGE: 0, S_SAME: 0, S_NO_PRODUCT: 0,
         S_NO_VARIATION: 0, S_UNMAPPED: 0, S_NEED_QTY: 0,
         "products": set(), "products_change": set()}
    for d in diffs:
        s[d.status] = s.get(d.status, 0) + 1
        if d.product_id:
            s["products"].add(d.product_id)
        if d.status == S_CHANGE:
            s["products_change"].add(d.product_id or d.source_product)
    s["products"] = len(s["products"])
    s["products_change"] = len(s["products_change"])
    return s
