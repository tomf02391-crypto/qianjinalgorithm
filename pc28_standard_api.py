#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pc28_standard_api.py — 加拿大28（PC28/JND28）统一数据接口模块
================================================================
统一规范：
  - 多源自动降级：pc28.help → pgsoft → 28api → byw.bet
  - 内置缓存层（默认3秒TTL）
  - 超时控制 + 自动重试（指数退避）
  - 统一返回格式（无论哪个源都转成标准结构）
  - 支持预测/遗漏/长龙/历史 全接口

适用：qianjinalgorithm / qingxun-algorithm / ime-backend

用法：
  from pc28_standard_api import PC28API
  api = PC28API()
  latest = api.get_latest()           # 实时开奖
  history = api.get_history(50)       # 历史50期
  pred = api.get_prediction()         # 双组+杀组+单双+大小
  miss = api.get_miss_stats()         # 遗漏统计
  dragons = api.get_dragons()        # 长龙监控
  all_data = api.get_all()            # 一次性全拉（推荐页面初始化）
"""

import json
import time
import math
import hashlib
import random
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple

# ============================================================
# 依赖处理（兼容 requests / urllib）
# ============================================================
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    import urllib.request
    import urllib.parse
    import ssl
    HAS_REQUESTS = False

# ============================================================
# 配置
# ============================================================
CONFIG = {
    # 主源（免费，推荐）
    "primary_base": "https://pc28.help/api",
    # 备用源
    "backup_base": "http://api.pgsoft.one/api/28",
    "backup2_base": "http://www.28api.com/api/v1",
    "backup3_base": "https://api.byw.bet/api",
    # 超时（秒）
    "timeout": 8,
    # 重试次数
    "max_retries": 2,
    # 缓存TTL（秒）
    "cache_ttl": 3,
    # 轮询间隔（秒）
    "poll_interval": 5,
    # 开奖间隔（秒）
    "draw_interval": 210,
}

# 环境变量覆盖
import os
CONFIG["timeout"] = int(os.environ.get("PC28_TIMEOUT", CONFIG["timeout"]))
CONFIG["cache_ttl"] = int(os.environ.get("PC28_CACHE_TTL", CONFIG["cache_ttl"]))
CONFIG["token_28api"] = os.environ.get("PC28_TOKEN_28API", "")
CONFIG["token_byw"] = os.environ.get("PC28_TOKEN_BYW", "")

BJT = timezone(timedelta(hours=8))

# ============================================================
# HTTP 工具
# ============================================================
class HTTPClient:
    """统一 HTTP 客户端，支持重试 + 超时"""

    def __init__(self, timeout=8, max_retries=2):
        self.timeout = timeout
        self.max_retries = max_retries
        self._session = None
        if HAS_REQUESTS:
            self._session = requests.Session()
            self._session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/125.0.0.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            })

    def get(self, url: str, params: Optional[dict] = None,
            extra_headers: Optional[dict] = None,
            timeout: Optional[int] = None) -> str:
        """GET 请求，带重试和超时"""
        to = timeout or self.timeout
        last_err = None

        for attempt in range(self.max_retries + 1):
            try:
                if HAS_REQUESTS:
                    headers = {}
                    if extra_headers:
                        headers.update(extra_headers)
                    r = self._session.get(
                        url, params=params, headers=headers,
                        timeout=to, verify=False
                    )
                    r.raise_for_status()
                    return r.text
                else:
                    full_url = url
                    if params:
                        full_url += "?" + urllib.parse.urlencode(params)
                    req = urllib.request.Request(full_url)
                    req.add_header("User-Agent", "Mozilla/5.0")
                    if extra_headers:
                        for k, v in extra_headers.items():
                            req.add_header(k, v)
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    with urllib.request.urlopen(req, timeout=to, context=ctx) as resp:
                        return resp.read().decode("utf-8")
            except Exception as e:
                last_err = e
                if attempt < self.max_retries:
                    # 指数退避
                    sleep_s = 0.5 * (2 ** attempt) + random.uniform(0, 0.3)
                    time.sleep(sleep_s)

        raise RuntimeError(f"HTTP失败(重试{self.max_retries}次): {url} → {last_err}")

    def get_json(self, url: str, params=None, extra_headers=None) -> dict:
        """GET 并解析 JSON"""
        text = self.get(url, params, extra_headers)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            raise RuntimeError(f"非JSON响应: {url} → {text[:200]}")


# ============================================================
# 缓存层
# ============================================================
class TTLCache:
    """简单的内存缓存，支持TTL"""

    def __init__(self, default_ttl=3):
        self._store: Dict[str, Tuple[Any, float]] = {}
        self._ttl = default_ttl
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key in self._store:
                val, exp = self._store[key]
                if time.time() < exp:
                    return val
                del self._store[key]
            return None

    def set(self, key: str, val: Any, ttl: Optional[int] = None) -> None:
        with self._lock:
            t = ttl or self._ttl
            self._store[key] = (val, time.time() + t)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


# ============================================================
# 降级器
# ============================================================
class FallbackChain:
    """多源降级：依次尝试，第一个成功即用"""

    def __init__(self, cache: TTLCache, http: HTTPClient):
        self.cache = cache
        self.http = http

    def fetch(self, key: str, url_list: List[str],
              parser, ttl: Optional[int] = None) -> Any:
        """
        key: 缓存键
        url_list: 按优先级排列的 URL 列表
        parser: func(raw_data) -> 标准化结果
        """
        # 检查缓存
        cached = self.cache.get(key)
        if cached is not None:
            return cached

        errors = []
        for url in url_list:
            try:
                data = self.http.get_json(url)
                result = parser(data)
                if result is not None:
                    self.cache.set(key, result, ttl)
                    return result
            except Exception as e:
                errors.append(f"  {url[:60]} → {str(e)[:80]}")

        raise RuntimeError(f"所有数据源不可用 [{key}]:\n" + "\n".join(errors))


# ============================================================
# 数据解析器（统一输出格式）
# ============================================================
def _extract_items(data: dict) -> List[dict]:
    """从各种API返回结构中提取items列表"""
    if not isinstance(data, dict):
        return []
    items = data.get("data") or data.get("list") or data.get("results") or data.get("items") or []
    if not items and isinstance(data, list):
        items = data
    return items


def _parse_item(item: dict, fallback_nbr: str = "") -> Optional[dict]:
    """通用：从一条记录里提取标准字段"""
    try:
        nbr = str(item.get("nbr") or item.get("issue") or item.get("period")
                   or item.get("qihao") or fallback_nbr)

        # 特码
        num_val = item.get("num") or item.get("number") or item.get("sum")
        if isinstance(num_val, str) and "+" in num_val:
            parts = num_val.split("+")
            num = sum(int(x) for x in parts if x.strip().isdigit())
        elif isinstance(num_val, str) and num_val.isdigit():
            num = int(num_val)
        elif isinstance(num_val, (int, float)):
            num = int(num_val)
        else:
            num = None

        # 三球
        nums = item.get("nums") or item.get("numbers") or item.get("raw")
        balls = []
        if isinstance(nums, str):
            balls = [int(x) for x in nums.split(",") if x.strip().isdigit()]
        elif isinstance(nums, list):
            balls = [int(x) for x in nums]

        if num is not None and 0 <= num <= 27:
            # 反推三球
            a = min(num // 9, 9)
            b = min((num % 9) // 3, 9)
            c = min(num % 3, 9)
            # 调整使 a+b+c=num
            while a + b + c > num:
                if c > 0: c -= 1
                elif b > 0: b -= 1
                else: a -= 1
            # 如果不足，补到 num
            while a + b + c < num:
                if a < 9: a += 1
                elif b < 9: b += 1
                elif c < 9: c += 1
        elif len(balls) >= 3:
            a, b, c = balls[0] % 10, balls[1] % 10, balls[2] % 10
            num = a + b + c
        else:
            return None

        combo = item.get("combination") or item.get("combo")
        if not combo:
            size = "大" if num >= 14 else "小"
            parity = "单" if num % 2 == 1 else "双"
            combo = size + parity

        return {
            "nbr": nbr,
            "date": str(item.get("date", "")),
            "time": str(item.get("time", "")),
            "b1": a, "b2": b, "b3": c,
            "sum": num,
            "combo": combo,
            "odd": num % 2 == 1,
            "big": num >= 14,
        }
    except Exception:
        return None


def _standardize_items(raw_items: List[dict]) -> List[dict]:
    """将原始 items 转成标准格式"""
    results = []
    for item in raw_items:
        parsed = _parse_item(item)
        if parsed:
            results.append(parsed)
    # 按期号排序
    results.sort(key=lambda x: x.get("nbr", ""))
    return results


# ============================================================
# 核心 API 类
# ============================================================
class PC28API:
    """
    加拿大28 统一数据接口
    所有仓库共用此模块，保证接口一致
    """

    def __init__(self, config: Optional[dict] = None):
        self.cfg = {**CONFIG, **(config or {})}
        self.http = HTTPClient(
            timeout=self.cfg["timeout"],
            max_retries=self.cfg["max_retries"],
        )
        self.cache = TTLCache(default_ttl=self.cfg["cache_ttl"])
        self.fallback = FallbackChain(self.cache, self.http)

        # URL 构建
        p = self.cfg["primary_base"]
        b = self.cfg["backup_base"]
        b2 = self.cfg["backup2_base"]
        b3 = self.cfg["backup3_base"]
        t28 = self.cfg.get("token_28api", "")
        tbyw = self.cfg.get("token_byw", "")

        # 实时开奖 URL 列表（按优先级）
        self._urls_latest = [
            f"{p}/kj.json",
            f"{b}/latest?type=canada28&limit=1",
        ]
        if tbyw:
            self._urls_latest.append(f"{b3}?token={tbyw}&t=130&p=json&limit=1")

        # 历史 URL 列表
        self._urls_history = [
            f"{p}/preview.json",
            f"{b}/history?type=canada28&page=1&limit=",
        ]
        if t28:
            self._urls_history.append(f"{b2}/canada28?token={t28}")

        # 预测 URL 列表
        self._urls_sz = [f"{p}/sz.json"]
        self._urls_sha = [f"{p}/sha.json"]
        self._urls_ds = [f"{p}/ds.json"]
        self._urls_dx = [f"{p}/dx.json"]

        # 遗漏
        self._urls_yl = [f"{p}/yl.json"]
        self._urls_yk = [f"{p}/yk.json"]

        # 长龙
        self._urls_xh = [f"{p}/xh.json"]
        self._urls_jt = [f"{p}/jt.json"]
        self._urls_abb = [f"{p}/abb.json"]
        self._urls_pl = [f"{p}/pl.json"]

        # Keno 原始
        self._urls_keno = [f"{p}/keno.json"]

    # ============================================================
    # 一、实时开奖（最核心）
    # ============================================================
    def get_latest(self, use_cache: bool = True) -> dict:
        """
        获取最新一期开奖结果（标准格式）
        返回: {nbr, date, time, b1, b2, b3, sum, combo, odd, big, countdown}
        """
        if not use_cache:
            self.cache.clear()

        def parser(data):
            # 先尝试提取 items
            items = _extract_items(data)
            if items:
                std = _standardize_items(items)
                if std:
                    latest = std[-1]
                    latest["countdown"] = data.get("countdown", "")
                    return latest
            # 直接解析（有些接口直接返回单条）
            direct = _parse_item(data)
            if direct:
                direct["countdown"] = data.get("countdown", "")
                return direct
            return None

        return self.fallback.fetch("latest", self._urls_latest, parser, ttl=3)

    # ============================================================
    # 二、历史开奖
    # ============================================================
    def get_history(self, count: int = 50, use_cache: bool = True) -> List[dict]:
        """
        获取历史开奖记录（标准格式列表）
        """
        if not use_cache:
            self.cache.clear()

        def parser(data):
            items = _extract_items(data)
            if items:
                return _standardize_items(items[-count:])
            return None

        # preview.json 是聚合接口，一次拿全
        result = self.fallback.fetch(
            f"history_{count}", self._urls_history, parser, ttl=10
        )
        return result or []

    def get_preview(self) -> dict:
        """
        聚合预览：开奖+倒计时+遗漏+预测+长龙 一次拿全
        返回完整 preview.json 结构
        """
        def parser(data):
            return data if isinstance(data, dict) and data else None

        return self.fallback.fetch("preview", [f"{self.cfg['primary_base']}/preview.json"], parser, ttl=5) or {}

    # ============================================================
    # 三、预测数据
    # ============================================================
    def get_double_group(self) -> dict:
        """双组预测 → 双组推荐"""
        def parser(data):
            return data if isinstance(data, dict) else None
        return self.fallback.fetch("sz", self._urls_sz, parser, ttl=30) or {}

    def get_kill_group(self) -> dict:
        """杀组预测 → 排除杀组"""
        def parser(data):
            return data if isinstance(data, dict) else None
        return self.fallback.fetch("sha", self._urls_sha, parser, ttl=30) or {}

    def get_ds_prediction(self) -> dict:
        """单双预测"""
        def parser(data):
            return data if isinstance(data, dict) else None
        return self.fallback.fetch("ds", self._urls_ds, parser, ttl=30) or {}

    def get_dx_prediction(self) -> dict:
        """大小预测"""
        def parser(data):
            return data if isinstance(data, dict) else None
        return self.fallback.fetch("dx", self._urls_dx, parser, ttl=30) or {}

    def get_prediction(self) -> dict:
        """一次性获取所有预测数据"""
        return {
            "double_group": self.get_double_group(),
            "kill_group": self.get_kill_group(),
            "ds": self.get_ds_prediction(),
            "dx": self.get_dx_prediction(),
        }

    # ============================================================
    # 四、统计与遗漏
    # ============================================================
    def get_miss_stats(self) -> dict:
        """号码遗漏统计（和值0-27各号码遗漏期数）"""
        def parser(data):
            return data if isinstance(data, dict) else None
        return self.fallback.fetch("yl", self._urls_yl, parser, ttl=30) or {}

    def get_today_count(self) -> dict:
        """今日已开次数"""
        def parser(data):
            return data if isinstance(data, dict) else None
        return self.fallback.fetch("yk", self._urls_yk, parser, ttl=10) or {}

    # ============================================================
    # 五、长龙监控
    # ============================================================
    def get_dragons(self) -> dict:
        """获取所有长龙数据"""
        results = {}
        for name, urls in [
            ("xh", self._urls_xh),
            ("jt", self._urls_jt),
            ("abb", self._urls_abb),
            ("pl", self._urls_pl),
        ]:
            try:
                def _parser(d, _n=name):
                    return d if isinstance(d, dict) else None
                results[name] = self.fallback.fetch(name, urls, _parser, ttl=30) or {}
            except Exception as e:
                results[name] = {"error": str(e)}
        return results

    # ============================================================
    # 六、Keno 原始数据
    # ============================================================
    def get_keno_raw(self, count: int = 60) -> List[dict]:
        """BCLC Keno 官方原始20码数据"""
        def parser(data):
            items = _extract_items(data)
            if not items:
                return None
            results = []
            for item in items[:count]:
                nums = item.get("nums") or item.get("numbers") or item.get("raw")
                if isinstance(nums, str):
                    nums = [int(x) for x in nums.split(",") if x.strip().isdigit()]
                elif isinstance(nums, list):
                    nums = [int(x) for x in nums]
                if len(nums) >= 19:
                    results.append({
                        "nbr": str(item.get("nbr", item.get("issue", ""))),
                        "raw20": sorted(nums)[:20],
                    })
            return results if results else None

        return self.fallback.fetch(f"keno_{count}", self._urls_keno, parser, ttl=10) or []

    # ============================================================
    # 七、聚合接口（推荐）
    # ============================================================
    def get_all(self) -> dict:
        """一次性拉取所有核心数据（页面初始化首选）"""
        try:
            latest = self.get_latest()
        except Exception as e:
            latest = {"error": str(e)}

        try:
            history = self.get_history(50)
        except Exception as e:
            history = []

        try:
            pred = self.get_prediction()
        except Exception:
            pred = {}

        try:
            miss = self.get_miss_stats()
        except Exception:
            miss = {}

        try:
            dragons = self.get_dragons()
        except Exception:
            dragons = {}

        return {
            "latest": latest,
            "history": history,
            "prediction": pred,
            "miss_stats": miss,
            "dragons": dragons,
            "fetched_at": datetime.now(BJT).strftime("%Y-%m-%d %H:%M:%S"),
        }

    # ============================================================
    # 八、工具方法
    # ============================================================
    def clear_cache(self) -> None:
        """清空缓存"""
        self.cache.clear()

    def health_check(self) -> dict:
        """检查各数据源健康状态"""
        results = {}
        sources = {
            "pc28.help": f"{self.cfg['primary_base']}/kj.json",
            "pgsoft": f"{self.cfg['backup_base']}/latest?type=canada28&limit=1",
        }
        for name, url in sources.items():
            try:
                start = time.time()
                self.http.get(url, timeout=5)
                elapsed = (time.time() - start) * 1000
                results[name] = {"status": "ok", "ms": round(elapsed, 1)}
            except Exception as e:
                results[name] = {"status": "fail", "error": str(e)[:80]}
        return results


# ============================================================
# 命令行测试
# ============================================================
if __name__ == "__main__":
    import sys

    api = PC28API()

    if "--health" in sys.argv:
        print("🏥 健康检查:")
        for k, v in api.health_check().items():
            if v["status"] == "ok":
                print(f"  ✅ {k}: {v['ms']}ms")
            else:
                print(f"  ❌ {k}: {v['error']}")
        sys.exit(0)

    if "--poll" in sys.argv:
        print("🔄 持续轮询（Ctrl+C 停止）...")
        last_nbr = None
        try:
            while True:
                try:
                    d = api.get_latest()
                    nbr = d.get("nbr", "?")
                    if last_nbr and nbr != last_nbr:
                        print(f"🆕 新期! 期号={nbr} 号码={d.get('b1','?')}+{d.get('b2','?')}+{d.get('b3','?')} 和值={d.get('sum','?')}")
                    elif not last_nbr:
                        print(f"📍 当前期: {nbr} 和值={d.get('sum','?')} 倒计时={d.get('countdown','?')}s")
                    last_nbr = nbr
                except Exception as e:
                    print(f"⚠️ {e}")
                time.sleep(CONFIG["poll_interval"])
        except KeyboardInterrupt:
            print("\n⏹ 停止")
        sys.exit(0)

    # 默认：拉取全部数据
    print("=" * 56)
    print("🎯 加拿大28 统一接口 — 全量拉取测试")
    print("=" * 56)

    # 1. 健康检查
    print("\n🏥 [0/7] 健康检查...")
    for k, v in api.health_check().items():
        s = "✅" if v["status"] == "ok" else "❌"
        print(f"   {s} {k}: {v.get('ms','')}{'ms' if v['status']=='ok' else v.get('error','')}")

    # 2. 实时开奖
    print("\n📅 [1/7] 实时开奖...")
    try:
        d = api.get_latest()
        print(f"   期号: {d.get('nbr','?')}")
        print(f"   号码: {d.get('b1','?')}+{d.get('b2','?')}+{d.get('b3','?')}")
        print(f"   和值: {d.get('sum','?')}  组合: {d.get('combo','?')}")
        print(f"   倒计时: {d.get('countdown','?')}s")
    except Exception as e:
        print(f"   ❌ {e}")

    # 3. 双组预测
    print("\n🎯 [2/7] 双组预测...")
    try:
        sz = api.get_double_group()
        print(f"   {json.dumps(sz, ensure_ascii=False)[:200]}")
    except Exception as e:
        print(f"   ❌ {e}")

    # 4. 杀组预测
    print("\n🚫 [3/7] 杀组预测...")
    try:
        sha = api.get_kill_group()
        print(f"   {json.dumps(sha, ensure_ascii=False)[:200]}")
    except Exception as e:
        print(f"   ❌ {e}")

    # 5. 遗漏统计
    print("\n📊 [4/7] 遗漏统计...")
    try:
        yl = api.get_miss_stats()
        print(f"   {json.dumps(yl, ensure_ascii=False)[:200]}")
    except Exception as e:
        print(f"   ❌ {e}")

    # 6. 长龙
    print("\n🐉 [5/7] 长龙监控...")
    try:
        dr = api.get_dragons()
        for k, v in dr.items():
            s = "✅" if "error" not in v else "❌"
            print(f"   {s} {k}: {json.dumps(v, ensure_ascii=False)[:80]}")
    except Exception as e:
        print(f"   ❌ {e}")

    # 7. 历史
    print("\n📜 [6/7] 历史开奖（最近5期）...")
    try:
        hist = api.get_history(5)
        for h in hist[-5:]:
            print(f"   {h.get('nbr','')}  {h.get('b1','?')}+{h.get('b2','?')}+{h.get('b3','?')}  ={h.get('sum','?')}  {h.get('combo','')}")
    except Exception as e:
        print(f"   ❌ {e}")

    # 8. 聚合
    print("\n📦 [7/7] 聚合接口 (preview.json)...")
    try:
        pv = api.get_preview()
        keys = list(pv.keys())[:10]
        print(f"   包含字段: {keys}")
    except Exception as e:
        print(f"   ❌ {e}")

    print("\n" + "=" * 56)
    print("✅ 测试完成")
    print("=" * 56)
