"""控制台兼容层：让中文和符号在 Windows / macOS / Linux 上都能正常显示。

Windows 的 cmd / PowerShell 默认代码页常常是 GBK(cp936)，直接 print
中文或 ✅ ⚠ ❌ 会抛 ``UnicodeEncodeError`` 把程序打断。这里做两件事：

1. 把控制台切到 UTF-8（Windows 上顺便调 SetConsoleOutputCP）；
2. 提供一个「符号表」：如果当前编码实在输出不了 ✅，就退化成 [OK] 这种纯文本。
"""
from __future__ import annotations

import sys

_UNICODE_SYMBOLS = {"ok": "✅", "warn": "⚠️ ", "err": "❌", "dot": "·", "arrow": "→"}
_ASCII_SYMBOLS = {"ok": "[OK]", "warn": "[!] ", "err": "[x]", "dot": ".", "arrow": "->"}

S = dict(_ASCII_SYMBOLS)      # 默认先用纯文本，setup() 之后再按情况换成符号
_configured = False


def _can_encode(text: str, enc: str | None) -> bool:
    if not enc:
        return False
    try:
        text.encode(enc)
        return True
    except (UnicodeEncodeError, LookupError):
        return False


def _force_utf8_console() -> None:
    """Windows：把控制台输出代码页切成 UTF-8。"""
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32          # type: ignore[attr-defined]
        kernel32.SetConsoleOutputCP(65001)
        kernel32.SetConsoleCP(65001)
    except Exception:                               # noqa: BLE001 - 非 Windows 会走到这里
        pass


def setup(force_ascii: bool = False) -> None:
    """在 CLI 最开头调用一次。"""
    global S, _configured
    if _configured:
        return

    if sys.platform == "win32":
        _force_utf8_console()

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")   # type: ignore[union-attr]
        except (AttributeError, ValueError, OSError):
            pass

    import os

    if force_ascii or os.environ.get("WANGXIANG_ASCII") in ("1", "true", "yes"):
        S = dict(_ASCII_SYMBOLS)
    else:
        enc = getattr(sys.stdout, "encoding", None)
        probe = "".join(_UNICODE_SYMBOLS.values())
        S = dict(_UNICODE_SYMBOLS) if _can_encode(probe, enc) else dict(_ASCII_SYMBOLS)
    _configured = True


def ok() -> str:
    return S["ok"]


def warn() -> str:
    return S["warn"]


def err() -> str:
    return S["err"]


def arrow() -> str:
    return S["arrow"]
