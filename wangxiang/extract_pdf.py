"""PDF「货盘」清单 -> 统一库存行。

适配版式（本项目 ``demo-inventory/10.5Essentials 货盘.pdf``）：

* 一页超长表格，用**灰色标题条**分成若干分区，例如
  ``卫衣（hoodie）/ 裤子（pant）``、``平脚裤（relaxed）``、``短裤（short）``、
  ``zip up 拉链``、``ALO``、``Stussy``、``Sp5der``、``Kith T-shirt``。
* 每个分区里横向排 1~2 栏（左栏 / 右栏），每栏又是一张竖表。
* 每个商品是表里的一个「行块」，左侧是商品图、中英文名与 SKU，右侧是尺码列；
  尺码右边一格若出现 ✅ / ☑ 表示该尺码**有货**，空白表示**无货**。
* 尺码自上而下递增（XXS…XXL）。解析器靠「尺码序号一旦不再递增就换下一个
  商品」来切块，因此不同分区使用不同尺码集合（5 码 / 6 码 / 7 码）都能自动适应，
  个别尺码标签缺失也不会串行。

产出的每一行都带 ``source_ref``，记录了分区、栏号、块号，方便回溯核对。
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from .models import InventoryRow, ProductBlock
from .util import normalize_size

SIZE_ORDER = ["XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL"]
SIZE_INDEX = {s: i for i, s in enumerate(SIZE_ORDER)}
SIZE_LABELS = set(SIZE_ORDER) | {"2XL", "3XL"}
MARK_CHARS = {"\u2705", "\u00fe", "\u2611", "\u2714", "\u2713", "\u2612", "\u2716", "\u274c"}

# 打勾判断用「渲染出来的像素」而不是文字层：这份 PDF 的文字层里混着
# 白色/被盖住的 ✅ 字符，只有真正画出来的绿色勾才是「有货」。
MARK_RENDER_DPI = 200      # 渲染精度
MARK_GREEN_MIN = 60        # 一个尺码格里至少有多少绿色像素才算打勾
SKU_RE = re.compile(r"^\d{2,3}[A-Za-z]{1,2}-?\d{2}-?\d{4}$")


class MarkMask:
    """把「打勾格」所在的窄条渲染成图片，用绿色像素判断有没有勾。

    PDF 的文字层里可能残留看不见的 ✅（白色字、或者被后来的图形盖住），
    所以必须以**渲染出来的画面**为准。绿色 = 有货。
    """

    def __init__(self, page, x_lo: float, x_hi: float, y_lo: float, y_hi: float, dpi: int):
        import numpy as np

        self.bbox = (x_lo, y_lo, x_hi, y_hi)
        self.dpi = dpi
        image = page.crop(self.bbox).to_image(resolution=dpi).original.convert("RGB")
        arr = np.asarray(image).astype("int16")
        r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
        self.mask = (g > 120) & (g > r + 40) & (g > b + 40)
        self.height, self.width = self.mask.shape

    def _py(self, y_pt: float) -> int:
        return int(round((y_pt - self.bbox[1]) / 72.0 * self.dpi))

    def green_count(self, y_top: float, y_bottom: float) -> int:
        a = max(0, self._py(y_top))
        b = min(self.height, self._py(y_bottom))
        if b <= a:
            return 0
        return int(self.mask[a:b, :].sum())

    def is_marked(self, y_top: float, y_bottom: float, threshold: int = MARK_GREEN_MIN) -> bool:
        return self.green_count(y_top, y_bottom) >= threshold


class PageIndex:
    """缓存一页 PDF 的词 / 字符 / 灰条，避免重复解析。"""

    def __init__(self, page):
        self.page = page
        self.words = page.extract_words(keep_blank_chars=False)
        self.chars = page.chars
        self.marks = [c for c in self.chars if c["text"] in MARK_CHARS]
        self.skus = [w for w in self.words if SKU_RE.match(w["text"].strip())]
        self.bands = self._grey_bands()

    def _grey_bands(self):
        """找出灰色标题条（宽 > 300pt，填充灰度在 0.5~0.92）。"""
        out = []
        for r in self.page.rects:
            if (r["x1"] - r["x0"]) < 300:
                continue
            fill = r.get("non_stroking_color")
            if fill is None:
                continue
            g = fill[0] if isinstance(fill, (list, tuple)) else fill
            if isinstance(g, (int, float)) and 0.5 <= float(g) <= 0.92:
                out.append(r)
        return sorted(out, key=lambda r: (round(r["top"], 1), r["x0"]))

    def band_text(self, band) -> str:
        words = [w for w in self.words
                 if band["top"] - 4 <= w["top"] <= band["bottom"] + 4
                 and band["x0"] - 4 <= w["x0"] <= band["x1"]]
        words.sort(key=lambda w: w["x0"])
        return unicodedata.normalize("NFKC", " ".join(w["text"] for w in words).strip())


def find_sections(pg: PageIndex, default_name="主表") -> list[dict]:
    """把整页切成若干分区。

    返回 list[dict]：``{"name", "top", "bottom", "columns": {index: label}}``。
    """
    rows: list[list] = []
    for b in pg.bands:
        if rows and abs(b["top"] - rows[-1][0]["top"]) <= 6:
            rows[-1].append(b)
        else:
            rows.append([b])

    sections: list[dict] = []
    for i, row in enumerate(rows):
        labels = [pg.band_text(b) for b in row]
        top = row[0]["bottom"]
        bottom = rows[i + 1][0]["top"] if i + 1 < len(rows) else pg.page.height
        if len(row) >= 2:                      # 同一行的多栏标题
            if sections:
                sections[-1]["columns"] = {j: t for j, t in enumerate(labels)}
            else:
                sections.append({"name": default_name, "top": top, "bottom": bottom,
                                 "columns": {j: t for j, t in enumerate(labels)},
                                 "synthetic": False})
        else:
            name = labels[0]
            sections.append({"name": name, "top": top, "bottom": bottom,
                             "columns": {0: name, 1: name}, "synthetic": True})
    if not sections:
        sections.append({"name": default_name, "top": 0, "bottom": pg.page.height,
                         "columns": {0: default_name, 1: default_name},
                         "synthetic": False})
    # 合并被「同一分区里的半宽标题条」拆出来的碎片（x 范围不覆盖整表的条）
    merged: list[dict] = []
    for s in sections:
        if (merged and s["name"] == merged[-1]["name"]):
            merged[-1]["bottom"] = s["bottom"]
            continue
        merged.append(s)
    return merged


def _columns_in(pg: PageIndex, top: float, bottom: float):
    """某一分区里，按 x 聚类出的「尺码列」。"""
    size_words = [
        w for w in pg.words
        if w["text"].strip() in SIZE_LABELS and top <= w["top"] <= bottom
    ]
    if not size_words:
        return []
    groups: list[list] = []
    for w in sorted(size_words, key=lambda w: w["x0"]):
        if groups and abs(w["x0"] - groups[-1][0]["x0"]) <= 15:
            groups[-1].append(w)
        else:
            groups.append([w])
    cols = []
    for ws_ in groups:
        if len(ws_) < 3:
            continue
        x0 = ws_[0]["x0"]
        cols.append({
            "x0": x0,
            "size_words": sorted(ws_, key=lambda w: w["top"]),
            "mask": MarkMask(pg.page, x0 - 10, x0 + 58, top, bottom, MARK_RENDER_DPI),
        })
    return cols


def split_blocks(size_words, max_gap=90.0):
    """按「尺码序号不再递增就换块」把尺码标签切成商品块。"""
    blocks, cur = [], []
    prev_idx, prev_top = -1, None
    for w in size_words:
        label = normalize_size(w["text"])
        idx = SIZE_INDEX.get(label)
        if idx is None:
            continue
        top = w["top"]
        if cur and (idx <= prev_idx or (prev_top is not None and top - prev_top > max_gap)):
            blocks.append(cur)
            cur = []
        cur.append({"size": label, "top": top,
                    "mid": top + (w.get("height") or 10.0) / 2.0})
        prev_idx, prev_top = idx, top
    if cur:
        blocks.append(cur)
    return blocks


def _join(parts):
    """拼接文本：中文之间不加空格。"""
    out = ""
    for t in parts:
        if not out:
            out = t
            continue
        prev, head = out[-1], t[0]
        cjk = lambda ch: "\u2e80" <= ch <= "\u9fff"
        out += t if (cjk(prev) or cjk(head) or prev in "（(［") else " " + t
    return out.strip()


def _text_near(pg: PageIndex, y_top, y_bottom, x_lo, x_hi):
    ws = [w for w in pg.words
          if y_top <= w["top"] <= y_bottom and x_lo <= w["x0"] <= x_hi
          and w["text"].strip() not in SIZE_LABELS
          and w["text"].strip() not in MARK_CHARS
          and not SKU_RE.match(w["text"].strip())]
    ws.sort(key=lambda w: (round(w["top"] / 6), w["x0"]))
    seen, parts = set(), []
    for w in ws:
        key = (round(w["top"]), round(w["x0"]))
        if key in seen:
            continue
        seen.add(key)
        parts.append(w["text"].strip())
    return unicodedata.normalize("NFKC", _join([p for p in parts if p]))


def _identify(pg: PageIndex, col_x, blk_top, blk_bottom):
    """返回 (SKU, 商品名)。有 SKU 用 SKU，没有就用文字名。"""
    def sku_cands(lo, hi):
        return [w for w in pg.skus
                if col_x - 400 <= w["x0"] <= col_x + 40 and lo <= w["top"] <= hi]

    cands = sku_cands(blk_top - 20, blk_bottom + 24) or sku_cands(blk_top - 40, blk_bottom + 40)
    sku = ""
    name = ""
    if cands:
        center = (blk_top + blk_bottom) / 2
        w = min(cands, key=lambda w: abs(w["top"] - center))
        sku = w["text"].strip()
        name = _text_near(pg, w["top"] - 42, w["top"] + 12, w["x0"] - 22, w["x0"] + 90)
    if not name:
        name = _text_near(pg, blk_top - 14, blk_bottom + 14, col_x - 400, col_x - 40)
    return sku, name


def extract_pdf_pallet(path, source_id: str, options: dict, pdf=None):
    """解析货盘 PDF。返回 ``(统一库存行, 统计信息, 商品块列表)``。"""
    import pdfplumber

    path = Path(path)
    page_number = int(options.get("page", 1))
    default_name = options.get("default_section", "主表")
    drop_empty = bool(options.get("drop_unidentified", True))
    section_columns = {str(k): list(v) for k, v in (options.get("section_columns") or {}).items()}

    rows: list[InventoryRow] = []
    blocks: list[ProductBlock] = []

    close = False
    if pdf is None:
        pdf = pdfplumber.open(path)
        close = True
    try:
        page = pdf.pages[page_number - 1]
        pg = PageIndex(page)
        for section in find_sections(pg, default_name):
            cols = _columns_in(pg, section["top"], section["bottom"])
            col_names = section_columns.get(section["name"])
            for ci, col in enumerate(cols):
                if section.get("synthetic"):
                    sub = (col_names[ci] if col_names and ci < len(col_names)
                           else ("左" if ci == 0 else "右"))
                    label = f"{section['name']}｜{sub}"
                else:
                    label = section["columns"].get(ci, section["name"])
                for bi, block in enumerate(split_blocks(col["size_words"])):
                    if len(block) < 3:
                        continue
                    blk_top, blk_bottom = block[0]["top"], block[-1]["top"]
                    sku, name = _identify(pg, col["x0"], blk_top, blk_bottom)
                    if drop_empty and not sku and not name:
                        continue
                    ref = f"{section['name']}|栏{ci + 1}|块{bi + 1}"
                    pb = ProductBlock(
                        source=source_id, name=name or sku, ref=ref,
                        extra={"sku": sku, "category": label, "section": section["name"],
                               "page": page_number},
                    )
                    for i, item in enumerate(block):
                        # 勾画在「尺码文字中心」上下约 ±12pt 的范围里；
                        # 行高约 25pt，取 23pt 宽的窗口可以避免串到相邻尺码
                        mid = item.get("mid", item["top"] + 5.0)
                        lo, hi = mid - 11.5, mid + 11.5
                        marked = col["mask"].is_marked(lo, hi)
                        row = InventoryRow(
                            source=source_id,
                            category=label,
                            source_product=sku or name,
                            size=item["size"],
                            quantity=None,
                            availability="instock" if marked else "outofstock",
                            source_ref=f"{path.name}|{ref}|{item['size']}",
                        )
                        pb.rows.append(row)
                        rows.append(row)
                    blocks.append(pb)
    finally:
        if close:
            pdf.close()

    used = {b.extra.get("sku") for b in blocks if b.extra.get("sku")}
    stats = {
        "source": source_id,
        "file": str(path),
        "sheet": f"page{page_number}",
        "rows": len(rows),
        "products": len(blocks),
        "orphan_skus": sorted({w["text"].strip() for w in pg.skus} - used),
    }
    return rows, stats, blocks


def extract_pdf_skus(path) -> list[str]:
    """只抓 PDF 中出现的所有 SKU（用于排查或生成映射表）。"""
    import pdfplumber

    found: list[str] = []
    with pdfplumber.open(Path(path)) as pdf:
        for page in pdf.pages:
            idx = PageIndex(page)
            for w in idx.skus:
                if w["text"].strip() not in found:
                    found.append(w["text"].strip())
    return found
