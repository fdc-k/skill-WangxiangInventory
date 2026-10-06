#!/usr/bin/env python3
"""给双击脚本用的中文横幅。

Windows 的 .bat 文件如果直接写中文，在某些 cmd 版本下会乱码或执行出错，
所以所有中文提示都放在这个 Python 文件里输出（Python 源文件本身就是 UTF-8，
而且 wangxiang 的控制台兼容层会把输出编码处理好）。

用法： python tools/banner.py <步骤名>
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BANNERS = {
    "setup": ("安装 / 修复运行环境", [
        "装好之后就能开始用了。整个过程都可以随时重复执行，不会弄坏已有数据。",
    ]),
    "step1": ("第 1 步：读取库存文件", [
        "把 demo-inventory（或你自己指定的文件夹）里的库存文件读出来，",
        "转换成统一格式的 Excel，放到 output/unified 文件夹里。",
        "这一步只读文件、不联网、不碰网店，放心跑。",
    ]),
    "step2": ("第 2 步：和网店比对差异", [
        "把刚转换出来的库存，和网店上的实际库存逐条比对，",
        "生成一份带颜色的差异报表，放到 output/diff 文件夹里。",
        "有差异的地方会标红，完全一样的会标绿。",
        "这一步也只是查看，不会改动网店，放心跑。",
    ]),
    "step3": ("第 3 步：把差异更新到网店", [
        "先跑一次「演练」：把准备改动的内容全部打印出来，但什么都不提交。",
        "你看完演练结果、确认没问题之后，再决定要不要真的更新。",
    ]),
    "selftest": ("自检：检查解析是否还正确", [
        "重新解析一遍来源文件，和内置的基准数字对比。",
        "不联网、不改任何数据，用来确认工具本身没坏。",
    ]),
}


def main() -> int:
    key = sys.argv[1] if len(sys.argv) > 1 else ""
    title, lines = BANNERS.get(key, ("祥旺库存工具", []))
    from wangxiang import console

    console.setup()
    bar = "=" * 58
    print()
    print(bar)
    print(f"  {title}")
    print(bar)
    for line in lines:
        print(f"  {line}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
