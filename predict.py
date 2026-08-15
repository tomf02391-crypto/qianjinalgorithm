#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
predict.py - 本地预测算法（与前端 QianJinU 引擎逻辑一致）
供 fetch_data.py 调用，也可独立运行测试
"""

import json
import math
import random
from collections import Counter

# 导入种子数据
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_data import SEED_DATA


def judge_combo(sum_val):
    b = "大" if sum_val >= 14 else "小"
    o = "单" if sum_val % 2 == 1 else "双"
    return b + o


def probability_weight(n):
    w = 0
    for a in range(10):
        for b in range(10):
            c = n - a - b
            if 0 <= c <= 9:
                w += 1
    return w


def calc_combo_probs(history, decay=0.88):
    if not history:
        return {"大单": 0.25, "大双": 0.25, "小单": 0.25, "小双": 0.25}
    w = {"大单": 0, "大双": 0, "小单": 0, "小双": 0}
    for i, item in enumerate(history):
        wt = decay ** (len(history) - 1 - i)
        c = item.get("combination") or judge_combo(int(item.get("num", 0)))
        if c in w:
            w[c] += wt
    total = sum(w.values()) or 1
    return {k: v / total for k, v in w.items()}


def predict_kill_combo(history):
    probs = calc_combo_probs(history)
    return min(probs, key=probs.get)


def predict_pick_combos(history, n=2):
    probs = calc_combo_probs(history)
    sorted_c = sorted(probs, key=probs.get, reverse=True)
    return sorted_c[:n]


def predict_sum(history):
    if not history:
        return 13.5
    sums = [int(h["num"]) for h in history if str(h.get("num", "")).isdigit()]
    if not sums:
        return 13.5
    weights = [0.95 ** (len(sums) - 1 - i) for i in range(len(sums))]
    weighted = sum(s * w for s, w in zip(sums, weights))
    total_w = sum(weights) or 1
    return weighted / total_w


def pick_te_numbers(history, combos, n=5):
    if not history:
        return [11, 13, 14, 15, 16]
    recent = history[-30:]
    sums = [int(h["num"]) for h in recent if str(h.get("num", "")).isdigit()]
    freq = Counter(sums)
    avg = sum(sums) / len(sums) if sums else 13.5

    scored = []
    for x in range(28):
        combo = judge_combo(x)
        if combos and combo not in combos:
            continue
        pw = probability_weight(x)
        max_pw = max(probability_weight(i) for i in range(28))
        freq_score = freq.get(x, 0) / (max(freq.values()) or 1)
        pw_score = pw / (max_pw or 1)
        dist = abs(x - avg)
        center_score = math.exp(-0.5 * (dist / 5) ** 2)
        score = pw_score * 1.4 + freq_score * 1.2 + center_score * 1.0
        scored.append((x, score))

    scored.sort(key=lambda x: -x[1])

    seen_tail = set()
    result = []
    for num, _ in scored:
        if num % 10 not in seen_tail:
            seen_tail.add(num % 10)
            result.append(num)
        if len(result) >= n:
            break

    return result[:n]


def full_predict(history):
    if len(history) < 5:
        return {"error": "数据不足"}

    kill = predict_kill_combo(history)
    picks = predict_pick_combos(history, 2)
    predicted_sum = predict_sum(history)
    te = pick_te_numbers(history, picks, 5)

    probs = calc_combo_probs(history)
    max_p = max(probs.values())
    confidence = int(40 + max_p * 50 + random.randint(-5, 10))
    confidence = max(10, min(95, confidence))

    return {
        "killCombo": kill,
        "combo1": picks[0],
        "combo2": picks[1] if len(picks) > 1 else picks[0],
        "combos": "+".join(picks),
        "teNumbers": te,
        "teNumbersStr": "/".join(str(x) for x in te),
        "confidence": confidence,
        "predictedSum": round(predicted_sum, 1),
        "weightName": "本地频率+杀组反转",
    }


def backtest(history, test_count=30):
    if len(history) < test_count + 10:
        return {"error": "数据不足"}

    results = []
    si = len(history) - test_count
    for i in range(si, len(history)):
        train = history[:i]
        actual = history[i]
        pred = full_predict(train)
        if "error" in pred:
            continue
        active = [pred["combo1"], pred["combo2"]]
        actual_combo = actual.get("combination") or judge_combo(int(actual.get("num", 0)))
        is_hit = actual_combo in active
        te_hit = int(actual.get("num", -1)) in pred["teNumbers"]
        results.append({
            "period": actual["period"],
            "kill": pred["killCombo"],
            "predicted": pred["combos"],
            "te": pred["teNumbersStr"],
            "actual_sum": actual.get("num"),
            "actual_combo": actual_combo,
            "hit": is_hit,
            "te_hit": te_hit and is_hit,
        })

    total = len(results)
    hits = sum(1 for r in results if r["hit"])
    te_hits = sum(1 for r in results if r["te_hit"])
    kill_correct = sum(1 for r in results if r["actual_combo"] != r["kill"])

    return {
        "total": total,
        "hit_rate": f"{(hits/total*100):.1f}%" if total else "0%",
        "te_rate": f"{(te_hits/total*100):.1f}%" if total else "0%",
        "kill_rate": f"{(kill_correct/total*100):.1f}%" if total else "0%",
        "results": results[-10:],
    }


if __name__ == "__main__":
    print("=" * 50)
    print("千金星轨 · 本地预测算法自检")
    print("=" * 50)

    history = []
    for item in SEED_DATA:
        period, time_str, number, num, combo = item
        history.append({
            "period": period, "date": "2026-08-12",
            "time": time_str, "number": number,
            "num": str(num), "combination": combo,
        })

    print(f"\n历史数据: {len(history)} 期")

    pred = full_predict(history)
    print(f"\n📊 下一期预测:")
    print(f"   杀组: {pred['killCombo']}")
    print(f"   押组: {pred['combos']}")
    print(f"   特码: {pred['teNumbersStr']}")
    print(f"   和值: {pred['predictedSum']}")
    print(f"   置信度: {pred['confidence']}%")

    bt = backtest(history, 30)
    print(f"\n📈 回测结果 (近{bt.get('total',0)}期):")
    print(f"   组命中率: {bt.get('hit_rate','-')}")
    print(f"   特码命中率: {bt.get('te_rate','-')}")
    print(f"   杀码正确率: {bt.get('kill_rate','-')}")
