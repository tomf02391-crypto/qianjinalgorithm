#!/usr/bin/env python3
"""
fetch_data.py — V9真数据版
从 pc28.help 拉取真实PC28数据 + V9预测
关键修复：
  1. 正确解析 kj.json 格式（number=特码字符串）
  2. 正确解析 keno.json 格式（20码原始数据）
  3. 绝不生成假数据，失败就保留旧数据
  4. 记录每期预测的对错
降级策略: pc28.help/kj → pc28.help/keno → yu28.top → 保留旧数据
"""

import json
import sys
import os
import time
import random
from datetime import datetime, timedelta
from pathlib import Path

try:
    import requests
    HAS_REQUESTS = True
except:
    import urllib.request
    import ssl
    HAS_REQUESTS = False

# ============================================================
# HTTP
# ============================================================
def http_get(url, timeout=10):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Referer": "https://pc28.help/",
    }
    if HAS_REQUESTS:
        r = requests.get(url, headers=headers, timeout=timeout, verify=False)
        r.raise_for_status()
        return r.text
    else:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            return resp.read().decode("utf-8")

# ============================================================
# 解析工具
# ============================================================
def combo_of(sum_val):
    if sum_val >= 14:
        return "大单" if sum_val % 2 == 1 else "大双"
    return "小单" if sum_val % 2 == 1 else "小双"

def decompose_sum(s):
    """从特码反推最可能的三球组合"""
    results = []
    for a in range(10):
        for b in range(10):
            for c in range(10):
                if a + b + c == s:
                    sorted_combo = sorted([a, b, c])
                    results.append(tuple(sorted_combo))
    # 去重
    seen = set()
    unique = []
    for r in results:
        if r not in seen:
            seen.add(r)
            unique.append(r)
    # 优先对子/豹子
    unique.sort(key=lambda x: (not (x[0]==x[1] or x[1]==x[2]), x[0]))
    return list(unique[0]) if unique else [0, 0, 0]

def calc_from_raw(nums):
    """从20码计算三球"""
    sorted_nums = sorted(nums)
    b1, b2, b3 = sorted_nums[0], sorted_nums[1], sorted_nums[2]
    total = b1 + b2 + b3
    return {"b1": b1, "b2": b2, "b3": b3, "sum": total, "combo": combo_of(total)}

# ============================================================
# 接口1: kj.json → {countdown, data:[{nbr,date,time,number,num,combination}], message}
# ============================================================
def fetch_kj(url="https://pc28.help/api/kj.json?nbr=60"):
    text = http_get(url)
    data = json.loads(text)
    
    # 检查是否被Cloudflare拦截
    if "title" in data and data.get("status") == 403:
        raise RuntimeError(f"Cloudflare拦截: {data.get('detail','')}")
    
    items = data.get("data") or data.get("list") or data.get("results") or []
    if not items and isinstance(data, list):
        items = data
    if not items:
        raise ValueError(f"kj.json 无数据, keys={list(data.keys()) if isinstance(data,dict) else type(data)}")
    
    parsed = []
    for item in items:
        try:
            nbr = str(item.get("nbr") or item.get("issue") or item.get("period") or "")
            # number 或 num 是特码
            num_val = item.get("number") or item.get("num") or item.get("sum") or item.get("value")
            if num_val is None:
                continue
            sum_val = int(num_val)
            if sum_val < 0 or sum_val > 27:
                continue
            
            date_str = item.get("date") or item.get("draw_date") or ""
            time_str = item.get("time") or item.get("draw_time") or ""
            combo_str = item.get("combination") or item.get("combo") or combo_of(sum_val)
            
            # 从特码反推三球
            balls = decompose_sum(sum_val)
            
            parsed.append({
                "nbr": nbr,
                "date": date_str,
                "time": time_str,
                "raw": balls,
                "b1": balls[0], "b2": balls[1], "b3": balls[2],
                "sum": sum_val,
                "combo": combo_str,
                "odd": sum_val % 2 == 1,
                "big": sum_val >= 14,
            })
        except Exception:
            continue
    
    if not parsed:
        raise ValueError("kj.json 解析后无有效数据")
    
    parsed.sort(key=lambda x: x.get("nbr", ""))
    return parsed

