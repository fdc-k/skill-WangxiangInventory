---
name: wangxiang-inventory
description: >-
  祥旺库存工具。读取多来源库存文件（Excel 表格 / 货盘 PDF），转换成统一格式的
  Excel 库存表，并与 WordPress + WooCommerce 独立站在线库存逐条比对（差异用颜色
  标记），经用户确认后通过 WooCommerce REST API 批量更新库存，并输出成功/失败明细，
  同时生成可一键回滚的快照。跨平台：Windows / macOS / Linux 通用，在 WorkBuddy、
  Codex、Claude Code 里都能直接调用。Use when 用户提到：库存同步、库存表、库存差异、
  WooCommerce 库存、独立站库存、货盘 PDF、SP5 / ALO / Essentials 库存、把库存更新到网店。
---

# 祥旺库存工具（wangxiang-inventory）

## 这个 Skill 解决什么问题

档口/工作室的库存表格式五花八门：有的 Excel 是「商品名 + 尺码 + 数量」，
有的 PDF「货盘」只有一个 ✅ 表示有货。这个 Skill 把它们统一成同一种格式，
再和 WooCommerce 网店的在线库存逐条比对，把差异用颜色标出来给人确认，
**确认之后**才通过 REST API 批量更新，并输出每一条的变化明细。

## 目录结构

```
SKILL.md                    本文件（给 AI 看的操作说明）
README.md                   给人看的快速上手（中文、零基础）
docs/                       详细帮助文档（安装 / 使用 / Windows / WorkBuddy / FAQ）
config/config.yaml          真实配置（网址 + 密钥 + 来源文件）—— 已被 .gitignore
config/config.example.yaml  配置模板（可以放心分发）
config/product_map.csv      商品映射表（来源商品 → 网店货号），可人工编辑
requirements.txt            依赖（宽松版本）
requirements.lock.txt       依赖（实测通过的精确版本，安装脚本优先用它）
wangxiang/                  Python 代码
tools/bootstrap.py          跨平台安装脚本（只用标准库，负责找 Python + 装依赖）
tools/banner.py             双击脚本用的中文横幅（中文不进 .bat，避免乱码）
bin/                        各平台启动脚本（.bat / .command / .sh）
tests/baseline.json         回归基线（行数/商品数，selftest 用它判断有没有跑偏）
demo-inventory/             示例数据（一份 PDF + 两份 Excel）
output/                     所有产物：unified / diff / sync
```

---

## 关键：跨平台命令对照

**同一个操作，三种系统的写法不同。执行前先判断当前系统。**

| 操作 | Windows | macOS / Linux |
|---|---|---|
| 装环境 | `py -3 tools\bootstrap.py` | `python3 tools/bootstrap.py` |
| 跑命令 | `.venv\Scripts\python -m wangxiang <cmd>` | `.venv/bin/python -m wangxiang <cmd>` |
| 短命令 | `.venv\Scripts\wangxiang <cmd>` | `.venv/bin/wangxiang <cmd>` |
| 双击入口 | `bin\*.bat` | `bin/*.command` |

**推荐做法**：不确定环境时，直接跑安装脚本，它自己会选对 Python：

```
# 任何系统都可以先跑这一句，它会自己判断
python tools/bootstrap.py
```

在 **WorkBuddy** 里更简单：WorkBuddy 自带 Python，注册在
`~/.workbuddy/binaries/.cache/registry.json`，
`tools/bootstrap.py` 会**优先读这个注册表**，用户什么都不用装。

---

## 环境要求

- Python **3.10+**（WorkBuddy 自带 3.13，会被自动选中）
- 依赖：openpyxl / pdfplumber / numpy / requests / PyYAML（+ 它们的间接依赖）
- 全部装在项目自己的 `.venv` 里，不污染系统

---

## 标准工作流

```bash
# 0. 装环境（已装过会跳过，可反复执行）
python tools/bootstrap.py

# 1. 离线自检：确认解析结果和基线一致（不联网，约 30 秒）
python -m wangxiang selftest

# 2. 环境 + 来源文件 + 网店连通性自检（联网）
python -m wangxiang check

# 3. 提取与拆分：来源文件 → 统一格式 Excel
python -m wangxiang extract

# 4. 差异比对：统一格式 + 线上库存 → 彩色差异报表（只读）
python -m wangxiang diff

# 5. 同步：默认只演练，确认后才真正写
python -m wangxiang sync             # 演练（不改线上）
python -m wangxiang sync --yes       # 真正更新（自动存回滚快照）
python -m wangxiang sync --ask       # 先演练，再用中文问用户要不要更新（适合双击）
```

辅助命令：

