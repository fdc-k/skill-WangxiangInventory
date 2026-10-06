"""Excel 库存表 -> 统一库存行。

适配「商品名 / 尺码 / 数量」三列的表格，且允许商品名或尺码使用
Excel 合并单元格（合并区域只在左上角保存值，其余为空）。
本模块会把合并单元格的值向下填充。
"""
from __future__ import annotations

from pathlib import Path

import openpyxl

from .models import InventoryRow, ProductBlock
from .util import availability_from_quantity, col_letter_to_index, normalize_size, to_int


def _build_merge_lookup(ws) -> dict[tuple[int, int], object]:
    lookup: dict[tuple[int, int], object] = {}
    for rng in ws.merged_cells.ranges:
        top_left = ws.cell(row=rng.min_row, column=rng.min_col).value
        if top_left is None:
            continue
        for r in range(rng.min_row, rng.max_row + 1):
            for c in range(rng.min_col, rng.max_col + 1):
                lookup[(r, c)] = top_left
    return lookup


def _cell(ws, lookup, row: int, col: int):
    value = lookup.get((row, col))
    if value is None:
        value = ws.cell(row=row, column=col).value
    return value


def _clean(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def extract_excel(path: str | Path, source_id: str, options: dict) -> tuple[list[InventoryRow], dict]:
    """读取一个 Excel 库存文件，返回 (统一库存行, 统计信息)。

    options:
        sheet            工作表名（默认第一个）
        product_column   商品名列（字母，如 "B"）
        size_column      尺码列
        quantity_column  数量列（可选，缺省表示只关心有无货）
        start_row        数据起始行（默认 1）
        stop_row         数据结束行（默认到最后）
        in_stock_values  数量列里表示「有货」的文本（如 "✅"）
    """
    path = Path(path)
    wb = openpyxl.load_workbook(path, data_only=True)
    sheet_name = options.get("sheet")
    ws = wb[sheet_name] if sheet_name else wb.worksheets[0]

    pcol = col_letter_to_index(options.get("product_column", "B"))
    scol = col_letter_to_index(options.get("size_column", "C"))
    qcol = options.get("quantity_column")
    qcol = col_letter_to_index(qcol) if qcol else None

    start_row = int(options.get("start_row", 1))
    stop_row = int(options.get("stop_row") or ws.max_row)
    in_stock_values = set(options.get("in_stock_values", []))

    lookup = _build_merge_lookup(ws)
    rows: list[InventoryRow] = []
    current_product = ""
    blocks: dict[str, ProductBlock] = {}
    last_key = None

    for r in range(start_row, stop_row + 1):
        raw_product = _cell(ws, lookup, r, pcol)
        raw_size = _cell(ws, lookup, r, scol)
        if raw_product not in (None, ""):
            current_product = _clean(raw_product)
        size = normalize_size(raw_size)
        if not size:
            continue
        # 合并单元格会让同一个「商品 × 尺码」在连续多行里重复出现，只保留第一条
        key = (current_product, size)
        if key == last_key:
            continue
        last_key = key
        if qcol:
            raw_qty = _cell(ws, lookup, r, qcol)
            qty_text = _clean(raw_qty)
            quantity = to_int(raw_qty)
            if quantity is not None:
                availability = availability_from_quantity(quantity)
            elif qty_text and in_stock_values and qty_text in in_stock_values:
                availability = "instock"
            elif qty_text:
                availability = "instock"
            else:
                availability = "outofstock"
        else:
            raw_qty = _cell(ws, lookup, r, qcol) if qcol else None
            quantity = None
            availability = "instock"

        row = InventoryRow(
            source=source_id,
            source_product=current_product,
            size=size,
            quantity=quantity,
            availability=availability,
            source_ref=f"{path.name}!{ws.title}!R{r}",
        )
        rows.append(row)
        block = blocks.setdefault(
            current_product,
            ProductBlock(source=source_id, name=current_product, ref=path.name),
        )
        block.rows.append(row)

    stats = {
        "source": source_id,
        "file": str(path),
        "sheet": ws.title,
        "rows": len(rows),
        "products": len(blocks),
    }
    wb.close()
    return rows, stats
