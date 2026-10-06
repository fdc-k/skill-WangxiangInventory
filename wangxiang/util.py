"""通用工具函数。"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

# ---------------------------------------------------------------- 文本规范化

_PUNCT = re.compile(r"[\s\u3000_\-/\\|,，.。:：;；'\"“”‘’()（）\[\]【】{}<>、+&*#@!！?？~`^$%°]+")
_ALNUM = re.compile(r"[^0-9A-Za-z]+")
_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


def normalize_sku(value) -> str:
    """把 SKU 规范成可比较的形式：仅保留字母数字并大写。

    ``192SU-22-4410`` -> ``192SU224410``
    """
    if value is None:
        return ""
    s = unicodedata.normalize("NFKC", str(value)).strip()
    return _ALNUM.sub("", s).upper()


def split_sku_field(value) -> list[str]:
    """拆分「一个字段里写了多个 SKU」的情况（组合商品）。

    ``"192BT212050F 130BT212020F"`` -> ``["192BT212050F", "130BT212020F"]``
    """
    if value is None:
        return []
    s = unicodedata.normalize("NFKC", str(value))
    parts = [p for p in re.split(r"[\s,，;；/|]+", s) if p.strip()]
    return parts or [s]


def sku_match_keys(value) -> set[str]:
    """生成一个 SKU 的所有候选比较键（含去掉结尾 F 的版本）。

    WooCommerce 里 Essentials 的父 SKU 常以 ``F`` 结尾（``192SU224410F``），
    而供货商的货盘 PDF 写作 ``192SU-22-4410``。这里同时给出两个键。
    """
    base = normalize_sku(value)
    if not base:
        return set()
    keys = {base}
    if len(base) > 1 and base.endswith("F"):
        keys.add(base[:-1])
    return keys


def normalize_name(value) -> str:
    """把商品名规范成小写、去标点、去空格的比较形式。"""
    if value is None:
        return ""
    s = unicodedata.normalize("NFKC", str(value)).lower()
    s = _PUNCT.sub("", s)
    return s


def name_tokens(value) -> set[str]:
    """把商品名切成词元集合，用于模糊匹配。"""
    if value is None:
        return set()
    s = unicodedata.normalize("NFKC", str(value)).lower()
    tokens = set()
    for chunk in _PUNCT.split(s):
        if chunk:
            tokens.add(chunk)
    # 中文按字切分，帮助中英混排的名字匹配
    for ch in _CJK.findall(s):
        tokens.add(ch)
    return tokens


def normalize_size(value) -> str:
    """尺寸规范化：去掉空格、全角转半角、统一常见别名。"""
    if value is None:
        return ""
    s = unicodedata.normalize("NFKC", str(value)).strip().upper()
    s = s.replace("码", "").replace("号", "").strip()
    alias = {
        "2XL": "XXL", "3XL": "XXXL", "ONE SIZE": "OS", "均码": "OS", "F": "OS",
    }
    return alias.get(s, s)


def raw_size_key(value) -> str:
    """只做全角->半角、去空格、大写；**不做** 2XL->XXL 这类别名映射。

    用于 ``size_map`` 的目标值，避免 ``XXL:2XL`` 被别名规则又改回 ``XXL``。
    """
    if value is None:
        return ""
    return unicodedata.normalize("NFKC", str(value)).strip().upper()


def size_equals(a, b) -> bool:
    """两个尺码是否算同一个：先按标准别名比，再按原始写法比。"""
    if normalize_size(a) == normalize_size(b):
        return True
    return raw_size_key(a) == raw_size_key(b)


def availability_from_quantity(qty) -> str:
    """由数量推导库存状态。"""
    if qty is None or qty == "":
        return "instock"
    try:
        return "instock" if float(qty) > 0 else "outofstock"
    except (TypeError, ValueError):
        return "instock"


def levenshtein(a: str, b: str) -> int:
    """编辑距离（用于「货号打错/少一位」的近似匹配）。"""
    a, b = str(a), str(b)
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def digits_of(value) -> str:
    """取出字符串里的数字，用于判断两个货号是不是「同一款」。"""
    return "".join(ch for ch in normalize_sku(value) if ch.isdigit())


def to_int(value):
    """尽量转成 int，失败返回 None。"""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int,)):
        return value
    if isinstance(value, float):
        return int(value)
    s = str(value).strip().replace(",", "")
    if not s:
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


# ---------------------------------------------------------------- 路径 / 输出

def ensure_dir(path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def col_letter_to_index(letter: str) -> int:
    """Excel 列号：``A`` -> 1，``AA`` -> 27。"""
    letter = str(letter).strip().upper()
    n = 0
    for ch in letter:
        if not ("A" <= ch <= "Z"):
            raise ValueError(f"非法列名: {letter!r}")
        n = n * 26 + (ord(ch) - 64)
    return n