# ============================================================
# 接口2: keno.json → 20码原始数据
# ============================================================
def fetch_keno(url="https://pc28.help/api/keno.json?count=60"):
    text = http_get(url)
    data = json.loads(text)
    
    if "title" in data and data.get("status") == 403:
        raise RuntimeError(f"Cloudflare拦截: {data.get('detail','')}")
    
    items = data.get("data") or data.get("list") or data.get("results") or []
    if not items and isinstance(data, list):
        items = data
    if not items:
        raise ValueError(f"keno.json 无数据")
    
    parsed = []
    for item in items:
        try:
            nbr = str(item.get("nbr") or item.get("issue") or item.get("period") or "")
            
            # 获取20码
            nums = item.get("nums") or item.get("numbers") or item.get("raw") or item.get("num")
            if isinstance(nums, str):
                nums = [int(x) for x in nums.split(",") if x.strip().isdigit()]
            elif isinstance(nums, list):
                nums = [int(x) for x in nums]
            else:
                continue
            
            if len(nums) < 19:
                # 如果num是特码字符串（不是20码），尝试另一种解析
                num_val = item.get("number") or item.get("sum")
                if num_val is not None:
                    sum_val = int(num_val)
                    if 0 <= sum_val <= 27:
                        balls = decompose_sum(sum_val)
                        parsed.append({
                            "nbr": nbr,
                            "date": item.get("date", ""),
                            "time": item.get("time", ""),
                            "raw": balls,
                            "b1": balls[0], "b2": balls[1], "b3": balls[2],
                            "sum": sum_val,
                            "combo": combo_of(sum_val),
                            "odd": sum_val % 2 == 1,
                            "big": sum_val >= 14,
                        })
                continue
            
            info = calc_from_raw(nums)
            parsed.append({
                "nbr": nbr,
                "date": item.get("date", ""),
                "time": item.get("time", ""),
                "raw": nums,
                "b1": info["b1"], "b2": info["b2"], "b3": info["b3"],
                "sum": info["sum"],
                "combo": info["combo"],
                "odd": info["sum"] % 2 == 1,
                "big": info["sum"] >= 14,
            })
        except Exception:
            continue
    
    if not parsed:
        raise ValueError("keno.json 解析后无有效数据")
    
    parsed.sort(key=lambda x: x.get("nbr", ""))
    return parsed

# ============================================================
# 接口3: yu28.top 备用
# ============================================================
def fetch_yu28(url="https://www.yu28.top/api/v1/pc28/history?limit=60"):
    text = http_get(url)
    data = json.loads(text)
    
    if "title" in data and data.get("status") == 403:
        raise RuntimeError(f"Cloudflare拦截: {data.get('detail','')}")
    
    items = data.get("data") or data.get("list") or data.get("results") or []
    if not items and isinstance(data, list):
        items = data
    if not items:
        raise ValueError("yu28.top 无数据")
    
    parsed = []
    for item in items:
        try:
            nbr = str(item.get("nbr") or item.get("issue") or "")
            nums = item.get("num") or item.get("numbers") or item.get("raw") or ""
            if isinstance(nums, str):
                nums_list = [int(x) for x in nums.split(",") if x.strip().isdigit()]
            elif isinstance(nums, list):
                nums_list = [int(x) for x in nums]
            else:
                continue
            
            if len(nums_list) >= 19:
                info = calc_from_raw(nums_list)
            elif len(nums_list) == 1:
                # 可能是特码
                s = nums_list[0]
                if 0 <= s <= 27:
                    balls = decompose_sum(s)
                    info = {"b1": balls[0], "b2": balls[1], "b3": balls[2], "sum": s, "combo": combo_of(s)}
                else:
                    continue
            else:
                continue
            
            parsed.append({
                "nbr": nbr,
                "date": item.get("date", ""),
                "time": item.get("time", ""),
                "raw": nums_list if len(nums_list) >= 19 else decompose_sum(info["sum"]),
                "b1": info["b1"], "b2": info["b2"], "b3": info["b3"],
                "sum": info["sum"],
                "combo": info["combo"],
                "odd": info["sum"] % 2 == 1,
                "big": info["sum"] >= 14,
            })
        except Exception:
            continue
    
    if not parsed:
        raise ValueError("yu28.top 解析后无有效数据")
    
    parsed.sort(key=lambda x: x.get("nbr", ""))
    return parsed

