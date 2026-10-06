# 10 · 在 WorkBuddy 里使用这个工具

在 WorkBuddy 里用，比单独装更省事 —— 因为 **WorkBuddy 自带 Python**，
你不需要自己装任何东西。

---

## 一、已经装好了吗？

这台电脑上已经装好了。检查方法：

| 看哪里 | 应该看到 |
|---|---|
| `~/.workbuddy/skills/wangxiang-inventory` | 一个指向本项目文件夹的快捷方式 |

> Windows 上对应 `%USERPROFILE%\.workbuddy\skills\wangxiang-inventory`

**如果还没有**，装起来只要一行命令（把路径换成你实际存放的位置）：

**Mac / Linux**
```bash
ln -sfn /你的路径/skill-WangxiangInventory ~/.workbuddy/skills/wangxiang-inventory
```

**Windows（在 PowerShell 里）**
```powershell
New-Item -ItemType Junction -Path "$env:USERPROFILE\.workbuddy\skills\wangxiang-inventory" -Target "C:\wangxiang"
```

---

## 二、第一次准备（只做一次）

### 1. 让 WorkBuddy 帮你装依赖

在 WorkBuddy 的对话里直接说：

> 用 wangxiang-inventory 这个 skill，先帮我跑一下安装脚本

WorkBuddy 会去执行 `tools/bootstrap.py`。
因为 **WorkBuddy 自带 Python**，脚本会自动用它来建环境、装依赖，你不用装 Python。

### 2. 填密钥

打开 `config/config.yaml`，填 3 行：

```yaml
store:
  base_url: "dailyessentials.club"     # 你的网站，不要 https://，结尾不要 /
  consumer_key: "ck_你的密钥"
  consumer_secret: "cs_你的密钥"
```

密钥怎么拿 → [04-WooCommerce密钥获取](04-WooCommerce密钥获取.md)

---

## 三、日常怎么用（直接在对话里说）

装好之后，你**不用记任何命令**，直接用大白话跟 WorkBuddy 说：

| 你想做的事 | 就这样说 |
|---|---|
| 读取库存文件 | 「用 wangxiang-inventory 跑一下 extract，把库存文件读出来」 |
| 看和网店的差异 | 「用 wangxiang-inventory 跑 diff，把差异报表给我看」 |
| 更新网店 | 「差异我看过了，确认同步，执行 sync --yes」 |
| 撤回更新 | 「用回滚快照把库存还原回去」 |
| 检查有没有装好 | 「跑一下 wangxiang-inventory 的 selftest」 |

WorkBuddy 会自动读 `SKILL.md`，里面写清楚了完整流程，
以及一条**硬规矩：没有你的确认，不许执行 `sync --yes`**。

---

## 四、WorkBuddy 的沙箱和权限

WorkBuddy 会对文件读写做权限控制。第一次跑的时候，如果弹出"允许访问"之类的提示：

| 提示 | 怎么办 |
|---|---|
| 要写入项目文件夹 | **允许**（输出报表、生成 Excel 都要写这里） |
| 要联网访问 `dailyessentials.club` | **允许**（要拉网店数据） |
| 要执行 `.venv` 里的 Python | **允许**（这是本工具自己的运行环境） |

如果被拦住了，报表就会生成失败，日志里会写"Permission denied"。

---

## 五、WorkBuddy 里点不开东西？

WorkBuddy 没有"双击"这个动作，所以：

| 在电脑上你会… | 在 WorkBuddy 里改成说… |
|---|---|
| 双击 `2-差异比对.bat` | 「跑 diff」 |
| 双击 `库存差异_xxx.html` | 「把 output/diff 里的差异报表发给我」 |
| 打开 `config/config.yaml` 改 | 「帮我把 config.yaml 的 base_url 改成 xxx」 |

---

## 六、WorkBuddy 自带 Python 在哪（技术备注）

WorkBuddy 把托管运行时记在一个注册表文件里：

```
~/.workbuddy/binaries/.cache/registry.json
```

里面 `binaries.python.<版本>.executablePath` 就是解释器路径（Windows 和 Mac 都是这个结构）。
本工具的 `tools/bootstrap.py` 会**优先读这个文件**，所以：

- ✅ 不需要用户另外装 Python
- ✅ 换 WorkBuddy 版本 / 换电脑都能自动找到
- ✅ 找不到才退回去用系统 Python

你可以自己验证一下：

```bash
python tools/bootstrap.py     # 第 1 步会打印它选中了哪个 Python
```

---

## 七、给 WorkBuddy 用的完整对话示例

> **你**：用 wangxiang-inventory 帮我把 demo-inventory 里三个库存文件同步到网店。
>
> **WorkBuddy**：（读 SKILL.md）先跑 extract → 再跑 diff → 把差异报表给你看 → 等你确认 →
> 你确认后才 `sync --yes` → 最后把逐条结果发给你。
>
> **你**：确认同步。
>
> **WorkBuddy**：（执行）同步完成，72 条全部成功，逐条明细如下……

---

## 八、在 Codex / Claude Code 等其它 AI 工具里用

这个工具不绑死在 WorkBuddy 上。同一个文件夹可以同时装到多个地方：

| 工具 | 安装位置 |
|---|---|
| WorkBuddy | `~/.workbuddy/skills/wangxiang-inventory` |
| Codex | `~/.codex/skills/wangxiang-inventory` |
| Claude Code | `~/.claude/skills/wangxiang-inventory` |

**都是同一份文件**（用软链接指过来），所以改一次、到处生效。
`SKILL.md` 是通用的，读哪个都一样。
