# 04 · 怎么拿到 WooCommerce 密钥（Consumer Key / Secret）

> 💡 **Windows 用户**：下面命令里的 `.venv/bin/python` 要换成 `.venv\Scripts\python`。


工具需要一对密钥才能读写你的网店库存。整个过程 3 分钟。

## 前提

- 你的网站装了 **WooCommerce** 插件；
- 你有 WordPress 的**管理员**账号（不是普通编辑）。

---

## 步骤

### 1. 进入 REST API 设置页

浏览器登录 WordPress 后台（一般是 `你的域名/wp-admin`），然后访问：

```
你的域名/wp-admin/admin.php?page=wc-settings&tab=advanced&section=keys
```

或者在后台菜单里点：
**WooCommerce → 设置 → 高级 → REST API**

### 2. 添加密钥

点击 **添加密钥 / Add key**，填写：

| 字段 | 填什么 |
|---|---|
| 描述 / Description | 例如 `祥旺库存工具`（随便写，方便以后辨认） |
| 用户 / User | 选择你自己的管理员账号 |
| 权限 / Permissions | **读/写 / Read/Write** ← 必须选这个，否则不能更新库存 |

点 **生成密钥 / Generate API key**。

### 3. 复制密钥

页面会出现：

```
Consumer key    ck_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
Consumer secret cs_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

> ⚠️ **Secret 只显示这一次！** 关掉页面就再也看不到了（只能删掉重新生成）。
> 请立刻复制到安全的地方。

### 4. 填进配置文件

打开 `config/config.yaml`：

```yaml
store:
  base_url: "dailyessentials.club"
  consumer_key: "ck_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
  consumer_secret: "cs_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

注意：
- `base_url` **不要**写 `https://`，**不要**写结尾的 `/`；
- 不要把密钥写进引号外面；
- 保存文件（UTF-8 编码）。

### 5. 验证

```bash
.venv/bin/python -m wangxiang check
```

看到 `ok 连接成功` 就成功了。

---

## 常见报错

| 报错 | 原因 | 解决 |
|---|---|---|
| `401 Unauthorized` | 密钥错 / 被删 / 复制时多了空格 | 重新生成，注意不要把前后空格复制进去 |
| `403 Forbidden` | 权限只选了「读」 | 删掉密钥，重新生成时选 **读/写** |
| `404 rest_no_route` | 网址写错了，或没装 WooCommerce | 确认 `base_url` 正确，并且用浏览器打开 `你的域名/wp-json/wc/v3/products` 试试 |
| `SSL certificate problem` | 服务器证书有问题 | 临时在 `config.yaml` 里设 `verify_ssl: false`（不安全，仅用于排查） |
| 连接超时 | 服务器慢或被防火墙拦 | 把 `timeout` 调大到 `120`；确认服务器允许外部访问 REST API |

---

## 安全提醒

1. `config/config.yaml` 等于**网店的后门钥匙**，不要发给别人、不要上传 GitHub。
   本项目 `.gitignore` 已经排除它。
2. 要分享给同事，请分享 `config/config.example.yaml`（模板，没有密钥）。
3. 换人接手时，建议在后台**删掉旧密钥**再生成新的。
4. 建议专门开一个权限受限的管理员账号给这个工具用，而不是主账号。

---

## 我想只让它「只能读不能写」行不行？

可以：生成密钥时权限选 **读 / Read**。然后 `diff`、`extract` 都能正常跑，
只有 `sync --yes` 会 403 失败。适合先观察一段时间再决定要不要开放写权限。
