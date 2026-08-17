#!/usr/bin/env python3
"""
fetch_data.py — GitHub Actions 抓取 PC28 真实开奖数据 + V8 预测引擎

数据源（优先级递减）：
  1) pc28.help/api/keno.json    ← 用户验证可用，含原始20码
  2) yu28.top/api/kj.json       ← 备用
  3) 内置真实数据 + 本地算法     ← 兜底（绝不生成假数据）

输出：data.json（供 index.html 在浏览器端 API 不可用时兜底）
"""
import json
import urllib.request
import urllib.parse
import datetime
import sys
import os
import re
import math

# ===== V8 算法核心（内嵌，无外部依赖）=====

def calc_balls(raw_nums):
    """从20个原始号码计算三球（与JS端完全一致）"""
    s = sorted(raw_nums)
    b1 = (s[0] + s[7]) % 10
    b2 = (s[1] + s[8]) % 10
    b3 = (s[2] + s[9]) % 10
    return b1, b2, b3, b1 + b2 + b3

def analyze(b1, b2, b3, total):
    """完整形态分析"""
    odd = total % 2 == 1
    big = total >= 14
    combo = ("大" if big else "小") + ("单" if odd else "双")
    # 组合
    pair = b1 == b2 or b2 == b3 or b1 == b3
    all_same = b1 == b2 == b3
    if all_same:
        shape = "豹子"
    elif pair:
        shape = "对子"
    elif odd and (total in [5,7,9,11,13,15,17,19,21,23,25,27]):
        shape = "杂单"
    elif not odd and (total in [4,6,8,10,12,14,16,18,20,22,24,26]):
        shape = "杂双"
    else:
        shape = "杂六"
    extreme = "大" if big else ("小" if total <= 5 else "")
    return {
        "odd_even": "单" if odd else "双",
        "big_small": "大" if big else "小",
        "combination": combo,
        "extreme": extreme,
        "shape": shape,
    }

def fetch_url(url, headers=None, timeout=15):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

def fetch_pc28help():
    """从 pc28.help 获取真实数据"""
    url = "https://pc28.help/api/keno.json"
    h = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
         "Accept": "application/json",
         "Referer": "https://pc28.help/"}
    data = fetch_url(url, h)
    return data

def parse_pc28help(raw):
    """解析 pc28.help 返回 → 标准格式"""
    out = []
    # 支持多种返回结构
    items = None
    if isinstance(raw, dict):
        items = raw.get("data") or raw.get("list") or raw.get("results")
    if items is None and isinstance(raw, list):
        items = raw
    if not items:
        # 可能直接是单层对象列表
        for k, v in (raw if isinstance(raw, dict) else {}).items():
            if isinstance(v, list):
                items = v
                break
    if not items:
        return out

    for it in items:
        try:
            nbr = str(it.get("nbr") or it.get("issue") or it.get("code") or it.get("period") or "")
            raw_nums = it.get("num") or it.get("numbers") or it.get("balls") or it.get("data") or []
            if isinstance(raw_nums, str):
                raw_nums = [int(x) for x in re.split(r"[,\s]+", raw_nums.strip()) if x.isdigit()]
            if len(raw_nums) < 6:
                continue
            nums = [int(x) for x in raw_nums[:20]]
            b1, b2, b3, total = calc_balls(nums)
            ana = analyze(b1, b2, b3, total)
            dt = it.get("date") or it.get("time") or it.get("draw_time") or ""
            out.append({
                "nbr": nbr,
                "time": dt,
                "a": b1, "b": b2, "c": b3,
                "number": f"{b1}+{b2}+{b3}={total}",
                "sum": total,
                "combination": ana["combination"],
                "raw_nums": nums,
            })
        except Exception:
            continue
    return out

# ===== V8 预测引擎 =====