# ============================================================
# V9 预测算法（与前端JS版一致）
# ============================================================
def gaussian_probs(center, sigma):
    probs = {}
    for x in range(28):
        d = x - center
        probs[x] = math.exp(-d * d / (2 * sigma * sigma))
    return probs

def normalize(probs):
    total = sum(probs.values()) or 1
    return {k: v / total for k, v in probs.items()}

def signal_ema(data, alpha=0.3):
    if not data: return {}
    ema = data[0]["sum"]
    for d in data[1:]:
        ema = alpha * d["sum"] + (1 - alpha) * ema
    return gaussian_probs(round(ema), 2.0)

def signal_double_ema(data):
    if len(data) < 3: return {}
    e1 = e2 = data[0]["sum"]
    for d in data[1:]:
        e1 = 0.3 * d["sum"] + 0.7 * e1
        e2 = 0.15 * e1 + 0.85 * e2
    c = max(0, min(27, round(e1 + (e1 - e2))))
    return gaussian_probs(c, 1.5)

def signal_weighted_freq(data, decay=0.95):
    if not data: return {}
    weights = [decay ** (len(data) - 1 - i) for i in range(len(data))]
    counts = {}
    for i, d in enumerate(data):
        counts[d["sum"]] = counts.get(d["sum"], 0) + weights[i]
    total = sum(counts.values()) or 1
    return {x: counts.get(x, 0) / total for x in range(28)}

def signal_markov1(data):
    if len(data) < 5: return {}
    trans = {}
    for i in range(len(data) - 1):
        k = data[i]["sum"]
        nxt = data[i + 1]["sum"]
        if k not in trans: trans[k] = {}
        trans[k][nxt] = trans[k].get(nxt, 0) + 1
    last = data[-1]["sum"]
    if last not in trans: return {}
    c = trans[last]
    total = sum(c.values()) or 1
    return {x: c.get(x, 0) / total for x in range(28)}

def signal_diff_reversal(data):
    if len(data) < 6: return {}
    diffs = [data[i]["sum"] - data[i-1]["sum"] for i in range(1, len(data))]
    recent = diffs[-5:]
    avg = sum(recent) / len(recent)
    center = max(0, min(27, round(data[-1]["sum"] - avg * 0.5)))
    return gaussian_probs(center, 1.0)

def signal_combo_constraint(data):
    if len(data) < 10: return {}
    combos = [combo_of(d["sum"]) for d in data[-30:]]
    counts = {}
    for c in combos:
        counts[c] = counts.get(c, 0) + 1
    top = max(counts, key=counts.get)
    return {x: 1.0 if combo_of(x) == top else 0.01 for x in range(28)}

