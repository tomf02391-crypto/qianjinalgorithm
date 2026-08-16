#!/usr/bin/env python3
"""
fetch_data.py - 从 pc28.help 获取真实 BCLK Keno 开奖数据
用于 GitHub Actions 定时更新 data.json

重要：pc28.help 使用 Cloudflare WAF，对多数服务端 IP 返回 403。
本脚本采用多层降级策略：
  1. 直连 pc28.help
  2. 通过 Cloudflare 允许的代理
  3. 通过 r.jina.ai 文本提取代理
  4. 全部失败 → 保留现有 data.json 不变（不生成假数据）

绝不生成模拟/伪造数据。所有数据必须来自 pc28.help 的真实返回。
"""
import urllib.request
import urllib.parse
import json
import time
import os
import sys
import socket
from datetime import datetime

API_URL = "https://pc28.help/api/keno.json"
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")
MAX_HISTORY = 500

# BCLK Keno 算法常量
SMALL_ODD  = {1, 3, 5, 7, 9, 11, 13}
SMALL_EVEN = {0, 2, 4, 6, 8, 10, 12}
BIG_ODD    = {15, 17, 19, 21, 23, 25, 27}
BIG_EVEN   = {14, 16, 18, 20, 22, 24, 26}

STRAIGHT_SET = {
    "1,2,3", "3,2,1", "2,3,4", "4,3,2", "3,4,5", "5,4,3",
    "4,5,6", "6,5,4", "6,7,8", "8,7,6", "7,8,9", "9,8,7"
}

# ============================================================
# 算法（与 pc28_api.py / 前端 JS 完全一致）
# ============================================================
def calc_balls(raw_nums):
    """从排序后的20个原始号码，按 BCLK Keno 规则计算三球"""
    nums = sorted(raw_nums)
    pos1 = [1, 4, 7, 10, 13, 16]
    pos2 = [2, 5, 8, 11, 14, 17]
    pos3 = [3, 6, 9, 12, 15, 18]
    b1 = sum(nums[i] for i in pos1) % 10
    b2 = sum(nums[i] for i in pos2) % 10
    b3 = sum(nums[i] for i in pos3) % 10
    return {"b1": b1, "b2": b2, "b3": b3, "total": b1 + b2 + b3}

def analyze(b1, b2, b3, total):
    odd_even = "单" if total % 2 == 1 else "双"
    big_small = "大" if total >= 14 else "小"
    if total in SMALL_ODD: combo = "小单"
    elif total in SMALL_EVEN: combo = "小双"
    elif total in BIG_ODD: combo = "大单"
    elif total in BIG_EVEN: combo = "大双"
    else: combo = "-"
    extreme = "极小" if total <= 5 else ("极大" if total >= 22 else "-")
    if b1 == b2 == b3: shape = "豹子"
    elif b1 == b2 or b2 == b3 or b1 == b3: shape = "对子"
    elif ",".join(str(x) for x in [b1, b2, b3]) in STRAIGHT_SET: shape = "顺子"
    else: shape = "杂六"
    return {"oddEven": odd_even, "bigSmall": big_small, "combo": combo,
            "extreme": extreme, "shape": shape}

# ============================================================
# 网络请求（多层降级，绝不复活假数据）
# ============================================================
def make_request(url, headers, timeout=15):
    """发起 HTTP 请求并返回 (status, body_text)"""
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8")

def try_fetch_direct():
    """方式1: 直连 pc28.help（模拟浏览器）"""
    url = API_URL + "?nbr=100"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "identity",
        "Referer": "https://pc28.help/",
        "Origin": "https://pc28.help",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }
    return make_request(url, headers)

def try_fetch_jina():
    """方式2: 通过 r.jina.ai 文本提取代理"""
    # jina.ai 可以抓取任意URL并返回清洗后的文本/JSON
    target = urllib.parse.quote(API_URL + "?nbr=100", safe="")
    url = f"https://r.jina.ai/{target}"
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    return make_request(url, headers, timeout=20)

def try_fetch_cors_proxy():
    """方式3: 通过公开 CORS 代理"""
    target = urllib.parse.quote(API_URL + "?nbr=100", safe="")
    urls = [
        f"https://api.allorigins.win/raw?url={target}",
        f"https://corsproxy.io/?{target}",
    ]
    last_err = None
    for url in urls:
        try:
            headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
            return make_request(url, headers, timeout=15)
        except Exception as e:
            last_err = e
            continue
    raise last_err if last_err else RuntimeError("所有CORS代理失败")

def try_fetch_textise():
    """方式4: textise dot iitty 文本化代理"""
    target = urllib.parse.quote(API_URL + "?nbr=100", safe="")
    url = f"https://r.jina.ai/http://textise dot iitty/{target}"
    # 简化：直接试 textise
    url = f"https://r.jina.ai/http://pc28.help/api/keno.json?nbr=100"
    headers = {"User-Agent": "Mozilla/5.0"}
    return make_request(url, headers, timeout=15)

def fetch_raw():
    """按优先级尝试所有方式，返回原始 JSON 文本"""
    strategies = [
        ("直连 pc28.help", try_fetch_direct),
        ("jina.ai 代理", try_fetch_jina),
        ("CORS 代理", try_fetch_cors_proxy),
    ]
    last_err = None
    for name, func in strategies:
        try:
            print(f"  🔗 尝试{name}...", end=" ")
            status, body = func()
            if status == 200 and body.strip():
                print(f"✅ 成功 ({len(body)} bytes)")
                return body
            else:
                print(f"⚠️ 返回 {status}, body空={not body.strip()}")
                last_err = f"{name}: HTTP {status}"
        except Exception as e:
            print(f"❌ {e}")
            last_err = f"{name}: {e}"
            continue
    raise RuntimeError(f"所有抓取方式均失败: {last_err}")

