"""生成差异报表（彩色 Excel + 文本预览 + Markdown）。"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .matching import nearest_sku

from .diff import (DIFF_COLUMNS, S_CHANGE, S_NEED_QTY, S_NO_PRODUCT, S_NO_VARIATION,
                   S_SAME, S_UNMAPPED, STATUS_LABEL, summarize)

FILL_HEAD = PatternFill("solid", fgColor="1F3864")
FILL_DIFF = PatternFill("solid", fgColor="FFC7CE")     # 红：有差异
FILL_DIFF_STRONG = PatternFill("solid", fgColor="FF7C80")
FILL_WARN = PatternFill("solid", fgColor="FFEB9C")     # 黄：需人工处理
FILL_SAME = PatternFill("solid", fgColor="E2EFDA")     # 绿：一致
FILL_SUB = PatternFill("solid", fgColor="DDEBF7")
FONT_HEAD = Font(color="FFFFFF", bold=True)
FONT_DIFF = Font(color="9C0006", bold=True)
FONT_WARN = Font(color="9C6500")
FONT_TITLE = Font(bold=True, size=13)
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

COL_WIDTH = [10, 10, 16, 34, 8, 20, 32, 10, 9, 9, 8, 12, 12, 16, 14, 30, 42]


def _style_header(ws, ncol):
    for c in range(1, ncol + 1):
        cell = ws.cell(row=1, column=c)
        cell.fill = FILL_HEAD
        cell.font = FONT_HEAD
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER
        ws.column_dimensions[get_column_letter(c)].width = COL_WIDTH[c - 1]
    ws.freeze_panes = "A2"


def _write_rows(ws, diffs, row_fill_switch):
    for d in diffs:
        ws.append(d.as_list())
        r = ws.max_row
        fill = row_fill_switch(d)
        for c in range(1, len(DIFF_COLUMNS) + 1):
            cell = ws.cell(row=r, column=c)
            cell.border = BORDER
            cell.alignment = Alignment(vertical="center", wrap_text=(c in (4, 7, 16, 17)))
            if fill is not None:
                cell.fill = fill
        # 差异单元格单独加深：数量列 9/10/11，状态列 12/13
        if d.status == S_CHANGE:
            for c in (9, 10, 11):
                if d.qty_delta not in (None, 0):
                    ws.cell(row=r, column=c).fill = FILL_DIFF_STRONG
                    ws.cell(row=r, column=c).font = FONT_DIFF
            if d.src_status != d.woo_status:
                for c in (12, 13):
                    ws.cell(row=r, column=c).fill = FILL_DIFF_STRONG
                    ws.cell(row=r, column=c).font = FONT_DIFF
            ws.cell(row=r, column=16).font = FONT_DIFF


def write_report_xlsx(diffs, path, meta: dict | None = None, index=None, catalog=None):
    """输出彩色差异报表。

    工作表：
      * 差异明细 — 所有「有差异」的行（红底，变化单元格加深）
      * 无差异   — 与线上完全一致的行（绿底）
      * 需人工处理 — 本店缺商品 / 缺尺码 / 未匹配（黄底）
      * 汇总     — 统计数字
    """
    path = Path(path)
    wb = Workbook()
    summary = summarize(diffs)

    ws = wb.active
    ws.title = "差异明细"
    ws.append(DIFF_COLUMNS)
    _style_header(ws, len(DIFF_COLUMNS))
    _write_rows(ws, [d for d in diffs if d.status == S_CHANGE], lambda d: FILL_DIFF)

    ws2 = wb.create_sheet("无差异")
    ws2.append(DIFF_COLUMNS)
    _style_header(ws2, len(DIFF_COLUMNS))
    _write_rows(ws2, [d for d in diffs if d.status == S_SAME], lambda d: FILL_SAME)

    ws3 = wb.create_sheet("需人工处理")
    ws3.append(DIFF_COLUMNS)
    _style_header(ws3, len(DIFF_COLUMNS))
    _write_rows(ws3, [d for d in diffs
                      if d.status in (S_NO_PRODUCT, S_NO_VARIATION, S_UNMAPPED, S_NEED_QTY)],
                lambda d: FILL_WARN)

    # 需人工处理 —— 按商品（而不是按尺码）汇总一份，方便逐条处理
    ws3b = wb.create_sheet("待处理商品清单")
    head2 = ["来源", "分区/品类", "来源商品/货号", "尺码范围", "尺码数",
             "近似货号建议（本店）", "建议商品名", "处理建议"]
    ws3b.append(head2)
    for c in range(1, len(head2) + 1):
        cell = ws3b.cell(row=1, column=c)
        cell.fill = FILL_HEAD
        cell.font = FONT_HEAD
        cell.alignment = Alignment(horizontal="center")
    for i, w in enumerate([10, 22, 34, 26, 8, 34, 40, 50], 1):
        ws3b.column_dimensions[get_column_letter(i)].width = w
    grouped = {}
    for d in diffs:
        if d.status in (S_NO_PRODUCT, S_NO_VARIATION, S_UNMAPPED, S_NEED_QTY):
            key = (d.source, d.category, d.source_product)
            g = grouped.setdefault(key, {"sizes": [], "note": d.note})
            g["sizes"].append(d.size)
    for (src, cat, prod), g in grouped.items():
        near_sku, near_name = "", ""
        if index is not None and catalog is not None and prod:
            # 只有「本店没有这个商品」类才给近似建议；重名商品带 #1/#2 后缀，先去掉
            base = prod.split("#")[0]
            if base and not base.startswith("ALO") and not base.startswith("ALO "):
                cands = nearest_sku(base, index, catalog, limit=1)
                if cands:
                    c0 = cands[0]
                    mark = "（组合款）" if c0.get("combo") else ""
                    near_sku = f'{c0["sku"]}{mark}'
                    near_name = c0["name"]
        ws3b.append([src, cat, prod, "、".join(g["sizes"]), len(g["sizes"]),
                     near_sku, near_name, g["note"]])
        for c in range(1, len(head2) + 1):
            ws3b.cell(row=ws3b.max_row, column=c).fill = FILL_WARN
        if near_sku:
            ws3b.cell(row=ws3b.max_row, column=6).fill = FILL_SUB
            ws3b.cell(row=ws3b.max_row, column=6).font = Font(bold=True, color="1F3864")
    ws3b.freeze_panes = "A2"

    ws4 = wb.create_sheet("汇总")
    ws4.column_dimensions["A"].width = 26
    ws4.column_dimensions["B"].width = 52
    ws4["A1"] = "库存差异比对汇总"
    ws4["A1"].font = FONT_TITLE
    rows = [
        ("生成时间", (meta or {}).get("generated_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))),
        ("店铺", (meta or {}).get("store", "")),
        ("来源文件", (meta or {}).get("sources", "")),
        ("比对总行数", summary["total"]),
        ("有差异（待更新）", summary[S_CHANGE]),
        ("一致（无需更新）", summary[S_SAME]),
        ("本店无此商品", summary[S_NO_PRODUCT]),
        ("本店无此尺码", summary[S_NO_VARIATION]),
        ("未能匹配", summary[S_UNMAPPED]),
        ("需人工填数量", summary[S_NEED_QTY]),
        ("涉及商品数", summary["products"]),
        ("涉及需要更新的商品数", summary["products_change"]),
    ]
    for i, (k, v) in enumerate(rows, start=3):
        ws4.cell(row=i, column=1, value=k).fill = FILL_SUB
        ws4.cell(row=i, column=1).font = Font(bold=True)
        ws4.cell(row=i, column=2, value=v)
    wb.save(path)
    return path


def console_preview(diffs, limit: int = 25):
    """给聊天窗口用的纯文本预览。"""
    changes = [d for d in diffs if d.status == S_CHANGE]
    sames = [d for d in diffs if d.status == S_SAME]
    manual = [d for d in diffs
              if d.status in (S_NO_PRODUCT, S_NO_VARIATION, S_UNMAPPED, S_NEED_QTY)]
    lines = []
    lines.append(f"有差异 {len(changes)} 行 | 一致 {len(sames)} 行 | 需人工处理 {len(manual)} 行")
    if manual:
        grouped = {}
        for d in manual:
            grouped.setdefault((d.source, d.category, d.source_product), []).append(d.size)
        lines.append("")
        lines.append(f"【需人工处理：{len(grouped)} 个商品（本店找不到对应商品或尺码）】")
        for (src, cat, prod), sizes in list(grouped.items())[:12]:
            lines.append(f"  - [{src}] {cat or '-'} | {prod}  （{len(sizes)} 个尺码）")
        if len(grouped) > 12:
            lines.append(f"  …… 其余 {len(grouped) - 12} 个商品见 Excel「待处理商品清单」")
    if changes:
        lines.append("")
        lines.append("【有差异（前 %d 行）】" % min(limit, len(changes)))
        lines.append(f"{'来源商品':<28}{'尺码':<6}{'本店SKU':<20}{'来源':<6}{'在线':<6}{'变化'}")
        for d in changes[:limit]:
            sq = "-" if d.src_qty is None else d.src_qty
            wq = "-" if d.woo_qty is None else d.woo_qty
            lines.append(f"{d.source_product[:26]:<28}{d.size:<6}{(d.parent_sku or '-')[:18]:<20}"
                         f"{str(sq):<6}{str(wq):<6}"
                         f"{STATUS_LABEL.get(d.src_status,d.src_status)} / "
                         f"{STATUS_LABEL.get(d.woo_status,d.woo_status)}")
        if len(changes) > limit:
            lines.append(f"…… 其余 {len(changes) - limit} 行见 Excel 报表")
    return "\n".join(lines)


def write_markdown(diffs, path, meta: dict | None = None):
    path = Path(path)
    changes = [d for d in diffs if d.status == S_CHANGE]
    sames = [d for d in diffs if d.status == S_SAME]
    manual = [d for d in diffs
              if d.status in (S_NO_PRODUCT, S_NO_VARIATION, S_UNMAPPED, S_NEED_QTY)]
    L = []
    L.append("# 库存差异比对报告\n")
    if meta:
        L.append(f"- 生成时间：{meta.get('generated_at','')}")
        L.append(f"- 店铺：{meta.get('store','')}")
        L.append(f"- 来源：{meta.get('sources','')}\n")
    L.append(f"- 有差异：**{len(changes)}** 行")
    L.append(f"- 一致：{len(sames)} 行")
    L.append(f"- 需人工处理：{len(manual)} 行\n")

    def table(rows, show_ignored=False):
        L.append("| 来源商品 | 尺码 | 本店 SKU | 本店商品 | 来源数量 | 在线数量 | 来源状态 | 在线状态 | 将执行的更新 |")
        L.append("|---|---|---|---|---|---|---|---|---|")
        for d in rows:
            L.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                d.source_product, d.size, d.parent_sku or "-", d.product_name or "-",
                "" if d.src_qty is None else d.src_qty,
                "" if d.woo_qty is None else d.woo_qty,
                STATUS_LABEL.get(d.src_status, d.src_status),
                STATUS_LABEL.get(d.woo_status, d.woo_status),
                d.action))
        L.append("")

    if changes:
        L.append("## 一、有差异（按商品汇总）\n")
        L.append("| 来源 | 品类/分区 | 来源商品 | 本店商品（SKU） | 尺寸变化 | 说明 |")
        L.append("|---|---|---|---|---|---|")
        grouped = {}
        for d in changes:
            key = (d.source, d.category, d.source_product, d.parent_sku, d.product_name)
            grouped.setdefault(key, []).append(d)
        for (src, cat, prod, sku, pname), items in grouped.items():
            bits = []
            for d in items:
                if d.src_qty is not None or d.woo_qty is not None:
                    bits.append(f"{d.size}: {d.woo_qty if d.woo_qty is not None else '-'}"
                                f"→{d.src_qty if d.src_qty is not None else '-'}")
                else:
                    bits.append(f"{d.size}: {STATUS_LABEL.get(d.woo_status, d.woo_status)}"
                                f"→{STATUS_LABEL.get(d.src_status, d.src_status)}")
            L.append(f"| {src} | {cat or '-'} | {prod} | {pname or '-'}（{sku or '-'}） | "
                     f"{'、'.join(bits)} | {items[0].action} |")
        L.append("")
        L.append("## 一之二、有差异（逐条明细）\n")
        table(changes)
    if manual:
        L.append("## 二、需要人工处理\n")
        L.append("| 来源商品 | 尺码 | 状态 | 说明 |")
        L.append("|---|---|---|---|")
        for d in manual:
            L.append(f"| {d.source_product} | {d.size} | {d.status} | {d.note} |")
        L.append("")
    if sames:
        L.append("## 三、无差异（无需更新）\n")
        table(sames)
    path.write_text("\n".join(L), encoding="utf-8")
    return path


# ------------------------------------------------------------------ HTML 报表

_HTML_HEAD = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
 :root {{ --red:#ffc7ce; --red2:#ff7c80; --green:#e2efda; --yellow:#ffeb9c;
          --head:#1f3864; --line:#d0d7e5; }}
 * {{ box-sizing:border-box; }}
 body {{ font-family:"PingFang SC","Microsoft YaHei","Heiti SC","Noto Sans CJK SC",
        "Hiragino Sans GB",sans-serif; margin:0; padding:24px; background:#f6f7fb;
        color:#1b1b1b; }}
 h1 {{ font-size:22px; margin:0 0 6px; }}
 h2 {{ font-size:17px; margin:28px 0 8px; padding-bottom:6px; border-bottom:2px solid var(--line); }}
 .meta {{ color:#666; font-size:13px; margin-bottom:16px; }}
 .cards {{ display:flex; flex-wrap:wrap; gap:10px; margin:16px 0 8px; }}
 .card {{ background:#fff; border:1px solid var(--line); border-radius:10px;
          padding:10px 16px; min-width:130px; }}
 .card b {{ display:block; font-size:22px; }}
 .card span {{ font-size:12px; color:#666; }}
 .legend {{ font-size:13px; color:#444; margin:8px 0 0; }}
 .sw {{ display:inline-block; width:14px; height:14px; border:1px solid #bbb;
        vertical-align:-2px; margin:0 4px 0 12px; border-radius:3px; }}
 table {{ border-collapse:collapse; width:100%; background:#fff; font-size:13px; }}
 th,td {{ border:1px solid var(--line); padding:6px 8px; text-align:left;
          vertical-align:top; }}
 th {{ background:var(--head); color:#fff; position:sticky; top:0; }}
 tr.diff td {{ background:var(--red); }}
 tr.diff td.chg {{ background:var(--red2); font-weight:700; }}
 tr.same td {{ background:var(--green); }}
 tr.manual td {{ background:var(--yellow); }}
 .wrap {{ max-height:640px; overflow:auto; border:1px solid var(--line);
           border-radius:8px; }}
 code {{ background:#eef1f7; padding:1px 5px; border-radius:4px; }}
</style></head><body>
"""