def v9_predict(data):
    if not data:
        return {
            "tricode_main": [13, 14, 15], "tricode_backup": [10, 17],
            "tricode_kill": [0, 1, 2, 26, 27],
            "combo_push": ["小单", "大双"], "combo_kill": "大单",
            "sum_center": 13, "sum_range": [10, 17], "confidence": 15,
        }
    
    signals = {
        "ema": normalize(signal_ema(data)),
        "double_ema": normalize(signal_double_ema(data)),
        "freq": normalize(signal_weighted_freq(data)),
        "mk1": normalize(signal_markov1(data)),
        "diff": normalize(signal_diff_reversal(data)),
        "combo": normalize(signal_combo_constraint(data)),
    }
    
    weights = {"ema": 3.0, "double_ema": 2.0, "freq": 2.5, "mk1": 2.0, "diff": 1.5, "combo": 1.2}
    
    fused = {x: 0.0 for x in range(28)}
    total_w = 0
    for name, probs in signals.items():
        if not probs: continue
        w = weights.get(name, 1.0)
        for x in range(28):
            fused[x] += probs.get(x, 0) * w
        total_w += w
    if total_w > 0:
        for x in range(28):
            fused[x] /= total_w
    
    # 主推3
    ranked = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)
    main3 = [kv[0] for kv in ranked[:3]]
    backup2 = [kv[0] for kv in ranked[3:5]]
    
    # 杀5（理论概率 + 反向融合）
    theo = {}
    for x in range(28):
        count = sum(1 for a in range(10) for b in range(10) for c in range(10) if a+b+c == x)
        theo[x] = count / 1000
    combined = {x: (1 - fused.get(x, 0)) * 0.5 + theo[x] * 0.5 for x in range(28)}
    kill5 = [kv[0] for kv in sorted(combined.items(), key=lambda kv: kv[1])[:5]]
    
    # 组合
    combo_counts = {}
    for d in data[-20:]:
        c = d["combo"]
        combo_counts[c] = combo_counts.get(c, 0) + 1
    combo_ranked = sorted(combo_counts.items(), key=lambda kv: kv[1], reverse=True)
    push2 = [kv[0] for kv in combo_ranked[:2]]
    kill1 = combo_ranked[-1][0] if combo_ranked else "大单"
    
    # 和值中心
    ema = data[0]["sum"]
    for d in data[1:]:
        ema = 0.3 * d["sum"] + 0.7 * ema
    center = round(ema)
    variance = sum((d["sum"] - ema) ** 2 for d in data[-20:]) / min(20, len(data))
    spread = max(2, round((variance ** 0.5) * 0.8))
    lo = max(0, center - spread)
    hi = min(27, center + spread)
    
    # 置信度
    entropy = -sum(p * (math.log2(p) if p > 0 else 0) for p in fused.values())
    max_e = math.log2(28)
    consistency = 1 - entropy / max_e
    conf = min(55, max(15, round(ranked[0][1] * 30 + consistency * 15)))
    
    return {
        "tricode_main": main3,
        "tricode_backup": backup2,
        "tricode_kill": kill5,
        "combo_push": push2,
        "combo_kill": kill1,
        "sum_center": center,
        "sum_range": [lo, hi],
        "confidence": conf,
    }

# ============================================================
# 对错记录
# ============================================================
def update_records(data, pred, old_records):
    """对比预测和实际结果，更新记录"""
    if not pred or not data:
        return old_records
    
    latest = data[-1]
    nbr = latest["nbr"]
    
    # 检查是否已有
    if any(r.get("nbr") == nbr for r in old_records):
        return old_records
    
    main_hit = latest["sum"] in pred["tricode_main"]
    backup_hit = latest["sum"] in pred["tricode_backup"]
    kill_correct = latest["sum"] not in pred["tricode_kill"]
    combo_hit = latest["combo"] in pred["combo_push"]
    
    record = {
        "nbr": nbr,
        "sum": latest["sum"],
        "combo": latest["combo"],
        "main_hit": main_hit,
        "backup_hit": backup_hit,
        "kill_correct": kill_correct,
        "combo_hit": combo_hit,
        "main_pred": pred["tricode_main"],
        "kill_pred": pred["tricode_kill"],
        "date": latest.get("date", ""),
    }
    old_records.append(record)
    return old_records[-100:]  # 保留最近100期

