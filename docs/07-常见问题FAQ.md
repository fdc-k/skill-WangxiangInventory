# 07 · 常见问题 FAQ

## 安装 / 环境

**Q：`ModuleNotFoundError: No module named 'yaml'`（或 openpyxl / pdfplumber）**

依赖没装。执行：

```bash
bash bin/setup.sh
# 或者
.venv/bin/pip install -r requirements.txt
```

**Q：刚 clone 下来，还没填密钥，能先跑点什么吗？**

能。`selftest`（离线自检）和 `extract`（读取库存文件）**都不需要密钥**。
如果连 `config/config.yaml` 都还没建，工具会自动用
`config/config.example.yaml` 模板跑，并提示你还没填密钥。
只有 `diff` / `sync`（要连网店）才必须填。

**Q：`command not found: .venv/bin/python`**

说明 `.venv` 不存在（没装，或者文件夹被移动过）。重新执行：

```bash
bash bin/setup.sh
```

**Q：`zsh: permission denied`**

给脚本加执行权限：

```bash
chmod +x bin/*.sh bin/*.command
```

**Q：我把文件夹改名/移动了，还能用吗？**

能。所有路径都是相对的，只要 `.venv` 一起带过去就行。
如果 `.venv` 出问题，删掉它重新 `bash bin/setup.sh` 即可。

---

## Windows 专属问题

**Q：窗口里中文变成方块 / 乱码**

窗口显示不影响功能。真正的数据在 `output` 文件夹里，
用浏览器打开 `.html`、用 Excel 打开 `.xlsx`，中文都是正常的。

如果实在想修窗口显示：右键窗口标题栏 → 属性 → 字体 → 换成 `Consolas` 或 `新宋体`。

**Q：`python 不是内部或外部命令`**

装 Python 时没勾 `Add python.exe to PATH`。两种办法：

1. 重新安装 Python，**勾上那个框**（推荐）；
2. 或者绕过它，直接用项目自带的：`.venv\Scripts\python -m wangxiang diff`

**Q：`.command` 文件打不开**

`.command` 是 Mac 专用的。Windows 请用同名的 `.bat` 文件，
例如 `2-差异比对.bat`。

**Q：双击 `.bat` 一闪就没了**

说明程序报错了。改用命令行就能看到报错原因：

```
cd /d C:\wangxiang
.venv\Scripts\python -m wangxiang diff
```

**Q：杀毒软件报毒 / 把文件删了**

`.bat` 和 `.exe` 容易被误报。把项目文件夹加入杀毒软件白名单，
重新拷贝一份，再双击 `setup.bat`。

**Q：路径里有中文或空格，会有问题吗？**

一般没问题。但为了少踩坑，建议放 `C:\wangxiang` 这种简单路径。

---

## WorkBuddy 专属问题

**Q：WorkBuddy 里怎么用？**

看 [10-WorkBuddy使用指南](10-WorkBuddy使用指南.md)。简单说：
在对话里直接说「用 wangxiang-inventory 跑一下 diff」就行。

**Q：提示找不到 Python，但我有 WorkBuddy**

先**打开一次 WorkBuddy 软件**（它会准备自带的 Python），
再重新跑安装脚本。安装脚本会自动找到它。

**Q：WorkBuddy 弹权限提示怎么办？**

| 提示 | 怎么办 |
|---|---|
| 要写项目文件夹 | 允许 |
| 要联网访问你的店铺域名 | 允许 |
| 要执行 `.venv` 里的 Python | 允许 |

**Q：WorkBuddy 没有"双击"怎么办？**

改成用说的：「跑 diff」「把差异报表发给我」「确认同步」。

---

## 连接网店

**Q：`401 Unauthorized` / `Consumer key is invalid`**

1. 确认 `config.yaml` 里的 key 和 secret 没有多余空格；
2. 后台 **WooCommerce → 设置 → 高级 → REST API** 确认这对密钥还在、权限是「读/写」；
3. 如果密钥被删过，重新生成再填。

**Q：`403 Forbidden`**

权限选成了「只读」。删掉重新生成，权限选 **Read/Write**。

**Q：`404 rest_no_route`**

- `base_url` 写错了（不要带 `https://`，不要带结尾 `/`）；
- 或者站点没启用固定链接。到 **设置 → 固定链接** 随便选一个非「朴素」的格式保存一次。

**Q：连接很慢 / 超时**

把 `config.yaml` 里 `timeout` 改成 `120`。如果还慢，多半是服务器在国外或被防火墙限制。

**Q：`SSL certificate problem`**

临时排查可以用 `verify_ssl: false`，但**不建议长期这样**。

---

## 提取（extract）

**Q：出来的行数是 0**

- 检查 `product_column` / `size_column` 是不是写对了（A、B、C…）；
- 打开 `output/unified/extract_stats.json` 看每个来源的处理结果；
- 确认 `sheet` 名字对（不是「Sheet1」就是「工作表1」，大小写和空格要一致）。

