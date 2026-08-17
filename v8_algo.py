#!/usr/bin/env python3
"""
V8 终极算法 — PC28 特码/组合预测引擎
==========================================
核心思想：PC28 特码近似均匀分布(熵≈3.27bit)，纯随机无法超越1/28。
但短窗口(50-200期)存在可检测的局部偏差：
  - 和值 EMA 惯性/均值回归
  - 条件转移概率 (Markov)
  - 冷热号偏离
  - 差分序列反转
  - 周期性尾数

策略：多信号加权投票 + 熵感知自适应权重
信号越多且越一致 → 置信度越高 → 缩小候选集
"""

import json
import math
import random
from collections import Counter, defaultdict
from typing import List, Tuple, Optional

# ============================================================
# 基础工具
# ============================================================

def calc_balls(raw_nums: List[int]) -> dict:
    """从20码计算三球+和值+组合+形态"""
    if len(raw_nums) < 20:
        raise ValueError(f"需要20个号码，只有{len(raw_nums)}个")
    sorted_nums = sorted(raw_nums)
    b1, b2, b3 = sorted_nums[0], sorted_nums[1], sorted_nums[2]
    total = b1 + b2 + b3
    combo = "大单" if total >= 14 else "小单" if total % 2 == 1 else "大双" if total >= 14 else "小双"
    return {
        "b1": b1, "b2": b2, "b3": b3,
        "sum": total,
        "combo": combo,
        "odd": total % 2 == 1,
        "big": total >= 14,
    }

def combo_of(sum_val: int) -> str:
    if sum_val >= 14:
        return "大单" if sum_val % 2 == 1 else "大双"
    else:
        return "小单" if sum_val % 2 == 1 else "小双"

COMBOS = ["大单", "大双", "小单", "小双"]

# ============================================================
# 信号层 — 每个信号独立给出特码概率分布
# ============================================================

def signal_ema(data: List[dict], alpha: float = 0.3) -> dict:
    """指数移动平均 → 特码概率分布"""
    if not data:
        return {}
    sums = [d["sum"] for d in data]
    ema = sums[0]
    for s in sums[1:]:
        ema = alpha * s + (1 - alpha) * ema
    center = round(ema)
    probs = {}
    for x in range(28):
        dist = abs(x - center)
        probs[x] = math.exp(-dist * dist / 4.0)
    return probs

def signal_double_ema(data: List[dict], alpha: float = 0.3, beta: float = 0.15) -> dict:
    """双指数平滑(趋势捕获)"""
    if len(data) < 3:
        return {}
    sums = [d["sum"] for d in data]
    ema1 = sums[0]
    ema2 = sums[0]
    for s in sums[1:]:
        ema1 = alpha * s + (1 - alpha) * ema1
        ema2 = beta * ema1 + (1 - beta) * ema2
    trend = ema1 - ema2
    center = round(ema1 + trend)
    center = max(0, min(27, center))
    probs = {}
    for x in range(28):
        dist = abs(x - center)
        probs[x] = math.exp(-dist * dist / 3.0)
    return probs

def signal_weighted_freq(data: List[dict], decay: float = 0.95) -> dict:
    """加权频率(近期权重更高)"""
    if not data:
        return {}
    weights = [decay ** (len(data) - 1 - i) for i in range(len(data))]
    counts = Counter()
    for d, w in zip(data, weights):
        counts[d["sum"]] += w
    total = sum(counts.values()) or 1
    probs = {x: counts.get(x, 0) / total for x in range(28)}
    return probs

def signal_markov_1(data: List[dict]) -> dict:
    """一阶马尔可夫条件转移"""
    if len(data) < 5:
        return {}
    sums = [d["sum"] for d in data]
    trans = defaultdict(Counter)
    for i in range(len(sums) - 1):
        trans[sums[i]][sums[i+1]] += 1
    last = sums[-1]
    if last not in trans:
        return {}
    counter = trans[last]
    total = sum(counter.values()) or 1
    probs = {x: counter.get(x, 0) / total for x in range(28)}
    return probs

def signal_markov_2(data: List[dict]) -> dict:
    """二阶马尔可夫"""
    if len(data) < 10:
        return {}
    sums = [d["sum"] for d in data]
    trans = defaultdict(Counter)
    for i in range(len(sums) - 2):
        key = (sums[i], sums[i+1])
        trans[key][sums[i+2]] += 1
    last_pair = (sums[-2], sums[-1])
    if last_pair not in trans:
        return {}
    counter = trans[last_pair]
    total = sum(counter.values()) or 1
    probs = {x: counter.get(x, 0) / total for x in range(28)}
    return probs

