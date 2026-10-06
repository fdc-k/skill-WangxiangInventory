"""跨平台运行时探测。

这一层负责回答三个问题，而且要在 macOS / Windows / Linux 上都能答对：

1. 现在跑的是不是够新的 Python？（>= 3.10）
2. 项目自带的虚拟环境 ``.venv`` 里的 Python 在哪？
   - POSIX：``.venv/bin/python``
   - Windows：``.venv\\Scripts\\python.exe``
3. 要建虚拟环境时，用哪个 Python 最省事？
   - 优先用 WorkBuddy 自带的 Python（用户什么都不用装）
   - 其次用当前正在跑的 Python
   - 最后去 PATH 上找 python3 / python / py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

MIN_PYTHON = (3, 10)
ROOT = Path(__file__).resolve().parent.parent
VENV_DIR = ROOT / ".venv"


# ---------------------------------------------------------------- 平台判断

def is_windows() -> bool:
    return os.name == "nt"


def venv_dir(root: Path | None = None) -> Path:
    return (root or ROOT) / ".venv"


def venv_python(root: Path | None = None) -> Path:
    """虚拟环境里 Python 可执行文件的路径（会自动判断 bin 还是 Scripts）。"""
    v = venv_dir(root)
    if is_windows():
        for name in ("python.exe", "python3.exe"):
            p = v / "Scripts" / name
            if p.exists():
                return p
        return v / "Scripts" / "python.exe"
    for name in ("python3", "python"):
        p = v / "bin" / name
        if p.exists():
            return p
    return v / "bin" / "python3"


def venv_script(name: str, root: Path | None = None) -> Path:
    """虚拟环境里某个命令行脚本的路径（Windows 会自动补 .exe）。"""
    v = venv_dir(root)
    if is_windows():
        return v / "Scripts" / f"{name}.exe"
    return v / "bin" / name


def venv_ready(root: Path | None = None) -> bool:
    return venv_python(root).exists()


# ---------------------------------------------------------------- Python 探测

def python_version_of(exe: str | Path) -> tuple[int, ...] | None:
    """取某个解释器的版本号；跑不起来就返回 None。"""
    import subprocess

    try:
        out = subprocess.run(
            [str(exe), "-c", "import sys;print('%d.%d.%d' % sys.version_info[:3])"],
            capture_output=True, text=True, timeout=30,
        )
        if out.returncode != 0:
            return None
        return tuple(int(x) for x in out.stdout.strip().split("."))
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def version_ok(v: tuple[int, ...] | None) -> bool:
    return bool(v) and v[:2] >= MIN_PYTHON


def workbuddy_python() -> Path | None:
    """找 WorkBuddy 自带的 Python。

    WorkBuddy 把所有托管运行时记在
    ``~/.workbuddy/binaries/.cache/registry.json`` 里，
    里面 ``binaries.python.<版本>.executablePath`` 就是解释器路径。
    找不到注册表就退回到扫描 ``versions/*/bin|python.exe``。
    """
    home = Path(os.environ.get("USERPROFILE") or Path.home())
    base = home / ".workbuddy" / "binaries" / "python"
    if not base.exists():
        return None

    reg = base / ".cache" / "registry.json"
    if reg.exists():
        try:
            data = json.loads(reg.read_text(encoding="utf-8"))
            entries = (data.get("binaries") or {}).get("python") or {}
            cands = []
            for ver, info in entries.items():
                exe = info.get("executablePath")
                if exe and Path(exe).exists():
                    cands.append((ver, Path(exe)))
            if cands:
                cands.sort(key=lambda x: _ver_key(x[0]), reverse=True)
                return cands[0][1]
        except (json.JSONDecodeError, OSError, AttributeError):
            pass

    # 退化方案：直接扫目录
    versions = base / "versions"
    if versions.is_dir():
        found = []
        for d in versions.iterdir():
            if not d.is_dir() or d.name.startswith("."):
                continue
            for rel in ("bin/python3", "bin/python", "python.exe", "Scripts/python.exe"):
                p = d / rel
                if p.exists():
                    found.append((d.name, p))
                    break
        if found:
            found.sort(key=lambda x: _ver_key(x[0]), reverse=True)
            return found[0][1]
    return None


def _ver_key(v: str):
    try:
        return tuple(int(x) for x in str(v).split(".")[:3])
    except ValueError:
        return (0,)


def find_bootstrap_python() -> list[tuple[str, str]]:
    """返回「可以用来创建 .venv 的解释器」候选列表，按推荐程度排序。

    每项是 ``(说明, 可执行文件路径)``。
    """
    out: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(label: str, exe) -> None:
        if not exe:
            return
        key = str(exe)
        if key in seen:
            return
        seen.add(key)
        out.append((label, key))

    wb = workbuddy_python()
    if wb and version_ok(python_version_of(wb)):
        add("WorkBuddy 自带 Python", wb)

    if version_ok(tuple(sys.version_info[:3])):
        add("当前运行的 Python", sys.executable)

    for name in ("python3", "python"):
        exe = shutil.which(name)
        if exe and version_ok(python_version_of(exe)):
            add(f"系统 PATH 上的 {name}", exe)

    for exe in (shutil.which("py"),):
        if exe:
            add("Windows 的 py 启动器", exe)

    return out


def describe_environment() -> dict:
    """给 check / selftest 用的环境快照。"""
    wb = workbuddy_python()
    return {
        "系统": "Windows" if is_windows() else ("macOS" if sys.platform == "darwin" else sys.platform),
        "当前 Python": sys.executable,
        "Python 版本": "%d.%d.%d" % sys.version_info[:3],
        "运行位置": "WorkBuddy 自带 Python" if wb and Path(sys.executable) == wb else "其它 Python",
        "WorkBuddy Python": str(wb) if wb else "（没找到）",
        "项目目录": str(ROOT),
        "虚拟环境": str(VENV_DIR) + ("（已就绪）" if venv_ready() else "（还没建）"),
        "虚拟环境 Python": str(venv_python()),
        "控制台编码": (getattr(sys.stdout, "encoding", None) or "?"),
    }
