"""WooCommerce REST API 客户端（只依赖 requests）。"""
from __future__ import annotations

import json
import time
from pathlib import Path

import requests

from .util import normalize_sku


class WooError(RuntimeError):
    pass


def _auth_help(status: int, url: str, body: str) -> str:
    """把 401/403 翻译成初学者看得懂的排查步骤。"""
    if status == 401:
        head = "HTTP 401 未授权：WooCommerce 没认出这对密钥。"
        steps = [
            "config/config.yaml 里的 consumer_key / consumer_secret 有没有复制完整、有没有多余空格",
            "密钥是不是已经被删掉了（后台 设置->高级->REST API 里能看见还在不在）",
            "网址有没有写对（不要带 https://，不要带结尾的 /）",
        ]
    else:
        head = "HTTP 403 无权限：密钥是对的，但权限不够。"
        steps = [
            "后台 设置->高级->REST API，把这条密钥删掉，重新生成时权限选「读/写 Read/Write」",
            "如果你只想看不想改，也可以保留「只读」——extract 和 diff 能用，sync 会失败",
        ]
    lines = [head, f"  请求地址：{url}"]
    for i, x in enumerate(steps, 1):
        lines.append(f"  {i}) {x}")
    lines.append(f"  服务器原话：{body[:200]}")
    return "\n".join(lines)


class WooClient:
    def __init__(self, base_url: str, consumer_key: str, consumer_secret: str,
                 *, verify_ssl: bool = True, timeout: int = 60, per_page: int = 100,
                 api_version: str = "wc/v3", cache_dir: str | Path | None = None):
        if not base_url:
            raise WooError("配置里没有填 store.base_url")
        if not consumer_key or not consumer_secret:
            raise WooError("配置里缺少 consumer_key / consumer_secret")
        self.base = base_url.rstrip("/")
        if not self.base.startswith("http"):
            self.base = "https://" + self.base
        self.root = f"{self.base}/wp-json/{api_version}"
        self.auth = (consumer_key, consumer_secret)
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self.per_page = per_page
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.session = requests.Session()

    # ------------------------------------------------------------ 底层请求

    def request(self, method: str, endpoint: str, *, params=None, payload=None,
                retries: int = 3):
        url = f"{self.root}/{endpoint.lstrip('/')}"
        last = None
        for attempt in range(retries):
            try:
                resp = self.session.request(
                    method, url, auth=self.auth, params=params, json=payload,
                    timeout=self.timeout, verify=self.verify_ssl,
                    headers={"User-Agent": "wangxiang-inventory-skill/1.0"},
                )
            except requests.RequestException as exc:
                last = exc
                time.sleep(1.5 * (attempt + 1))
                continue
            if resp.status_code in (429, 502, 503, 504):
                last = WooError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                time.sleep(1.5 * (attempt + 1))
                continue
            if resp.status_code in (401, 403):
                raise WooError(_auth_help(resp.status_code, url, resp.text))
            if resp.status_code == 404:
                raise WooError(
                    f"HTTP 404：接口地址不存在（{url}）。\n"
                    f"  常见原因：1) config.yaml 的 store.base_url 写错（不要带 https://、不要带结尾 /）；"
                    f"2) 站点没装 WooCommerce；3) 固定链接设置有问题（设置->固定链接 随便换个格式保存一次）。")
            if resp.status_code >= 400:
                raise WooError(f"{method} {url} -> HTTP {resp.status_code}: {resp.text[:400]}")
            if not resp.content:
                return None
            try:
                return resp.json()
            except json.JSONDecodeError:
                return resp.text
        raise WooError(f"{method} {url} 连续失败：{last}")

    def get(self, endpoint, **params):
        return self.request("GET", endpoint, params=params or None)

    def post(self, endpoint, payload):
        return self.request("POST", endpoint, payload=payload)

    def put(self, endpoint, payload):
        return self.request("PUT", endpoint, payload=payload)

    # ------------------------------------------------------------ 业务接口

    def ping(self):
        data = self.get("products", per_page=1)
        return bool(data)

    def list_products(self, status="any", extra=None):
        out, page = [], 1
        while True:
            params = {"per_page": self.per_page, "page": page, "status": status}
            if extra:
                params.update(extra)
            chunk = self.get("products", **params)
            if not chunk:
                break
            out.extend(chunk)
            if len(chunk) < self.per_page:
                break
            page += 1
        return out

    def list_variations(self, product_id):
        out, page = [], 1
        while True:
            chunk = self.get(f"products/{product_id}/variations",
                             per_page=self.per_page, page=page)
            if not chunk:
                break
            out.extend(chunk)
            if len(chunk) < self.per_page:
                break
            page += 1
        return out

    def update_variation(self, product_id, variation_id, payload):
        return self.put(f"products/{product_id}/variations/{variation_id}", payload)

    # ------------------------------------------------------------ 目录缓存

    def fetch_catalog(self, *, refresh=False, verbose=True):
        """拉取全店商品 + 变体，返回 dict。

        结构::

            {
              "products": [ {...}, ... ],
              "variations": { "<product_id>": [ {...}, ... ] },
              "by_parent_sku": { "<NORMALIZED SKU>": product_id },
              "fetched_at": <epoch>,
            }
        """
        cache_file = None
        if self.cache_dir:
            cache_file = Path(self.cache_dir) / "woo_catalog.json"
            if cache_file.exists() and not refresh:
                try:
                    data = json.loads(cache_file.read_text(encoding="utf-8"))
                    if data.get("base_url") == self.base and data.get("products"):
                        if verbose:
                            print(f"  （使用本地缓存 {cache_file.name}，加 --refresh 可强制重取）")
                        return data
                except (json.JSONDecodeError, OSError):
                    pass

        if verbose:
            print("  正在从 WooCommerce 拉取商品列表……")
        products = self.list_products()
        variations = {}
        for i, p in enumerate(products, 1):
            if p.get("type") != "variable":
                continue
            if verbose and i % 20 == 0:
                print(f"    已处理 {i}/{len(products)} 个商品")
            variations[str(p["id"])] = self.list_variations(p["id"])

        by_parent_sku = {}
        for p in products:
            key = normalize_sku(p.get("sku"))
            if key:
                by_parent_sku.setdefault(key, p["id"])

        data = {
            "base_url": self.base,
            "fetched_at": time.time(),
            "products": products,
            "variations": variations,
            "by_parent_sku": by_parent_sku,
        }
        if cache_file:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        if verbose:
            total_v = sum(len(v) for v in variations.values())
            print(f"  完成：{len(products)} 个商品，{total_v} 个变体。")
        return data
