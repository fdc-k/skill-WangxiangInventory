# 09 · Windows 用户专用指南

这一篇只讲 Windows。**照着做，一步一步来，不会出错。**

---

## 一、我能用吗？

| 项目 | 要求 |
|---|---|
| 系统 | Windows 10 / 11（64 位） |
| 软件 | 不需要装 Office、不需要装数据库 |
| Python | **不用自己装**（脚本会帮你找；找不到才需要装，见第四节） |
| 网络 | 第一次安装和更新网店时需要联网 |

---

## 二、安装（只做一次）

### 1. 打开这个文件夹

下载/拷贝过来的文件夹，名字大概是 `skill-WangxiangInventory`。
**不要放在桌面上的中文长路径里**（比如 `C:\Users\张三\桌面\库存\新建文件夹\...`），
建议放到简单的位置，例如：

```
C:\wangxiang
```

> 为什么？因为路径太长或有特殊字符，偶尔会让某些工具出错。放简单一点最保险。

### 2. 双击安装

进去后打开 **`bin`** 文件夹，双击 **`setup.bat`**。

会出现一个黑色窗口，自动开始装东西。你会看到类似：

```
==========================================================
 祥旺库存工具 —— 安装 / 修复运行环境
==========================================================
  [OK] 用这个：WorkBuddy 自带的 Python
  [OK] 创建好了。
  [OK] 依赖装好了。
  ...
✅ 自检全部通过。
```

**第一次需要联网，等 1~3 分钟。** 看到"自检全部通过"就好了。

> **窗口里如果显示"没有找到 Python"** → 看下面第四节。

### 3. 如果 Windows 弹窗拦截

第一次双击 `.bat` 文件，Windows 可能弹提示、或者杀毒软件提示"已阻止"。
这是正常的（因为 `.bat` 是可执行脚本）。选择 **"仍要运行" / "允许"** 即可。

如果被彻底删掉了，把你的文件夹加入杀毒软件的"白名单/信任区"，再重新拷贝一份。

---

## 三、日常使用（Windows 版）

### 最快的办法：双击

打开 `bin` 文件夹，**按顺序**双击这三个：

1. **`1-提取库存.bat`** —— 读取库存文件（不改网店）
2. **`2-差异比对.bat`** —— 生成差异报表，跑完会自动打开报表文件夹
3. **`3-同步更新.bat`** —— 先演练，然后问你要不要真的更新（输入 `YES` 才更新）

### 用命令行（可选）

打开"命令提示符"或"PowerShell"，先进入项目目录：

```bat
cd /d C:\wangxiang
```

然后：

```bat
.venv\Scripts\python -m wangxiang check        :: 检查一下
.venv\Scripts\python -m wangxiang extract      :: 第 1 步
.venv\Scripts\python -m wangxiang diff         :: 第 2 步
.venv\Scripts\python -m wangxiang sync         :: 第 3 步（演练）
.venv\Scripts\python -m wangxiang sync --yes   :: 第 3 步（真的更新）
```

或者用安装时创建好的短命令（更省事）：

```bat
.venv\Scripts\wangxiang check
.venv\Scripts\wangxiang diff
```

> **Mac 上的 `.command` 文件在 Windows 上点不开**，这是正常的。
> Windows 用 `.bat`，Mac 用 `.command`，名字虽然不一样，做的事完全相同。

---

## 四、提示"没有找到 Python"怎么办

### 情况 A：你用 WorkBuddy

先**打开一次 WorkBuddy 软件**（它会自动下载自带的 Python），
然后回到这里，重新双击 `setup.bat`。

### 情况 B：没用 WorkBuddy

1. 打开 <https://www.python.org/downloads/>
2. 点黄色的 **Download Python 3.x.x** 按钮
3. 运行下载的安装包
4. **⚠️ 最重要的一步**：安装第一屏最下面有一个勾选框
   **`Add python.exe to PATH`** —— **必须勾上！**
5. 点 `Install Now`，装完关掉
6. 回到 `bin` 文件夹，重新双击 `setup.bat`

---

## 五、Windows 上常见的小问题

| 现象 | 原因 | 怎么办 |
|---|---|---|
| 窗口里中文变成方块或乱码 | 控制台字体问题 | 不影响功能。报表文件（.html / .xlsx）里的中文是正常的，用浏览器/Excel 打开看就行 |
| 窗口一闪就没了 | 程序报错后自动关闭 | 改用命令行运行，就能看到完整报错：`cd /d 你的目录` 然后 `.venv\Scripts\python -m wangxiang diff` |
| `python 不是内部或外部命令` | 装 Python 时没勾 "Add to PATH" | 重新装一遍 Python，勾上那个框；或者直接用 `.venv\Scripts\python` |
| `拒绝访问` / `Permission denied` | 文件夹放在了系统盘受保护目录 | 把整个文件夹挪到 `C:\wangxiang` 这种地方 |
| 双击 `.bat` 后提示找不到路径 | 文件夹路径里有特殊字符 | 挪到简单路径，例如 `C:\wangxiang` |
| 下载依赖很慢或失败 | 网络问题 | 换个网络，或连着手机热点再试一次；脚本可以反复重跑 |
| 杀毒软件把文件删了 | 误报 | 把文件夹加入白名单，重新拷贝一份，再双击 `setup.bat` |

---

## 六、确认装好了

双击 **`bin\4-离线自检.bat`**。

看到最后一行是 **`✅ 自检全部通过。`** 就说明 Windows 上一切正常。

这个自检：
- 不联网
- 不改任何数据
- 大约 30 秒

如果它报错，把窗口里的内容**整段复制**发给帮你搭的人即可。

---

## 七、Mac 和 Windows 对照表

| 事情 | Windows | Mac |
|---|---|---|
| 安装 | 双击 `bin\setup.bat` | 双击 `bin/setup.command` |
| 第 1 步 | 双击 `bin\1-提取库存.bat` | 双击 `bin/1-提取库存.command` |
| 第 2 步 | 双击 `bin\2-差异比对.bat` | 双击 `bin/2-差异比对.command` |
| 第 3 步 | 双击 `bin\3-同步更新.bat` | 双击 `bin/3-同步更新.command` |
| 自检 | 双击 `bin\4-离线自检.bat` | 双击 `bin/4-离线自检.command` |
| Python 位置 | `.venv\Scripts\python` | `.venv/bin/python` |
| 路径分隔符 | `\`（反斜杠） | `/`（正斜杠） |

**其他所有东西都一样**：配置文件、报表、输出文件夹，完全通用。
