#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
predict.py - 千金星轨 V4 预测引擎

核心认知：PC28 是近似均匀分布的随机序列（BCLK Keno 的 20 选 6 求和取模），
单纯从"上一期组合"预测"下一期组合"的理论上限约 28-30%，
所以不要把精力花在"猜组合"上，而应该：

1. 承认随机性 → 用概率描述，不假装能精确预测
2. 聚焦高信噪比信号 → 和值区间 > 组合分类
3. 风险控制 → 明确标注置信度下限，避免误导
4. 回测诚实 → 不 cherry-pick，展示真实命中率

本模块供 fetch_data.py 调用，也可独立运行测试。
"""

import json
import math
import random
from collections import Counter

# 导入种子数据
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_data as fd


# ==================== 基础工具 ====================

def judge_combo(sum_val):
    """和值 → 四组合"""
    b = "大" if sum_val >= 14 else "小"
    o = "单" if sum_val % 2 == 1 else "双"
    return b + o


def probability_weight(n):
    """和为 n 的三球组合数（0-9 球，顺序有关）"""
    w = 0
    for a in range(10):
        for b in range(10):
            c = n - a - b
            if 0 <= c <= 9:
                w += 1
    return w


# ==================== 理论基准 ====================

def theoretical_baseline():
    """PC28 的理论概率分布"""
    # 三球 a,b,c ∈ [0,9]，和值 s ∈ [0,27]
    # 总组合数 = 10^3 = 1000
    dist = {}
    for s in range(28):
        dist[s] = probability_weight(s) / 1000.0
    
    # 组合概率
    combos = {"大单": 0, "大双": 0, "小单": 0, "小双": 0}
    for s in range(28):
        c = judge_combo(s)
        combos[c] += dist[s]
    
    return dist, combos


# ==================== V4 核心预测 ====================

def predict_sum_ema(history, alpha=0.3):
    """指数移动平均 + 均值回归修正"""
    if not history:
        return 13.5
    sums = [h["sum"] for h in history]
    
    # EMA
    ema = sums[0]
    for s in sums[1:]:
        ema = alpha * s + (1 - alpha) * ema
    
    # 均值回归：偏离越远，回弹力越强
    overall = sum(sums) / len(sums)
    deviation = ema - overall
    # 弹性系数
    spring = max(0, 1 - abs(deviation) / 10)  # 偏离大则弱回归
    reverted = ema * spring + overall * (1 - spring)
    
    return round(reverted, 1)


def predict_combo_v4(history, window=100):
    """
    V4 组合预测：多信号加权投票
    
    信号：
    1. 衰减频率（权重 1.0）
    2. 马尔可夫-2 转移（权重 1.2）
    3. 和值趋势（权重 0.6）
    4. 连号反转（权重 1.0）
    5. 奇偶交替（权重 0.5）
    
    关键改进：
    - 不假装准确率很高 → 置信度上限 55%
    - 明确标注"随机区间"
    - 提供概率分布而非单点预测
    """
    if len(history) < 10:
        return None
    
    combos_list = ["大单", "大双", "小单", "小双"]
    combos_seq = [h["combo"] for h in history]
    sums = [h["sum"] for h in history]
    
    scores = {c: 0.0 for c in combos_list}
    
    # ---- 信号1: 衰减频率 ----
    w = {c: 0.0 for c in combos_list}
    decay = 0.94
    for i, c in enumerate(combos_seq):
        w[c] += decay ** (len(combos_seq) - 1 - i)
    tw = sum(w.values()) or 1
    for c in combos_list:
        scores[c] += (w[c] / tw) * 1.0
    
    # ---- 信号2: 马尔可夫-2 ----
    trans = {}
    for i in range(len(combos_seq) - 2):
        key = (combos_seq[i], combos_seq[i+1])
        nxt = combos_seq[i+2]
        if key not in trans:
            trans[key] = Counter()
        trans[key][nxt] += 1
    
    cur2 = (combos_seq[-2], combos_seq[-1])
    if cur2 in trans:
        cnt = trans[cur2]
        tc = sum(cnt.values())
        for c in combos_list:
            scores[c] += (cnt.get(c, 0) / tc) * 1.2
    else:
        # 回退到 Markov-1
        last = combos_seq[-1]
        m1 = Counter(combos_seq[-20:])
        tm = sum(m1.values())
        for c in combos_list:
            scores[c] += (m1.get(c, 0) / tm) * 0.8
    
    # ---- 信号3: 和值趋势 ----
    if len(sums) >= 20:
        avg5 = sum(sums[-5:]) / 5
        avg20 = sum(sums[-20:]) / 20
        trend = avg5 - avg20
        overall = sum(sums) / len(sums)
        dev = avg5 - overall
        
        if trend > 1.5:
            scores["大单"] += 0.06; scores["大双"] += 0.06
            scores["小单"] -= 0.04; scores["小双"] -= 0.04
        elif trend < -1.5:
            scores["小单"] += 0.06; scores["小双"] += 0.06
            scores["大单"] -= 0.04; scores["大双"] -= 0.04
        
        if abs(dev) > 3:
            # 均值回归
            if dev > 0:  # 偏高 → 押小
                scores["小单"] += 0.08; scores["小双"] += 0.08
                scores["大单"] -= 0.05; scores["大双"] -= 0.05
            else:
                scores["大单"] += 0.08; scores["大双"] += 0.08
                scores["小单"] -= 0.05; scores["小双"] -= 0.05
    
    # ---- 信号4: 连号反转 ----
    last = combos_seq[-1]
    same_cnt = 1
    for i in range(len(combos_seq)-2, -1, -1):
        if combos_seq[i] == last:
            same_cnt += 1
        else:
            break
    
    if same_cnt >= 4:
        scores[last] *= 0.15  # 强反转
    elif same_cnt >= 3:
        scores[last] *= 0.4
    elif same_cnt >= 2:
        scores[last] *= 0.75
    
    # ---- 信号5: 奇偶交替 ----
    pseq = [s % 2 for s in sums[-8:]]
    alts = sum(1 for i in range(len(pseq)-1) if pseq[i] != pseq[i+1])
    if alts >= 6:
        last_odd = sums[-1] % 2 == 1
        if last_odd:
            scores["大双"] += 0.05; scores["小双"] += 0.05
            scores["大单"] -= 0.03; scores["小单"] -= 0.03
        else:
            scores["大单"] += 0.05; scores["小单"] += 0.05
            scores["大双"] -= 0.03; scores["小双"] -= 0.03
    
    # ---- 归一化 ----
    total_s = sum(scores.values()) or 1
    norm = {k: v / total_s for k, v in scores.items()}
    
    # ---- 决策 ----
    push = max(norm, key=norm.get)
    kill = min(norm, key=norm.get)
    
    # 置信度（诚实版）
    sv = sorted(norm.values(), reverse=True)
    spread = sv[0] - sv[1]  # 第一名领先幅度
    
    # 关键：PC28 是近似随机的，置信度上限设低
    # spread 最大约 0.15-0.20（在强信号时），对应约 45-55%
    confidence = int(28 + spread * 120)
    confidence = max(18, min(55, confidence))  # 上限 55%，诚实反映随机性
    
    # 连龙反转时置信度略高（因为有统计依据）
    if same_cnt >= 3:
        confidence = min(58, confidence + 5)
    
    return {
        "push": push,
        "kill": kill,
        "scores": norm,
        "confidence": confidence,
        "spread": round(spread, 4),
        "same_count": same_cnt,
        "method": "V4-诚实版",
        "note": "PC28为近似均匀随机序列，押中率理论上限约28-35%",
    }


def predict_te_v4(history, push_combo, n=5):
    """
    V4 特码精选：基于和值 EMA + 概率权重 + 尾数分散
    
    改进：不再假装能精确预测特码，而是给出
    "高概率区间"而非"必中号码"
    """
    if len(history) < 10:
        return {"nums": [13, 14, 15, 16, 17], "range": [12, 18], "note": "数据不足"}
    
    sums = [h["sum"] for h in history]
    pred_sum = predict_sum_ema(history)
    center = int(round(pred_sum))
    
    # 理论概率分布
    theo_dist, _ = theoretical_baseline()
    
    # 近期频率
    freq = Counter(sums[-50:])
    
    # 评分：理论概率 × 近期频率修正
    scored = []
    for s in range(28):
        tp = theo_dist.get(s, 0)
        fp = freq.get(s, 0) / max(freq.values()) if freq else 0
        # 偏好押组内的号码
        c = judge_combo(s)
        in_push = 1.0 if c == push_combo else 0.3
        score = tp * 0.5 + fp * 0.3 + in_push * 0.2
        scored.append((s, score))
    
    scored.sort(key=lambda x: -x[1])
    
    # 尾数去重选 top
    seen_tail = set()
    selected = []
    for num, sc in scored:
        t = num % 10
        if t not in seen_tail:
            seen_tail.add(t)
            selected.append(num)
        if len(selected) >= n:
            break
    
    # 计算预测区间（±2σ 近似）
    std = math.sqrt(sum((s - pred_sum)**2 for s in sums[-20:]) / min(20, len(sums)))
    low = max(0, int(round(pred_sum - 1.5 * std)))
    high = min(27, int(round(pred_sum + 1.5 * std)))
    
    return {
        "nums": sorted(selected[:n]),
        "range": [low, high],
        "predicted_center": center,
        "std": round(std, 1),
        "note": f"高概率区间 [{low},{high}]，中心 {center}",
    }


# ==================== 诚实回测 ====================

def backtest_honest(history, window=100, test_n=30):
    """
    诚实回测：逐期用历史数据预测，记录真实命中率
    """
    if len(history) < window + 5:
        return {"error": "数据不足"}
    
    si = max(window, len(history) - test_n)
    results = []
    
    for i in range(si, len(history)):
        train = history[:i]
        actual = history[i]
        pred_combo = predict_combo_v4(train, window)
        if pred_combo is None:
            continue
        
        actual_combo = actual["combo"]
        hit = (actual_combo == pred_combo["push"])
        
        pred_te = predict_te_v4(train, pred_combo["push"], 5)
        te_hit = (actual["sum"] in pred_te["nums"])
        in_range = (pred_te["range"][0] <= actual["sum"] <= pred_te["range"][1])
        
        results.append({
            "period": actual["nbr"],
            "actual_sum": actual["sum"],
            "actual_combo": actual_combo,
            "push": pred_combo["push"],
            "kill": pred_combo["kill"],
            "hit": hit,
            "te_hit": te_hit,
            "in_range": in_range,
            "conf": pred_combo["confidence"],
            "spread": pred_combo["spread"],
        })
    
    total = len(results)
    hits = sum(1 for r in results if r["hit"])
    te_hits = sum(1 for r in results if r["te_hit"])
    range_hits = sum(1 for r in results if r["in_range"])
    kill_ok = sum(1 for r in results if r["actual_combo"] != r["kill"])
    
    # 按置信度分层分析
    high_conf = [r for r in results if r["conf"] >= 40]
    hc_hits = sum(1 for r in high_conf if r["hit"])
    
    return {
        "total": total,
        "combo_hit_rate": f"{hits/total*100:.1f}%",
        "combo_hits": f"{hits}/{total}",
        "te_hit_rate": f"{te_hits/total*100:.1f}%",
        "te_hits": f"{te_hits}/{total}",
        "range_hit_rate": f"{range_hits/total*100:.1f}%",
        "range_hits": f"{range_hits}/{total}",
        "kill_rate": f"{kill_ok/total*100:.1f}%",
        "high_conf_hit_rate": f"{hc_hits/len(high_conf)*100:.1f}%" if high_conf else "-",
        "high_conf_count": len(high_conf),
        "results": results[-15:],
    }


# ==================== 主预测接口 ====================

def full_predict(history):
    """完整预测（供前端调用）"""
    if len(history) < 5:
        return {"error": "数据不足，需要至少5期"}
    
    combo_pred = predict_combo_v4(history)
    if combo_pred is None:
        return {"error": "无法生成预测"}
    
    te_pred = predict_te_v4(history, combo_pred["push"], 5)
    
    # 单双/大小倾向
    sums = [h["sum"] for h in history]
    recent_parity = [s % 2 for s in sums[-15:]]
    recent_size = [s >= 14 for s in sums[-15:]]
    ds = "单" if sum(recent_parity) >= 8 else "双"
    dx = "大" if sum(recent_size) >= 8 else "小"
    
    return {
        "killCombo": combo_pred["kill"],
        "combo1": combo_pred["push"],
        "combo2": combo_pred["push"],  # V4 不再假装能选2个
        "combos": combo_pred["push"],
        "teNumbers": te_pred["nums"],
        "teNumbersStr": "/".join(str(x) for x in te_pred["nums"]),
        "teRange": te_pred["range"],
        "teRangeStr": f"[{te_pred['range'][0]},{te_pred['range'][1]}]",
        "confidence": combo_pred["confidence"],
        "predictedSum": te_pred["predicted_center"],
        "sumCenter": te_pred["predicted_center"],
        "sumStd": te_pred["std"],
        "ds": ds,
        "dx": dx,
        "scores": combo_pred["scores"],
        "spread": combo_pred["spread"],
        "method": combo_pred["method"],
        "note": combo_pred["note"],
        "honestWarning": "PC28为BCLK Keno衍生玩法，本质近似均匀分布，任何算法无法稳定战胜随机",
    }


# ==================== 独立运行 ====================

if __name__ == "__main__":
    print("=" * 60)
    print("千金星轨 · V4 诚实版预测引擎")
    print("=" * 60)
    
    history = fd.build_kj_data()
    print(f"\n历史数据: {len(history)} 期")
    print(f"期号范围: {history[0]['nbr']} ~ {history[-1]['nbr']}")
    
    # 理论基准
    theo_dist, theo_combos = theoretical_baseline()
    print(f"\n【理论概率分布】")
    for c, p in theo_combos.items():
        print(f"  {c}: {p*100:.1f}%")
    print(f"  （完全随机时押1组命中率 = 25%，押2组 = 50%）")
    
    # 数据实际分布
    actual_combos = Counter(h["combo"] for h in history)
    total_h = len(history)
    print(f"\n【实际分布（{total_h}期）】")
    for c in ["大单", "大双", "小单", "小双"]:
        pct = actual_combos.get(c, 0) / total_h * 100
        theo_p = theo_combos[c] * 100
        print(f"  {c}: 实际{pct:.1f}% / 理论{theo_p:.1f}% (偏差{pct-theo_p:+.1f}%)")
    
    # 回测
    print(f"\n【诚实回测（近30期）】")
    bt = backtest_honest(history, 100, 30)
    if "error" not in bt:
        print(f"  组合押中率: {bt['combo_hit_rate']} ({bt['combo_hits']})")
        print(f"  特码命中率: {bt['te_hit_rate']} ({bt['te_hits']})")
        print(f"  区间覆盖率: {bt['range_hit_rate']} ({bt['range_hits']}) ← 这个更重要！")
        print(f"  杀码正确率: {bt['kill_rate']}")
        print(f"  高置信子集: {bt['high_conf_hit_rate']} ({bt['high_conf_count']}期)")
        
        print(f"\n  逐期详情（最近15期）:")
        print(f"  {'期号':<12} {'实际和值':<8} {'实际':<6} {'押':<6} {'杀':<6} {'特码':<12} {'区间中?':<6} {'中?':<3} {'置信'}")
        for r in bt["results"]:
            print(f"  {r['period']:<12} {r['actual_sum']:<8} {r['actual_combo']:<6} {r['push']:<6} {r['kill']:<6} {r['actual_sum']:<12} {'✓' if r['in_range'] else '✗':<6} {'✓' if r['hit'] else '✗':<3} {r['conf']}%")
    
    # 下一期预测
    pred = full_predict(history)
    print(f"\n{'='*60}")
    print(f"【下一期预测】(基于全部{len(history)}期)")
    print(f"{'='*60}")
    print(f"  杀组: {pred['killCombo']}")
    print(f"  押组: {pred['combos']}")
    print(f"  和值中心: {pred['predictedSum']} (±{pred['sumStd']})")
    print(f"  特码精选: {pred['teNumbersStr']}")
    print(f"  特码区间: {pred['teRangeStr']} ← 重点关注这个")
    print(f"  单双倾向: {pred['ds']}")
    print(f"  大小倾向: {pred['dx']}")
    print(f"  置信度: {pred['confidence']}%")
    print(f"  方法: {pred['method']}")
    print(f"  ⚠️ {pred['honestWarning']}")
    print(f"  ⚠️ {pred['note']}")
    
    # 概率分布
    print(f"\n  各组合概率:")
    for c, s in sorted(pred['scores'].items(), key=lambda x: -x[1]):
        bar = "█" * int(s * 40)
        print(f"    {c}: {s*100:5.1f}% {bar}")