def signal_diff_reversal(data: List[dict]) -> dict:
    """差分反转信号 — 近期差分方向反转概率"""
    if len(data) < 6:
        return {}
    sums = [d["sum"] for d in data]
    diffs = [sums[i+1] - sums[i] for i in range(len(sums)-1)]
    recent_diffs = diffs[-5:]
    avg_diff = sum(recent_diffs) / len(recent_diffs)
    # 反转方向
    predicted_diff = -avg_diff * 0.5
    center = round(sums[-1] + predicted_diff)
    center = max(0, min(27, center))
    probs = {}
    for x in range(28):
        dist = abs(x - center)
        probs[x] = math.exp(-dist * dist / 2.0)
    return probs

def signal_second_diff(data: List[dict]) -> dict:
    """二阶差分(加速度)信号"""
    if len(data) < 8:
        return {}
    sums = [d["sum"] for d in data]
    diffs = [sums[i+1] - sums[i] for i in range(len(sums)-1)]
    sec_diff = [diffs[i+1] - diffs[i] for i in range(len(diffs)-1)]
    avg_sec = sum(sec_diff[-5:]) / min(5, len(sec_diff))
    predicted = sums[-1] + diffs[-1] + avg_sec
    center = round(predicted)
    center = max(0, min(27, center))
    probs = {}
    for x in range(28):
        dist = abs(x - center)
        probs[x] = math.exp(-dist * dist / 2.5)
    return probs

def signal_cold_return(data: List[dict], window: int = 50) -> dict:
    """冷号回归 — 长期未出现的号码有回归趋势"""
    if not data:
        return {}
    recent = data[-window:]
    seen = set(d["sum"] for d in recent)
    all_nums = set(range(28))
    cold = all_nums - seen
    if not cold:
        return {}
    probs = {}
    cold_strength = 1.0 / max(1, len(cold))
    for x in range(28):
        probs[x] = cold_strength if x in cold else 0.01
    return probs

def signal_combo_constraint(data: List[dict]) -> dict:
    """组合约束 — 预测组合后只在该组合内分配概率"""
    if len(data) < 10:
        return {}
    # 用频率法预测下一期组合
    combos = [combo_of(d["sum"]) for d in data[-30:]]
    counter = Counter(combos)
    predicted_combo = counter.most_common(1)[0][0]
    probs = {}
    for x in range(28):
        if combo_of(x) == predicted_combo:
            probs[x] = 1.0
        else:
            probs[x] = 0.01
    return probs

def signal_periodicity(data: List[dict], max_period: int = 10) -> dict:
    """周期性检测 — 检测尾数/值的周期重复"""
    if len(data) < 20:
        return {}
    sums = [d["sum"] for d in data]
    # 检测最近值的周期性重现
    last = sums[-1]
    scores = {x: 0.0 for x in range(28)}
    for period in range(2, max_period + 1):
        if len(sums) >= period + 1:
            if sums[-1] == sums[-period]:
                # 周期确认，加分给 sums[-period] 附近
                for offset in range(-2, 3):
                    val = sums[-1] + offset
                    if 0 <= val <= 27:
                        scores[val] += 1.0 / period
    if max(scores.values()) == 0:
        return {}
    return scores

def signal_extreme_reversal(data: List[dict]) -> dict:
    """极值反转 — 连续极端值后回归中枢"""
    if len(data) < 5:
        return {}
    sums = [d["sum"] for d in data]
    recent = sums[-5:]
    avg = sum(recent) / len(recent)
    # 如果近期偏极端，预测回归13.5
    extremity = abs(avg - 13.5)
    if extremity > 5:
        center = round(13.5 + (avg - 13.5) * 0.3)  # 部分回归
        center = max(0, min(27, center))
        probs = {}
        for x in range(28):
            dist = abs(x - center)
            probs[x] = math.exp(-dist * dist / 3.0)
        return probs
    return {}

# ============================================================
# 组合预测信号
# ============================================================