def _html_table(headers, rows, row_class, chg_cols=()):
    out = ['<div class="wrap"><table><thead><tr>']
    out += [f"<th>{h}</th>" for h in headers]
    out.append("</tr></thead><tbody>")
    for r in rows:
        cls = row_class(r[0]) if callable(row_class) else row_class
        out.append(f'<tr class="{cls}">')
        for i, v in enumerate(r):
            extra = ' class="chg"' if i in chg_cols else ""
            out.append(f"<td{extra}>{'' if v is None else v}</td>")
        out.append("</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


def write_report_html(diffs, path, meta: dict | None = None, index=None, catalog=None):
    """输出一个可以直接双击用浏览器打开、带颜色的 HTML 报表。

    相比 Excel 的好处：任何系统都能打开，中文和颜色都不会跑掉。
    """
    from html import escape

    path = Path(path)
    s = summarize(diffs)
    changes = [d for d in diffs if d.status == S_CHANGE]
    sames = [d for d in diffs if d.status == S_SAME]
    manual = [d for d in diffs if d.status in (S_NO_PRODUCT, S_NO_VARIATION, S_UNMAPPED, S_NEED_QTY)]

    head = _HTML_HEAD.format(title=escape("库存差异比对报告"))
    L = [head, "<h1>库存差异比对报告</h1>"]
    if meta:
        L.append(f'<div class="meta">生成时间：{escape(str(meta.get("generated_at","")))}　|　'
                 f'店铺：{escape(str(meta.get("store","")))}　|　'
                 f'来源：{escape(str(meta.get("sources","")))}</div>')
    L.append('<div class="cards">'
             f'<div class="card"><b style="color:#c00">{len(changes)}</b><span>有差异（待更新）</span></div>'
             f'<div class="card"><b style="color:#2a7">{len(sames)}</b><span>一致（无需更新）</span></div>'
             f'<div class="card"><b style="color:#a70">{len(manual)}</b><span>需人工处理</span></div>'
             '</div>')
    L.append('<div class="legend">颜色说明：'
             '<span class="sw" style="background:#ffc7ce"></span>有差异'
             '<span class="sw" style="background:#ff7c80"></span>具体变化的单元格'
             '<span class="sw" style="background:#e2efda"></span>一致'
             '<span class="sw" style="background:#ffeb9c"></span>需人工处理</div>')

    def esc(v):
        return escape("" if v is None else str(v))

    if changes:
        L.append(f'<h2>一、有差异（{len(changes)} 条，需要更新）</h2>')
        rows = [[esc(v) for v in d.as_list()] for d in changes]
        L.append(_html_table(DIFF_COLUMNS, rows, "diff", chg_cols=(8, 9, 10, 11, 12)))
    if manual:
        # 先给「按商品汇总 + 近似货号建议」，这是一眼能干活的那张表
        grouped = {}
        for d in manual:
            grouped.setdefault((d.source, d.category, d.source_product), []).append(d)
        L.append(f'<h2>二、需人工处理 —— 按商品汇总（{len(grouped)} 个商品）</h2>')
        L.append('<p class="legend">「近似货号建议」是工具在本店找到的最相近货号，'
                 '供你判断是不是同一个商品；确认后填进 <code>config/product_map.csv</code> '
                 '的 <code>parent_sku</code> 再重跑 diff。</p>')
        rows = []
        for (src, cat, prod), items in grouped.items():
            near, near_name = "", ""
            base = str(prod).split("#")[0]
            if index is not None and catalog is not None and base and not base.upper().startswith("ALO"):
                cands = nearest_sku(base, index, catalog, limit=1)
                if cands:
                    c0 = cands[0]
                    near = f'{c0["sku"]}' + ("（组合款）" if c0.get("combo") else "")
                    near_name = c0["name"]
            sizes = "、".join(d.size for d in items)
            rows.append([esc(src), esc(cat or "-"), esc(prod), esc(sizes), esc(len(items)),
                         esc(near or "-"), esc(near_name), esc(items[0].note)])
        L.append(_html_table(["来源", "分区/品类", "来源商品/货号", "尺码", "尺码数",
                              "近似货号建议（本店）", "建议商品名", "处理建议"],
                             rows, "manual"))
        L.append(f'<h2>二之二、需人工处理 —— 逐条明细（{len(manual)} 条）</h2>')
        rows = [[esc(v) for v in d.as_list()] for d in manual]
        L.append(_html_table(DIFF_COLUMNS, rows, "manual"))
    if sames:
        L.append(f'<h2>三、无差异（{len(sames)} 条，无需更新）</h2>')
        rows = [[esc(v) for v in d.as_list()] for d in sames]
        L.append(_html_table(DIFF_COLUMNS, rows, "same"))
    L.append("</body></html>")
    path.write_text("\n".join(L), encoding="utf-8")
    return path