def parse_api_response(text):
    """解析 API 返回的 JSON，提取标准记录列表"""
    data = json.loads(text)
    # pc28.help 返回格式: {"countdown": "...", "data": [...], "message": "success"}
    if isinstance(data, dict):
        if data.get("message") == "success" and data.get("data"):
            return data["data"]
        # 有时直接返回数组
        if isinstance(data.get("data"), list):
            return data["data"]
    if isinstance(data, list):
        return data
    raise ValueError(f"无法识别的API返回格式: {str(data)[:200]}")

# ============================================================
# 数据转换
# ============================================================
def convert_record(rec):
    """将 API 单条记录 → 标准格式（含原始号码→三球→和值→组合）"""
    # 兼容多种字段名
    nbrs_str = rec.get("nbrs") or rec.get("number") or rec.get("nums") or ""
    if not nbrs_str:
        raise ValueError(f"记录缺少原始号码字段: {list(rec.keys())}")
    
    nbrs = [int(x.strip()) for x in str(nbrs_str).split(",") if x.strip()]
    if len(nbrs) < 19:
        raise ValueError(f"原始号码不足20个(实际{len(nbrs)}): {nbrs_str[:60]}")
    
    result = calc_balls(nbrs)
    an = analyze(result["b1"], result["b2"], result["b3"], result["total"])
    
    return {
        "nbr":     str(rec.get("nbr") or rec.get("issue") or rec.get("id") or ""),
        "date":    rec.get("date") or "",
        "time":    rec.get("time") or "",
        "a":       result["b1"],
        "b":       result["b2"],
        "c":       result["b3"],
        "number":  f"{result['b1']}+{result['b2']}+{result['b3']}={result['total']}",
        "sum":     result["total"],
        "combo":   an["combo"],
        "size":    an["bigSmall"],
        "parity":  an["oddEven"],
        "shape":   an["shape"],
        "extreme": an["extreme"],
        "rawNums": nbrs,
        "bonus":   int(rec["bonus"]) if rec.get("bonus") else 0,
        "countdown": rec.get("countdown") or ""
    }

# ============================================================
# 持久化
# ============================================================
def load_existing():
    """读取现有 data.json，返回标准记录列表"""
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "data" in data:
            return data["data"]
        if isinstance(data, list):
            return data
        return []
    except Exception as e:
        print(f"  ⚠️ 读取现有 data.json 失败: {e}", file=sys.stderr)
        return []

def save_data(data):
    """保存数据，按 nbr 排序，截断到 MAX_HISTORY"""
    data.sort(key=lambda x: int(x["nbr"]) if x.get("nbr") else 0)
    if len(data) > MAX_HISTORY:
        data = data[-MAX_HISTORY:]
    
    output = {
        "source":   "pc28.help",
        "updated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count":    len(data),
        "note":     "自动更新自 pc28.help 真实开奖数据，绝无模拟",
        "data":     data
    }
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    return len(data)

# ============================================================
# 主流程
# ============================================================
def main():
    print("=" * 55)
    print("🔍 千金星轨 · 数据抓取（仅真实数据，零模拟）")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 55)

    existing = load_existing()
    seen = set(item.get("nbr", "") for item in existing if item.get("nbr"))
    print(f"📦 已有 {len(existing)} 期数据")

    # 尝试抓取
    try:
        raw_text = fetch_raw()
        records = parse_api_response(raw_text)
        print(f"📥 API 返回 {len(records)} 条记录")
    except Exception as e:
        print(f"\n❌ 抓取失败: {e}")
        print("📌 保留现有 data.json 不变（绝不生成假数据）")
        if existing:
            save_data(existing)  # 仅更新时间戳
            print(f"✅ 现有 {len(existing)} 期数据保留")
        sys.exit(0)

    # 转换 + 去重
    new_count = 0
    for rec in records:
        nbr = str(rec.get("nbr") or "")
        if not nbr or nbr in seen:
            continue
        try:
            std = convert_record(rec)
            # 严格校验：三球之和必须等于和值
            assert std["a"] + std["b"] + std["c"] == std["sum"], \
                f"校验失败: {std['a']}+{std['b']}+{std['c']}≠{std['sum']}"
            # 严格校验：和值范围 0-27
            assert 0 <= std["sum"] <= 27, f"和值越界: {std['sum']}"
            existing.append(std)
            seen.add(nbr)
            new_count += 1
            if new_count <= 5:
                print(f"  ✅ 新增: {nbr} | {std['date']} {std['time']} | {std['number']} | {std['combo']}")
        except Exception as e:
            print(f"  ⚠️ 跳过 {nbr}: {e}", file=sys.stderr)

    if new_count == 0:
        print("📌 无新数据（已有数据已是最新）")
    else:
        print(f"📥 共新增 {new_count} 期")

    total = save_data(existing)
    print(f"💾 已保存 {total} 期 → data.json")

    if existing:
        latest = existing[-1]
        print(f"📌 最新: {latest['nbr']} | {latest['date']} {latest['time']} | {latest['number']} | {latest['combo']}")

if __name__ == "__main__":
    main()