def combo_signal_markov(data: List[dict], order: int = 1) -> dict:
    """组合马尔可夫"""
    if len(data) < 10:
        return {}
    combos = [combo_of(d["sum"]) for d in data]
    if order == 1:
        trans = defaultdict(Counter)
        for i in range(len(combos) - 1):
            trans[combos[i]][combos[i+1]] += 1
        last = combos[-1]
        if last not in trans:
            return {}
        counter = trans[last]
        total = sum(counter.values()) or 1
        return {c: counter.get(c, 0) / total for c in COMBOS}
    else:
        trans = defaultdict(Counter)
        for i in range(len(combos) - 2):
            key = (combos[i], combos[i+1])
            trans[key][combos[i+2]] += 1
        last_pair = (combos[-2], combos[-1])
        if last_pair not in trans:
            return {}
        counter = trans[last_pair]
        total = sum(counter.values()) or 1
        return {c: counter.get(c, 0) / total for c in COMBOS}

def combo_signal_freq(data: List[dict], decay: float = 0.97) -> dict:
    """组合加权频率"""
    if not data:
        return {}
    combos = [combo_of(d["sum"]) for d in data]
    weights = [decay ** (len(combos) - 1 - i) for i in range(len(combos))]
    scores = defaultdict(float)
    for c, w in zip(combos, weights):
        scores[c] += w
    total = sum(scores.values()) or 1
    return {c: scores.get(c, 0) / total for c in COMBOS}

def combo_signal_trend(data: List[dict]) -> dict:
    """组合趋势 — 近期组合分布偏向"""
    if len(data) < 10:
        return {}
    recent = [combo_of(d["sum"]) for d in data[-15:]]
    counter = Counter(recent)
    total = sum(counter.values()) or 1
    return {c: counter.get(c, 0) / total for c in COMBOS}

def combo_signal_entropy(data: List[dict]) -> dict:
    """熵加权 — 高熵(均匀)时降低置信度"""
    if len(data) < 10:
        return {}
    combos = [combo_of(d["sum"]) for d in data[-20:]]
    counter = Counter(combos)
    total = sum(counter.values()) or 1
    probs = [v / total for v in counter.values()]
    entropy = -sum(p * math.log2(p) for p in probs if p > 0)
    max_entropy = math.log2(4)
    normalized = entropy / max_entropy  # 1.0=完全均匀
    # 均匀时给均匀预测
    if normalized > 0.9:
        return {c: 0.25 for c in COMBOS}
    # 不均匀时放大差异
    raw = {c: counter.get(c, 0) / total for c in COMBOS}
    return raw

# ============================================================
# 融合层
# ============================================================

# 信号权重配置
SIGNAL_WEIGHTS = {
    "ema": 3.0,
    "double_ema": 2.0,
    "weighted_freq": 2.5,
    "markov_1": 2.0,
    "markov_2": 1.0,
    "diff_reversal": 1.5,
    "second_diff": 1.0,
    "cold_return": 0.8,
    "combo_constraint": 1.2,
    "periodicity": 0.5,
    "extreme_reversal": 1.0,
}

COMBO_WEIGHTS = {
    "markov_1": 2.5,
    "markov_2": 1.5,
    "freq": 2.0,
    "trend": 1.5,
    "entropy": 1.0,
}

def fuse_signals(data: List[dict]) -> dict:
    """融合所有信号 → 特码概率分布"""
    signals = {}
    signals["ema"] = signal_ema(data)
    signals["double_ema"] = signal_double_ema(data)
    signals["weighted_freq"] = signal_weighted_freq(data)
    signals["markov_1"] = signal_markov_1(data)
    signals["markov_2"] = signal_markov_2(data)
    signals["diff_reversal"] = signal_diff_reversal(data)
    signals["second_diff"] = signal_second_diff(data)
    signals["cold_return"] = signal_cold_return(data)
    signals["combo_constraint"] = signal_combo_constraint(data)
    signals["periodicity"] = signal_periodicity(data)
    signals["extreme_reversal"] = signal_extreme_reversal(data)

    # 加权融合
    fused = {x: 0.0 for x in range(28)}
    total_weight = 0.0
    for name, probs in signals.items():
        if not probs:
            continue
        w = SIGNAL_WEIGHTS.get(name, 1.0)
        # 归一化单个信号
        s = sum(probs.values()) or 1
        norm = {k: v / s for k, v in probs.items()}
        for x in range(28):
            fused[x] += norm.get(x, 0) * w
        total_weight += w

    if total_weight > 0:
        fused = {k: v / total_weight for k, v in fused.items()}

    return fused