**Q：商品名没有向下填充**

本工具会自动处理合并单元格。如果你的表**没有真正合并**、而是上面的行留空，
请把商品名列全选后「合并单元格」，或者手工补全。

**Q：PDF 解析出来的商品少了/错了**

看 `extract_stats.json` 里的 `orphan_skus`：如果非空，说明有些货号没被分配到商品块。
把这个输出的 `source_ref` 拿到 PDF 里核对。
货盘 PDF 版式如果有变化（比如多了新的分区），需要在 `config.yaml` 的
`section_columns` 里补上那个分区。

---

## 比对（diff）

**Q：`未能匹配` 特别多**

差不多都是「网店还没有上架这个商品」。看 `output/diff/*.xlsx` 的
**待处理商品清单** 页，那里一个商品一行，写清了处理建议。

**Q：明明网店有这个商品，却说没匹配上**

1. 打开 `config/product_map.csv`，找到那行，手工填上 `parent_sku`；
2. 或者把 `options.fuzzy_threshold` 调低一点（比如 `0.75`）再跑；
3. 注意 `source_product` 必须和统一格式 Excel 里完全一致（含空格与大小写）。

**Q：数量怎么是空的？**

那个来源文件本身就没有数量（比如货盘 PDF 只有 ✅）。
这类来源只能同步「有货/缺货」，不会动库存数字。

**Q：`一致` 里数量明明是 45，网店却不管理库存，为什么还叫一致？**

因为网店那个变体的「管理库存」是关闭的，只区分有货/缺货。
默认 `sync.mode: auto` 会尊重网店的设置。想让工具接管数量，
把 `sync.mode` 改成 `quantity`。

**Q：跑完 diff 以后又改了源文件，结果没变化**

统一格式 Excel 是中间产物。改完源文件要**先 `extract` 再 `diff`**。

---

## 同步（sync）

**Q：为什么 `sync` 什么都没改？**

`sync` 默认是演练模式。要真正更新必须加 `--yes`。

**Q：一部分失败会怎样？**

不会中断整批。每条独立记录成功/失败，失败的会写明 HTTP 错误。
修好原因后再跑一次 `sync --yes`，已经成功的不会重复更新。

**Q：更新错了能撤销吗？**

能。每次同步都会在 `output/sync/` 生成一份 `回滚快照_<时间>.json`，
一条命令还原：

```bash
.venv/bin/python -m wangxiang rollback output/sync/回滚快照_20261007-012230.json --yes
```

去掉 `--yes` 就是演练，只会告诉你会还原成什么，不会提交。
另外同步日志里也逐条记着「更新前」的数值，可以手工核对。

**建议第一次先小范围试**：`sync --yes --only-source SP5` 或
`sync --yes --only-sku 192HO24`。

**Q：报表里出现「需人工填数量」是什么意思？**

来源文件（比如货盘 PDF）只标了「有货」，但网店这个变体开着「管理库存」，
而且当前数量是 0。工具不知道你实际有多少件，所以不会瞎填，
需要你人工在网店填上数量（或者把 `sync.mode` 改成 `status` 只同步状态）。

**Q：为什么「判缺货」的时候数量也被置成 0 了？**

这是默认策略 `sync.no_qty_policy: status_and_zero` 的行为：来源说这个尺码没货，
如果只把状态改成缺货而数量还挂着 5，网店前台会前后矛盾。
如果你希望数量完全不动，把它改成 `status`。

**Q：会不会把「管理库存」关掉？**

默认 `sync.mode: auto` 不会改动变体的「管理库存」开关，
只在原本就管理库存时写数量（没有数量的来源则只写状态）。
只有 `sync.mode: quantity` 才会打开「管理库存」。

---

## 其它

**Q：能定时自动跑吗？**

可以。三行命令串起来即可（在 macOS/Linux 的 crontab 里）：

```bash
cd /path/to/skill-WangxiangInventory && \
  ./.venv/bin/python -m wangxiang extract && \
  ./.venv/bin/python -m wangxiang diff && \
  ./.venv/bin/python -m wangxiang sync --yes
```

⚠️ 但**不建议**完全无人值守地自动 --yes，最好还是人看一遍差异报表。

**Q：能不能只处理某几个来源？**

```bash
.venv/bin/python -m wangxiang extract --sources SP5,ALO
```

**Q：能不能只同步一部分？**

```bash
.venv/bin/python -m wangxiang sync --yes --only-source SP5
.venv/bin/python -m wangxiang sync --yes --only-sku 192HO24
```

**Q：报表里的中文变成乱码**

用 Excel 打开 `.md` 可能乱码；`.xlsx` 不会。
`product_map.csv` 是 UTF-8 with BOM，Excel 直接双击也不会乱码。