```bash
python -m wangxiang map                       # 查看商品匹配建议
python -m wangxiang map --write               # 把建议写进 config/product_map.csv
python -m wangxiang diff --combo              # 允许用「组合商品」的货号匹配
python -m wangxiang sync --yes --only-source SP5      # 只同步某个来源
python -m wangxiang sync --yes --only-sku 192HO24     # 只同步含关键词的条目
python -m wangxiang rollback output/sync/回滚快照_xxx.json --yes   # 一键撤回
```

---

## 作为 AI 使用时必须遵守的规则

1. **先读 `config/config.yaml`**，确认 `store.base_url` 与 `sources` 指向正确的店铺和文件。
   如果用户给了新的密钥/网址，先改这里。
2. **永远不要跳过差异比对直接 sync。** 用户明确说「确认更新」之前，只允许
   `extract`、`diff`、`selftest`，以及不带 `--yes` 的 `sync`（演练）。
   `--ask` 会自己问用户，可以安全使用。
3. **差异报表有三种同内容格式，优先给用户 `.html`**（双击就能看，颜色和中文最稳）：
   `output/diff/库存差异_<时间戳>.html` / `.xlsx` / `.md`。Excel 版工作表：

   | 工作表 | 内容 | 颜色 |
   |---|---|---|
   | 差异明细 | 和网店不一致的条目 | 整行浅红，变化的单元格深红 |
   | 无差异 | 完全一致 | 浅绿 |
   | 需人工处理 | 网店没有的商品/尺码，含「近似货号建议」 | 浅黄 |
   | 待处理商品清单 | 按商品去重汇总，一商品一行 | 浅黄 |
   | 汇总 | 统计数字 | |

4. **更新完成后必须向用户汇报** `output/sync/同步结果_<时间>.xlsx` 里的
   成功条数、失败条数、每条「更新前 → 更新后」的变化，失败的要给出错误原因。
   **同时告诉用户回滚快照的路径**（`output/sync/回滚快照_<时间>.json`），
   要撤回就 `python -m wangxiang rollback <快照> --yes`。
5. 想只动一部分时用 `--only-source <来源ID>` 或 `--only-sku <关键词>` 缩小范围；
   第一次上线建议先拿一个来源或一个款式试水。
6. **Windows 注意事项**：
   - 命令里的 `.venv/bin/python` 要换成 `.venv\Scripts\python`
   - 不要往 `.bat` 文件里写中文（会乱码）——中文一律由 Python 打印，
     `.bat` 只负责调用 `tools/banner.py`
   - 如果控制台显示不了中文/符号，设环境变量 `WANGXIANG_ASCII=1`，
     工具会自动退化成纯文本符号（`[OK]` / `[x]`）
7. **数量语义要讲清楚**：
   - 来源有数量 + 网店变体「管理库存」→ 同步数量
   - 来源只有 ✅（如货盘 PDF）→ 只同步有货/缺货，**不动库存数字**
   - 来源说「有货」但网店数量是 0 → 工具不会瞎猜数字，会标成「需人工填数量」
   - 想强制按数量同步，把 `config/config.yaml` 的 `sync.mode` 改成 `quantity`

---

## 支持的数据来源（adapter）

| adapter | 适用文件 | 关键配置 |
|---|---|---|
| `excel_table` | 商品名 / 尺码 / 数量 三列，允许合并单元格 | `product_column`、`size_column`、`quantity_column`、`sheet` |
| `pdf_pallet` | 「货盘」PDF：灰色分区标题条 + ✅ 尺码格 | `page`、`section_columns` |

新增来源 = 在 `config/config.yaml` 的 `sources` 里加一段，**不用改代码**。

---

## 常见故障速查

| 现象 | 处理 |
|---|---|
| `缺少 PyYAML` 之类 | 跑一次安装脚本：`python tools/bootstrap.py` |
| Windows 提示找不到 Python | 先打开一次 WorkBuddy；或装 Python 时勾选 `Add python.exe to PATH` |
| 控制台中文/符号乱码 | 设 `WANGXIANG_ASCII=1`；报表文件本身不受影响 |
| `401 Unauthorized` | 密钥不对/被删；工具会打印 1-2-3 排查步骤 |
| `403 Forbidden` | 密钥权限要选「读/写 Read/Write」 |
| `404 rest_no_route` | 网址写错，或站点固定链接设置有问题 |
| 大量「需人工处理」 | 商品在网店还没上架，或名称/货号不同；看「待处理商品清单」的近似货号建议 |
| 改了来源文件但结果没变 | 先 `extract` 再 `diff`（统一格式 Excel 是中间产物） |
| 改了 `extract_pdf.py` 等解析逻辑 | 跑 `python -m wangxiang selftest`，和 `tests/baseline.json` 对比 |

细节见 `docs/`，Windows 用户看 `docs/09-Windows使用指南.md`，
在 WorkBuddy 里用看 `docs/10-WorkBuddy使用指南.md`。