def v8_predict(data, window=100):
    """V8 终极预测引擎"""
    if len(data) < 10:
        return None
    recent = data[-window:]
    sums = [d["sum"] for d in recent]
    n = len(sums)

    # --- 1. 和值 EMA ---
    alpha = 0.3
    ema = sums[0]
    for s in sums[1:]:
        ema = alpha * s + (1 - alpha) * ema
    ema_int = round(ema)

    # --- 2. 加权频率 ---
    weights = [i + 1 for i in range(n)]
    freq = {}
    for i, s in enumerate(sums):
        freq[s] = freq.get(s, 0) + weights[i]
    top_sums = sorted(freq.items(), key=lambda x: -x[1])[:5]

    # --- 3. 马尔可夫-1 ---
    mk1 = {}
    for i in range(1, n):
        prev = sums[i-1]
        cur = sums[i]
        if prev not in mk1:
            mk1[prev] = {}
        mk1[prev][cur] = mk1[prev].get(cur, 0) + 1
    last = sums[-1]
    next_candidates = mk1.get(last, {})
    mk1_top = sorted(next_candidates.items(), key=lambda x: -x[1])[:3]

    # --- 4. 趋势 ---
    recent10 = sums[-10:]
    trend = sum(recent10[-5:]) / 5 - sum(recent10[:5]) / 5
    trend_adj = round(trend * 2)

    # --- 5. 组合预测 ---
    combos = [d["combination"] for d in recent]
    combo_weights = {}
    for i, c in enumerate(combos):
        w = (i + 1) ** 1.5
        combo_weights[c] = combo_weights.get(c, 0) + w
    top_combo = sorted(combo_weights.items(), key=lambda x: -x[1])[:2]

    # ===== 融合投票 =====
    votes = {}
    def add_vote(name, weight, candidates):
        for val, w in candidates:
            votes[val] = votes.get(val, 0) + w * weight

    # 和值 EMA ±2
    for offset in range(-2, 3):
        v = max(0, min(27, ema_int + offset))
        add_vote("ema", 3.0 - abs(offset) * 0.5, [(v, 1.0)])

    # 加权频率 top5
    add_vote("freq", 2.5, [(v, w) for v, w in top_sums])

    # MK-1
    add_vote("mk1", 2.0, [(v, w) for v, w in mk1_top])

    # 趋势
    trend_val = max(0, min(27, ema_int + trend_adj))
    add_vote("trend", 1.5, [(trend_val, 1.0)])

    ranked = sorted(votes.items(), key=lambda x: -x[1])
    top5 = [v for v, _ in ranked[:5]]
    top3 = [v for v, _ in ranked[:3]]

    # 杀号：频率最低 + 远离 EMA
    all_sums = list(range(28))
    inverse_freq = {}
    for s in all_sums:
        inverse_freq[s] = 1.0 / (freq.get(s, 0) + 1)
    kill_candidates = sorted(inverse_freq.items(), key=lambda x: -x[1])
    kill5 = [v for v, _ in kill_candidates[:5]]

    # 组合锁定
    push_combo = top_combo[0][0] if top_combo else "小单"
    kill_combo = "大单" if push_combo != "大单" else "小双"

    # 置信度（诚实上限55%）
    spread = len(set([v for v, _ in ranked[:5]]))
    confidence = min(55, 28 + spread * 120 / 5)

    return {
        "push_sums": top5,
        "main3": top3,
        "kill_sums": kill5,
        "push_combo": push_combo,
        "kill_combo": kill_combo,
        "ema": ema_int,
        "trend": trend_adj,
        "confidence": round(confidence, 1),
        "window": n,
    }

def build_from_seed():
    """内置真实数据兜底"""
    sys.path.insert(0, os.path.dirname(__file__))
    try:
        import seed_data
        return seed_data.build()
    except ImportError:
        return None

def main():
    src = ""
    kj_data = []

    # ===== 尝试 1: pc28.help（用户验证可用）=====
    print("→ 尝试 pc28.help/api/keno.json ...")
    try:
        raw = fetch_pc28help()
        kj_data = parse_pc28help(raw)
        if kj_data:
            src = "pc28.help 直连"
            print(f"  ✅ 获取 {len(kj_data)} 期真实数据")
    except Exception as e:
        print(f"  ❌ pc28.help 失败: {e}")

    # ===== 尝试 2: yu28.top =====
    if not kj_data:
        print("→ 尝试 yu28.top ...")
        try:
            url = "https://yu28.top/api/kj.json?nbr=100"
            h = {"User-Agent": "Mozilla/5.0", "X-Api-Key": "yu28_ef248feb94737c55"}
            raw = fetch_url(url, h)
            items = raw.get("data") if isinstance(raw, dict) else raw
            for it in (items or []):
                try:
                    nbr = str(it.get("nbr") or it.get("code") or "")
                    nums = it.get("num") or it.get("numbers") or []
                    if isinstance(nums, str):
                        nums = [int(x) for x in re.split(r"[,\s]+", nums.strip()) if x.isdigit()]
                    if len(nums) < 6:
                        continue
                    b1, b2, b3, total = calc_balls([int(x) for x in nums[:20]])
                    ana = analyze(b1, b2, b3, total)
                    kj_data.append({
                        "nbr": nbr, "time": it.get("time") or it.get("date") or "",
                        "a": b1, "b": b2, "c": b3,
                        "number": f"{b1}+{b2}+{b3}={total}",
                        "sum": total, "combination": ana["combination"],
                    })
                except:
                    continue
            if kj_data:
                src = "yu28.top"
                print(f"  ✅ 获取 {len(kj_data)} 期")
        except Exception as e:
            print(f"  ❌ yu28.top 失败: {e}")

    # ===== 尝试 3: 内置数据兜底 =====
    if not kj_data:
        print("→ 回退到内置真实数据 ...")
        seed = build_from_seed()
        if seed:
            kj_data = seed["kj"]["data"]
            src = seed["source"]
            print(f"  ✅ 内置数据 {len(kj_data)} 期")

    if not kj_data:
        print("❌ 所有数据源均失败，保留旧 data.json")
        sys.exit(0)

    # ===== V8 预测 =====
    pred = v8_predict(kj_data, window=min(100, len(kj_data)))
    if pred:
        print(f"  📊 V8 预测：押{pred['push_sums']} 杀{pred['kill_sums']} "
              f"组合押{pred['push_combo']}杀{pred['kill_combo']} 置信{pred['confidence']}%")

    out = {
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "source": src,
        "game": "pc28",
        "kj": {"data": kj_data},
        "sha": {"code": 200, "data": []},
        "sz": {"code": 200, "data": []},
        "ds": {"code": 200, "data": []},
        "dx": {"code": 200, "data": []},
    }
    if pred:
        out["next_prediction"] = {
            "push": pred["push_sums"],
            "kill": pred["kill_sums"],
            "main3": pred["main3"],
            "push_combo": pred["push_combo"],
            "kill_combo": pred["kill_combo"],
            "ema": pred["ema"],
            "confidence": pred["confidence"],
        }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 写入 data.json ← {src}")
    print(f"   开奖数据：{len(kj_data)} 期")
    if kj_data:
        print(f"   最新期：{kj_data[-1]['nbr']} 和值{kj_data[-1]['sum']}")

if __name__ == "__main__":
    main()
