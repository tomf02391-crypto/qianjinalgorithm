#!/usr/bin/env python3
"""
fetch_data.py - 从 pc28.help 获取真实开奖数据
用于 GitHub Actions 定时更新 data.json

注意：pc28.help 使用 Cloudflare WAF，对部分服务端IP返回403
解决策略：
1. 优先直连
2. 失败则尝试代理列表
3. 最终降级：保留现有 data.json 不变
"""
import urllib.request
import json
import time
import os
import sys
import socket
from datetime import datetime

API_URL = "https://pc28.help/api/keno.json"
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")
MAX_HISTORY = 500

# 代理列表（按优先级排列）
# GitHub Actions 的 IP 可能被 CF 拦截，用代理绕过
PROXY_LIST = [
    None,  # 先试直连
    "http://proxy.poiuy.bid:3128",   # 备用代理1
    "http://45.77.50.133:3128",      # 备用代理2
]

# BCLK Keno 算法常量
SMALL_ODD = {1, 3, 5, 7, 9, 11, 13}
SMALL_EVEN = {0, 2, 4, 6, 8, 10, 12}
BIG_ODD = {15, 17, 19, 21, 23, 25, 27}
BIG_EVEN = {14, 16, 18, 20, 22, 24, 26}

STRAIGHT_SET = {
    "1,2,3", "3,2,1", "2,3,4", "4,3,2", "3,4,5", "5,4,3",
    "4,5,6", "6,5,4", "6,7,8", "8,7,6", "7,8,9", "9,8,7"
}

def calc_balls(raw_nums):
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
    return {"oddEven": odd_even, "bigSmall": big_small, "combo": combo, "extreme": extreme, "shape": shape}

def fetch_with_proxy(url, proxy=None, timeout=15):
    """通过可选代理获取 JSON"""
    handlers = []
    if proxy:
        from urllib.request import ProxyHandler
        handlers.append(ProxyHandler({"http": proxy, "https": proxy}))
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://pc28.help/",
        "Origin": "https://pc28.help"
    })
    with opener.open(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

def fetch_latest():
    """尝试多种策略获取最新数据"""
    last_err = None
    for proxy in PROXY_LIST:
        try:
            label = "直连" if proxy is None else f"代理({proxy})"
            print(f"  🔗 尝试{label}...", end=" ")
            json_data = fetch_with_proxy(API_URL, proxy=proxy)
            if json_data.get("message") == "success" and json_data.get("data"):
                print("✅ 成功")
                return json_data
            else:
                print(f"⚠️ 返回异常: {json_data.get('message','?')}")
                last_err = json_data.get("message", "未知")
        except Exception as e:
            print(f"❌ {e}")
            last_err = str(e)
            continue
    raise RuntimeError(f"所有获取方式均失败，最后错误: {last_err}")

def load_existing():
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
        print(f"⚠️ 读取现有 data.json 失败: {e}", file=sys.stderr)
        return []

def save_data(data):
    data.sort(key=lambda x: int(x["nbr"]))
    if len(data) > MAX_HISTORY:
        data = data[-MAX_HISTORY:]
    output = {
        "source": "pc28.help",
        "updated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count": len(data),
        "data": data
    }
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    return len(data)

def convert_record(rec):
    nbrs_str = rec.get("nbrs", "")
    nbrs = [int(x.strip()) for x in nbrs_str.split(",") if x.strip()]
    if len(nbrs) < 19:
        raise ValueError(f"号码数量不足: {len(nbrs)}")
    result = calc_balls(nbrs)
    an = analyze(result["b1"], result["b2"], result["b3"], result["total"])
    return {
        "nbr": str(rec["nbr"]),
        "date": rec.get("date", ""),
        "time": rec.get("time", ""),
        "a": result["b1"],
        "b": result["b2"],
        "c": result["b3"],
        "number": f"{result['b1']}+{result['b2']}+{result['b3']}={result['total']}",
        "sum": result["total"],
        "combo": an["combo"],
        "size": an["bigSmall"],
        "parity": an["oddEven"],
        "shape": an["shape"],
        "extreme": an["extreme"],
        "rawNums": nbrs,
        "bonus": int(rec["bonus"]) if rec.get("bonus") else 0,
        "countdown": rec.get("countdown", "")
    }

def main():
    print("🔍 正在从 pc28.help 获取数据...")
    existing = load_existing()
    seen = set(item["nbr"] for item in existing)
    print(f"📦 已有 {len(existing)} 期数据")

    new_count = 0
    try:
        json_data = fetch_latest()
        for rec in json_data["data"]:
            nbr = str(rec["nbr"])
            if nbr in seen:
                print(f"  ⏭️ 期号{nbr} 已存在，跳过")
                continue
            try:
                std = convert_record(rec)
                existing.append(std)
                seen.add(nbr)
                new_count += 1
                print(f"  ✅ 新增: 期号{nbr} | {std['date']} {std['time']} | {std['number']} | {std['combo']}")
            except Exception as e:
                print(f"  ⚠️ 解析期号{nbr}失败: {e}", file=sys.stderr)
    except Exception as e:
        print(f"❌ 数据获取失败: {e}", file=sys.stderr)
        if existing:
            print(f"📌 保留现有 {len(existing)} 期数据不变")
            save_data(existing)  # 更新时间戳
        sys.exit(0)

    if new_count > 0:
        total = save_data(existing)
        print(f"\n✅ 新增 {new_count} 期，共 {total} 期数据已保存")
    else:
        print(f"\n📌 无新数据（已有 {len(existing)} 期已是最新）")
        save_data(existing)

    if existing:
        latest = existing[-1]
        print(f"📌 最新: 期号{latest['nbr']} | {latest['date']} {latest['time']} | {latest['number']} | {latest['combo']}")

if __name__ == "__main__":
    main()