# ============================================================
# 主流程
# ============================================================
import math

def main():
    print("=" * 55)
    print("🔄 V9 真数据抓取 + 预测 + 对错记录")
    print("=" * 55)
    
    data = None
    source = ""
    errors = []
    
    # 尝试顺序: kj → keno → yu28
    attempts = [
        ("pc28.help/kj", lambda: fetch_kj()),
        ("pc28.help/keno", lambda: fetch_keno()),
        ("yu28.top", lambda: fetch_yu28()),
    ]
    
    for name, func in attempts:
        try:
            print(f"\n📡 尝试 {name} ...")
            result = func()
            if result and len(result) > 0:
                data = result
                source = name
                print(f"  ✅ 成功! {len(data)}期")
                print(f"  最新: 期{data[-1]['nbr']} 特码{data[-1]['sum']} {data[-1]['combo']}")
                break
        except Exception as e:
            msg = str(e)[:100]
            errors.append(f"{name}: {msg}")
            print(f"  ❌ {msg}")
    
    if not data:
        print(f"\n⚠️ 所有接口失败:")
        for e in errors:
            print(f"  {e}")
        print("  保留旧数据不更新")
        return
    
    # 数据校验
    valid = []
    for d in data:
        if d["sum"] < 0 or d["sum"] > 27: continue
        if d["b1"] + d["b2"] + d["b3"] != d["sum"]: continue
        if not d.get("date") and not d.get("time"):
            # 至少要有期号和特码
            pass
        valid.append(d)
    
    print(f"\n📊 有效数据: {len(valid)}期 (来源: {source})")
    
    if len(valid) < 5:
        print("⚠️ 数据不足5期，跳过预测")
        pred = None
    else:
        pred = v9_predict(valid)
        print(f"\n🎯 V9 预测:")
        print(f"  主推: {pred['tricode_main']}")
        print(f"  候补: {pred['tricode_backup']}")
        print(f"  杀5:  {pred['tricode_kill']}")
        print(f"  押2组: {pred['combo_push']}")
        print(f"  杀1组: {pred['combo_kill']}")
        print(f"  和值: {pred['sum_center']} 区间{pred['sum_range']}")
        print(f"  置信度: {pred['confidence']}%")
    
    # 更新对错记录
    records_path = Path(__file__).parent / "records.json"
    old_records = []
    if records_path.exists():
        try:
            with open(records_path) as f:
                old_records = json.load(f)
        except:
            old_records = []
    
    new_records = update_records(valid, pred, old_records)
    
    # 统计
    if new_records:
        main_hits = sum(1 for r in new_records if r.get("main_hit"))
        backup_hits = sum(1 for r in new_records if r.get("backup_hit"))
        kill_correct = sum(1 for r in new_records if r.get("kill_correct"))
        total = len(new_records)
        print(f"\n📈 对错记录 (共{total}期):")
        print(f"  主推命中: {main_hits}/{total} ({main_hits/total*100:.1f}%)")
        print(f"  含候补: {main_hits+backup_hits}/{total} ({(main_hits+backup_hits)/total*100:.1f}%)")
        print(f"  杀特码正确: {kill_correct}/{total} ({kill_correct/total*100:.1f}%)")
    
    # 写入 data.json
    output = {
        "meta": {
            "source": source,
            "count": len(valid),
            "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "engine": "V9",
            "records_total": len(new_records),
        },
        "history": valid,
        "prediction": pred,
        "records": new_records[-20:],  # 最近20期记录
    }
    
    out_path = Path(__file__).parent / "data.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    # 写入 records.json
    with open(records_path, "w", encoding="utf-8") as f:
        json.dump(new_records, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 已写入 {out_path} ({out_path.stat().st_size} bytes)")
    print(f"✅ 已写入 {records_path}")

if __name__ == "__main__":
    main()