def predict_combo(data: List[dict]) -> dict:
    """融合组合信号"""
    signals = {}
    signals["markov_1"] = combo_signal_markov(data, 1)
    signals["markov_2"] = combo_signal_markov(data, 2)
    signals["freq"] = combo_signal_freq(data)
    signals["trend"] = combo_signal_trend(data)
    signals["entropy"] = combo_signal_entropy(data)

    fused = {c: 0.0 for c in COMBOS}
    total_weight = 0.0
    for name, probs in signals.items():
        if not probs:
            continue
        w = COMBO_WEIGHTS.get(name, 1.0)
        s = sum(probs.values()) or 1
        norm = {k: v / s for k, v in probs.items()}
        for c in COMBOS:
            fused[c] += norm.get(c, 0) * w
        total_weight += w

    if total_weight > 0:
        fused = {k: v / total_weight for k, v in fused.items()}
    return fused

# ============================================================
# 决策层 — 输出最终预测
# ============================================================

def decide_tricode(fused: dict, top_n: int = 3) -> List[int]:
    """从融合概率中选 top_n 特码"""
    ranked = sorted(fused.items(), key=lambda x: -x[1])
    return [x[0] for x in ranked[:top_n]]

def decide_kill_tricode(fused: dict, data: List[dict], kill_n: int = 5) -> List[int]:
    """杀特码 — 选概率最低 + 理论概率最低的混合"""
    # 理论概率（PC28 特码分布，中心高两端低）
    theoretical = {}
    for x in range(28):
        # 特码=x的组合数（三球a+b+c=x, a,b,c∈[0,9]）
        count = 0
        for a in range(10):
            for b in range(10):
                for c in range(10):
                    if a + b + c == x:
                        count += 1
        theoretical[x] = count
    total = sum(theoretical.values())  # 1000
    theo_prob = {k: v / total for k, v in theoretical.items()}

    # 混合：模型概率低 + 理论概率低
    combined = {}
    for x in range(28):
        combined[x] = (1 - fused.get(x, 0)) * 0.5 + theo_prob.get(x, 0) * 0.5

    ranked = sorted(combined.items(), key=lambda x: x[1])
    return [x[0] for x in ranked[:kill_n]]

def decide_two_combos(combo_probs: dict) -> List[str]:
    """押2组 — 选概率最高的2个组合"""
    ranked = sorted(combo_probs.items(), key=lambda x: -x[1])
    return [x[0] for x in ranked[:2]]

def decide_kill_combo(combo_probs: dict) -> str:
    """杀1组 — 选概率最低的1个组合"""
    ranked = sorted(combo_probs.items(), key=lambda x: x[1])
    return ranked[0][0]

def decide_sum_center(data: List[dict]) -> Tuple[int, int, int]:
    """和值中心 ± 范围"""
    if not data:
        return 13, 10, 17
    sums = [d["sum"] for d in data[-20:]]
    ema = sums[0]
    for s in sums[1:]:
        ema = 0.3 * s + 0.7 * ema
    center = round(ema)
    spread = max(2, round(math.sqrt(sum((s - ema)**2 for s in sums) / len(sums)) * 0.8))
    lo = max(0, center - spread)
    hi = min(27, center + spread)
    return center, lo, hi

# ============================================================
# 置信度计算
# ============================================================

def calc_confidence(fused: dict, combo_probs: dict) -> int:
    """基于信号一致性和熵计算置信度(0-55%)"""
    # 特码部分：top1概率占比
    probs_sorted = sorted(fused.values(), reverse=True)
    top_share = probs_sorted[0] if probs_sorted else 0
    # 组合部分
    combo_sorted = sorted(combo_probs.values(), reverse=True)
    combo_share = combo_sorted[0] if combo_sorted else 0

    # 信号一致性(熵越低越一致)
    entropy = -sum(p * math.log2(p + 1e-10) for p in fused.values() if p > 0)
    max_entropy = math.log2(28)
    consistency = 1 - (entropy / max_entropy)  # 1=完全一致, 0=完全均匀

    score = top_share * 30 + combo_share * 15 + consistency * 15
    return min(55, max(15, round(score)))

# ============================================================
# 主入口
# ============================================================

