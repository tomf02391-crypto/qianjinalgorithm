"""
pc28_standard_api.py — 加拿大28 统一数据接口（Python 版）
=================================================================
数据源优先级：pc28.help → pgsoft.one → 28api.com → byw.bet
功能：多源降级、缓存、超时重试、统一输出格式

使用：
    from pc28_standard_api import PC28API
    api = PC28API()
    data = api.get_latest()
"""

import json
import time
import requests
from typing import Optional, Dict, Any, List

# ============================================================
# 配置
# ============================================================
CONFIG = {
    "primary": "https://pc28.help/api",
    "backup1": "http://api.pgsoft.one/api/28",
    "backup2": "http://www.28api.com/api/v1",
    "backup3": "https://api.byw.bet/api",
    "timeout": 8,
    "cache_ttl": 3,
}


# ============================================================
# 工具函数
# ============================================================
def _normalize(raw: Any, source: str = "") -> Optional[Dict]:
    """统一输出格式"""
    if not raw:
        return None

    # 单条记录
    if isinstance(raw, dict):
        nums = raw.get("numbers") or raw.get("opencode") or []
        if isinstance(nums, str):
            nums = [int(x) for x in nums.split("+") if x.strip().isdigit()]
        b1 = int(nums[0]) if len(nums) > 0 else int(raw.get("num1", 0))
        b2 = int(nums[1]) if len(nums) > 1 else int(raw.get("num2", 0))
        b3 = int(nums[2]) if len(nums) > 2 else int(raw.get("num3", 0))
        s = int(raw.get("sum", b1 + b2 + b3))
        return {
            "nbr": str(raw.get("period") or raw.get("issue") or raw.get("nbr") or ""),
            "b1": b1, "b2": b2, "b3": b3,
            "sum": s,
            "combo": raw.get("combo") or raw.get("combination") or "",
            "size": raw.get("size") or ("大" if s >= 14 else "小"),
            "parity": raw.get("parity") or ("双" if s % 2 == 0 else "单"),
            "countdown": raw.get("countdown", 0),
            "source": source or raw.get("_source", ""),
        }

    # 列表取第一条
    if isinstance(raw, list) and len(raw) > 0:
        return _normalize(raw[0], source)

    return None


