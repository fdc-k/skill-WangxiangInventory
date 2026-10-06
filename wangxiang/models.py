"""统一的库存数据模型。"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

UNIFIED_COLUMNS = [
    "source",          # 来源标识（例如 SP5 / ALO / PALLET）
    "category",        # 品类/分区（例如 卫衣(hoodie)、裤子(pant)、ALO）
    "source_product",  # 来源文件里的原始商品名（PDF 里常是 SKU）
    "size",            # 尺码
    "quantity",        # 数量（来源没有数量时为空）
    "availability",    # instock / outofstock
    "source_ref",      # 来源位置（行号 / 货盘格），便于回溯
]


@dataclass
class InventoryRow:
    """统一格式的一行库存（= 一个「商品 × 尺码」变体）。"""

    source: str
    source_product: str
    size: str
    category: str = ""
    quantity: int | None = None
    availability: str = "instock"
    source_ref: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProductBlock:
    """来源文件中的一个商品块（含多个尺码）。"""

    source: str
    name: str
    rows: list[InventoryRow] = field(default_factory=list)
    ref: str = ""
    extra: dict = field(default_factory=dict)