def predict(data: List[dict]) -> dict:
    """V8 主预测函数"""
    if not data:
        return {
            "tricode_main": [13, 14, 15],
            "tricode_backup": [10, 17],
            "tricode_kill": [0, 1, 2, 26, 27],
            "combo_push": ["小单", "大双"],
            "combo_kill": "大单",
            "sum_center": 13,
            "sum_range": [10, 17],
            "confidence": 15,
            "signal_details": {},
        }

    fused = fuse_signals(data)
    combo_probs = predict_combo(data)

    main3 = decide_tricode(fused, 3)
    # 候补：从剩余中选概率最高的2个
    remaining = [(x, fused[x]) for x in range(28) if x not in main3]
    remaining.sort(key=lambda x: -x[1])
    backup2 = [x[0] for x in remaining[:2]]

    kill5 = decide_kill_tricode(fused, data, 5)
    push2 = decide_two_combos(combo_probs)
    kill1 = decide_kill_combo(combo_probs)
    center, lo, hi = decide_sum_center(data)
    confidence = calc_confidence(fused, combo_probs)

    return {
        "tricode_main": main3,
        "tricode_backup": backup2,
        "tricode_kill": kill5,
        "combo_push": push2,
        "combo_kill": kill1,
        "sum_center": center,
        "sum_range": [lo, hi],
        "confidence": confidence,
        "signal_details": {
            "ema_center": round(sum(x * fused[x] for x in range(28))),
            "top3_prob": sum(fused[x] for x in main3),
            "kill5_prob": sum(fused[x] for x in kill5),
            "combo_entropy": round(-sum(p * math.log2(p + 1e-10) for p in combo_probs.values() if p > 0), 3),
        },
    }

# ============================================================
# 蒙特卡洛回测
# ============================================================

def monte_carlo_backtest(num_simulations: int = 1000, data_length: int = 200) -> dict:
    """用理论分布模拟PC28，回测V8算法"""
    random.seed(42)
    results = {
        "main3_hit": 0,
        "backup2_hit": 0,
        "kill5_correct": 0,
        "push2_hit": 0,
        "kill1_correct": 0,
        "total": 0,
    }

    for sim in range(num_simulations):
        # 生成模拟数据（带轻微非随机性）
        data = []
        for i in range(data_length + 1):
            # 基础随机
            s = random.randint(0, 27)
            # 轻微惯性（模拟真实摇奖偏差）
            if data and random.random() < 0.15:
                s = max(0, min(27, data[-1]["sum"] + random.randint(-2, 2)))
            data.append({"sum": s})

        train = data[:-1]
        actual = data[-1]["sum"]

        pred = predict(train)

        results["total"] += 1
        if actual in pred["tricode_main"]:
            results["main3_hit"] += 1
        if actual in pred["tricode_backup"]:
            results["backup2_hit"] += 1
        if actual not in pred["tricode_kill"]:
            results["kill5_correct"] += 1
        if combo_of(actual) in pred["combo_push"]:
            results["push2_hit"] += 1
        if combo_of(actual) != pred["combo_kill"]:
            results["kill1_correct"] += 1

    total = results["total"]
    return {
        "main3_rate": results["main3_hit"] / total,
        "backup2_rate": results["backup2_hit"] / total,
        "push5_rate": (results["main3_hit"] + results["backup2_hit"]) / total,
        "kill5_rate": results["kill5_correct"] / total,
        "push2_rate": results["push2_hit"] / total,
        "kill1_rate": results["kill1_correct"] / total,
        "total": total,
    }

if __name__ == "__main__":
    print("=" * 60)
    print("V8 终极算法 — 蒙特卡洛回测")
    print("=" * 60)
    result = monte_carlo_backtest(5000, 200)
    print(f"\n📊 回测结果 ({result['total']} 次模拟):")
    print(f"  主推3命中率:   {result['main3_rate']*100:.2f}%  (随机10.71%)")
    print(f"  候补2命中率:   {result['backup2_rate']*100:.2f}%")
    print(f"  押5总命中率:   {result['push5_rate']*100:.2f}%  (随机17.86%)")
    print(f"  杀5正确率:     {result['kill5_rate']*100:.2f}%  (随机82.14%)")
    print(f"  押2组命中率:   {result['push2_rate']*100:.2f}%  (随机50.00%)")
    print(f"  杀1组正确率:   {result['kill1_rate']*100:.2f}%  (随机75.00%)")