# ============================================================
# 主类
# ============================================================
class PC28API:
    """加拿大28 统一数据接口"""

    def __init__(self, token_28api: str = "", token_byw: str = ""):
        self.token_28api = token_28api
        self.token_byw = token_byw
        self._cache: Dict[str, Any] = {}
        self._cache_time: Dict[str, float] = {}

    def _is_cached(self, key: str) -> bool:
        return key in self._cache and (time.time() - self._cache_time.get(key, 0)) < CONFIG["cache_ttl"]

    def _set_cache(self, key: str, val: Any):
        self._cache[key] = val
        self._cache_time[key] = time.time()

    def _fetch(self, url: str, params: Optional[Dict] = None) -> Any:
        r = requests.get(url, params=params, timeout=CONFIG["timeout"],
                         headers={"User-Agent": "PC28-Standard-API/1.0"})
        r.raise_for_status()
        return r.json()

    def _fetch_with_fallback(self, sources: List[Dict]) -> Any:
        """多源降级"""
        errors = []
        for src in sources:
            try:
                data = self._fetch(src["url"], src.get("params"))
                if data is not None:
                    return data
            except Exception as e:
                errors.append(f"{src['name']}: {e}")
        raise RuntimeError("所有数据源不可用: " + " | ".join(errors))

    # ---------- 一、实时开奖 ----------
    def get_latest(self) -> Optional[Dict]:
        key = "latest"
        if self._is_cached(key):
            return self._cache[key]
        sources = [
            {"name": "pc28.help", "url": f"{CONFIG['primary']}/kj.json"},
            {"name": "pgsoft", "url": f"{CONFIG['backup1']}/latest",
             "params": {"type": "canada28", "limit": 1}},
        ]
        raw = self._fetch_with_fallback(sources)
        data = _normalize(raw, "pc28.help" if raw else "")
        if data:
            self._set_cache(key, data)
        return data

    # ---------- 二、Keno 原始数据 ----------
    def get_keno(self) -> Optional[Dict]:
        key = "keno"
        if self._is_cached(key):
            return self._cache[key]
        try:
            data = self._fetch(f"{CONFIG['primary']}/keno.json")
            self._set_cache(key, data)
            return data
        except Exception:
            return None

    # ---------- 三、聚合预览 ----------
    def get_preview(self) -> Optional[Dict]:
        key = "preview"
        if self._is_cached(key):
            return self._cache[key]
        try:
            data = self._fetch(f"{CONFIG['primary']}/preview.json")
            self._set_cache(key, data)
            return data
        except Exception:
            return None

    # ---------- 四、历史开奖 ----------
    def get_history(self, page: int = 1, limit: int = 50) -> Any:
        key = f"hist_{page}_{limit}"
        if self._is_cached(key):
            return self._cache[key]
        sources = [
            {"name": "pgsoft", "url": f"{CONFIG['backup1']}/history",
             "params": {"type": "canada28", "page": page, "limit": limit}},
            {"name": "pc28_preview", "url": f"{CONFIG['primary']}/preview.json"},
        ]
        data = self._fetch_with_fallback(sources)
        self._set_cache(key, data)
        return data

    # ---------- 五、预测接口 ----------
    def get_double_group(self):
        try: return self._fetch(f"{CONFIG['primary']}/sz.json")
        except: return None

    def get_kill_group(self):
        try: return self._fetch(f"{CONFIG['primary']}/sha.json")
        except: return None

    def get_ds(self):
        try: return self._fetch(f"{CONFIG['primary']}/ds.json")
        except: return None

    def get_dx(self):
        try: return self._fetch(f"{CONFIG['primary']}/dx.json")
        except: return None

    # ---------- 六、统计遗漏 ----------
    def get_miss_stats(self):
        try: return self._fetch(f"{CONFIG['primary']}/yl.json")
        except: return None

    def get_today_count(self):
        try: return self._fetch(f"{CONFIG['primary']}/yk.json")
        except: return None

    # ---------- 七、长龙监控 ----------
    def get_dragons(self) -> Dict:
        results = {}
        for name, path in [("xh", "xh"), ("jt", "jt"), ("abb", "abb"), ("pl", "pl")]:
            try:
                results[name] = self._fetch(f"{CONFIG['primary']}/{path}.json")
            except Exception as e:
                results[name] = {"error": str(e)}
        return results

    # ---------- 八、一键全部 ----------
    def fetch_all(self) -> Dict:
        return {
            "latest": self.get_latest(),
            "preview": self.get_preview(),
            "prediction": {
                "double_group": self.get_double_group(),
                "kill_group": self.get_kill_group(),
                "ds": self.get_ds(),
                "dx": self.get_dx(),
            },
            "miss": self.get_miss_stats(),
            "dragons": self.get_dragons(),
        }


# ============================================================
# 命令行快速测试
# ============================================================
if __name__ == "__main__":
    api = PC28API()
    print("=" * 50)
    print("PC28 统一接口 - 快速测试")
    print("=" * 50)

    print("\n📅 实时开奖:")
    latest = api.get_latest()
    if latest:
        print(f"   期号: {latest.get('nbr')}")
        print(f"   号码: {latest.get('b1')}+{latest.get('b2')}+{latest.get('b3')}")
        print(f"   和值: {latest.get('sum')} ({latest.get('size')}{latest.get('parity')})")
    else:
        print("   ❌ 获取失败")

    print("\n🎯 双组预测:")
    sz = api.get_double_group()
    if sz:
        print(f"   {json.dumps(sz, ensure_ascii=False)[:200]}")
    else:
        print("   ❌ 获取失败")

    print("\n✅ 测试完成")
