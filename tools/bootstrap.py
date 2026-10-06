#!/usr/bin/env python3
"""一键安装 / 修复运行环境（Windows / macOS / Linux 通用）。

这个脚本刻意**只用 Python 标准库**，因为它在依赖装好之前就要能跑。

它做这些事：
  1. 找一个人能用的 Python（优先 WorkBuddy 自带的，其次你电脑上的）
  2. 在项目目录里建一个独立环境 .venv（已有就跳过）
  3. 把需要的库装进 .venv
  4. 在 .venv 里放一个方便的 wangxiang 命令
  5. 没有配置文件就从模板复制一份
  6. 打印接下来该做什么（大白话）

用法（在本项目目录下）：
    python tools/bootstrap.py            # macOS / Linux 常见写法
    py -3 tools\\bootstrap.py            # Windows 常见写法
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV = ROOT / ".venv"
MIN = (3, 10)          # 能跑的最低版本
BEST = "3.12"          # 实测最顺的版本（WorkBuddy 自带 3.13，正合适）


# ---------------------------------------------------------------- 小工具

def say(msg=""):
    print(msg, flush=True)


def title(msg):
    line = "=" * 58
    say()
    say(line)
    say(f" {msg}")
    say(line)


def run(cmd, **kw):
    """跑一个命令，顺便把它的输出原样透出来（方便看进度）。"""
    say("  $ " + " ".join(str(c) for c in cmd))
    return subprocess.run([str(c) for c in cmd], **kw)


def python_of(venv: Path) -> Path:
    if os.name == "nt":
        p = venv / "Scripts" / "python.exe"
        return p if p.exists() else venv / "Scripts" / "python3.exe"
    p = venv / "bin" / "python3"
    return p if p.exists() else venv / "bin" / "python"


def version_of(exe) -> tuple[int, ...] | None:
    try:
        out = subprocess.run([str(exe), "-c",
                              "import sys;print('%d.%d.%d'%sys.version_info[:3])"],
                             capture_output=True, text=True, timeout=30)
        if out.returncode != 0:
            return None
        return tuple(int(x) for x in out.stdout.strip().split("."))
    except Exception:  # noqa: BLE001
        return None


def ver_ok(v) -> bool:
    return bool(v) and v[:2] >= MIN


def workbuddy_python() -> Path | None:
    """WorkBuddy 自带的 Python（它把所有托管的运行时记在 registry.json）。"""
    home = Path(os.environ.get("USERPROFILE") or Path.home())
    base = home / ".workbuddy" / "binaries" / "python"
    if not base.exists():
        return None
    reg = base / ".cache" / "registry.json"
    if reg.exists():
        try:
            import json

            data = json.loads(reg.read_text(encoding="utf-8"))
            entries = (data.get("binaries") or {}).get("python") or {}
            good = [(str(v), Path(i["executablePath"]))
                    for v, i in entries.items()
                    if i.get("executablePath") and Path(i["executablePath"]).exists()]
            if good:
                good.sort(key=lambda x: [int(n) for n in x[0].split(".")[:3]
                                         if n.isdigit()], reverse=True)
                return good[0][1]
        except Exception:  # noqa: BLE001
            pass
    versions = base / "versions"
    if versions.is_dir():
        found = []
        for d in sorted(versions.iterdir(), reverse=True):
            if not d.is_dir() or d.name.startswith("."):
                continue
            for rel in ("bin/python3", "bin/python", "python.exe", "Scripts/python.exe"):
                if (d / rel).exists():
                    found.append(d / rel)
                    break
        if found:
            return found[0]
    return None


def find_python() -> tuple[str, Path] | None:
    """按「最省事」的顺序找一个够新的 Python。"""
    if ver_ok(tuple(sys.version_info[:3])):
        return "当前正在运行的 Python", Path(sys.executable)

    wb = workbuddy_python()
    if wb and ver_ok(version_of(wb)):
        return "WorkBuddy 自带的 Python", wb

    for name in ("python3", "python", "py"):
        exe = shutil.which(name)
        if exe and ver_ok(version_of(exe)):
            return f"系统里的 {name}", Path(exe)
    return None


# ---------------------------------------------------------------- 主流程

def main() -> int:
    title("祥旺库存工具 —— 安装 / 修复运行环境")
    say(f"项目目录：{ROOT}")
    say(f"操作系统：{'Windows' if os.name == 'nt' else sys.platform}")

    # 1. 找一个可用的 Python
    say()
    say("[第 1 步 / 共 5 步] 找 Python")
    found = find_python()
    if not found:
        say("  [x] 没有找到 Python 3.10 或更新的版本。")
        say()
        say("  怎么解决：")
        say("    • 如果你用的是 WorkBuddy：先打开一次 WorkBuddy，再回来重跑本脚本；")
        say("    • 否则去 https://www.python.org/downloads/ 下载安装，")
        say("      安装时记得勾选「Add Python to PATH」。")
        return 2
    label, py = found
    say(f"  [OK] 用这个：{label}")
    say(f"    {py}  （版本 {'%d.%d.%d' % version_of(py)}）")

    # 2. 建虚拟环境
    say()
    say("[第 2 步 / 共 5 步] 创建独立运行环境 .venv")
    if python_of(VENV).exists():
        say("  已经存在，跳过。")
    else:
        r = run([py, "-m", "venv", str(VENV)])
        if r.returncode != 0 or not python_of(VENV).exists():
            say("  [x] 创建失败。")
            say("  提示：有些 Linux 需要先装 python3-venv（sudo apt install python3-venv）。")
            return 3
        say("  [OK] 创建好了。")
    vpy = python_of(VENV)

    # 3. 装依赖
    say()
    say("[第 3 步 / 共 5 步] 安装需要的库（第一次要联网，通常 1~3 分钟）")
    run([vpy, "-m", "pip", "install", "--quiet", "--upgrade", "pip"])
    # 先试"实测过的精确版本"（最稳）；如果本机 Python 版本太老装不上，
    # 自动退回"宽松版本"，让 pip 自己挑一个兼容的。
    lock = ROOT / "requirements.lock.txt"
    plain = ROOT / "requirements.txt"
    attempts = []
    if lock.exists():
        attempts.append(lock)
    if plain.exists():
        attempts.append(plain)

    installed = False
    for i, req in enumerate(attempts):
        say(f"  使用的依赖清单：{req.name}")
        r = run([vpy, "-m", "pip", "install", "--quiet", "-r", str(req)])
        if r.returncode == 0:
            installed = True
            break
        if i + 1 < len(attempts):
            say("  这份清单装不上（多半是本机 Python 版本偏旧），")
            say("  自动换成宽松版本再试一次……")
    if not installed:
        say("  [x] 安装失败。请检查网络，或把这段报错发给帮你搭的人。")
        say("  小提示：建议用 Python 3.12 或更新的版本，兼容性最好。")
        return 4
    say("  [OK] 依赖装好了。")

    # 4. 放一个顺手的小命令
    say()
    say("[第 4 步 / 共 5 步] 创建 wangxiang 快捷命令")
    try:
        if os.name == "nt":
            shim = VENV / "Scripts" / "wangxiang.bat"
            shim.write_text(
                f'@echo off\r\n"{vpy}" -m wangxiang %*\r\n', encoding="utf-8")
        else:
            shim = VENV / "bin" / "wangxiang"
            shim.write_text(f'#!/bin/sh\nexec "{vpy}" -m wangxiang "$@"\n', encoding="utf-8")
            shim.chmod(0o755)
        say(f"  [OK] {shim}")
    except OSError as exc:
        say(f"  （跳过，不影响使用：{exc}）")

    # 5. 配置文件
    say()
    say("[第 5 步 / 共 5 步] 准备配置文件")
    cfg = ROOT / "config" / "config.yaml"
    tpl = ROOT / "config" / "config.example.yaml"
    if cfg.exists():
        say(f"  已存在，不动它：{cfg}")
    elif tpl.exists():
        shutil.copy2(tpl, cfg)
        say(f"  [OK] 已从模板生成：{cfg}")
        say("    [!] 请打开它，填上你的店铺网址和 WooCommerce 密钥。")
    else:
        say("  [x] 找不到 config/config.example.yaml，项目文件可能不完整。")
        return 5

    # 收尾：跑一次离线自检
    title("装完了！下面跑一次离线自检（不联网）")
    run([vpy, "-m", "wangxiang", "selftest"])

    title("接下来做什么")
    say("  1) 打开 config/config.yaml，填 3 个地方：")
    say("       base_url、consumer_key、consumer_secret")
    say("  2) 把库存文件放进 demo-inventory 文件夹（或改成你自己的路径）")
    say("  3) 在项目目录执行（Windows 用 .venv\\Scripts\\python，Mac 用 .venv/bin/python）：")
    say("       python -m wangxiang check     检查一下")
    say("       python -m wangxiang extract   第 1 步：读出库存")
    say("       python -m wangxiang diff      第 2 步：看差异（不会改网店）")
    say("       python -m wangxiang sync      第 3 步：演练（不会改网店）")
    say("       python -m wangxiang sync --yes  确认后：真的更新")
    say()
    say("  也可以直接双击：Windows 用 bin\\setup.bat，Mac 用 bin/setup.command")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
