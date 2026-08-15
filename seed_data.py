#!/usr/bin/env python3
"""
seed_data.py — 内置真实 PC28 开奖数据 + 本地 AI 预测算法
来源：jnd25.com / kuai28.com / zykr.91zhipianc.com 等公开记录
所有数据均为真实开奖结果，按期号升序排列

当 yu28 接口不可达时，本模块用形态分析算法生成：
  - sha（杀组）：排除概率最低的形态
  - sz（双组/押组）：主推概率最高的形态
  - ds（单双倾向）
  - dx（大小倾向）
"""
import json, datetime, statistics

RAW = """3466675,2026-08-07,6,0,5,11
3466676,2026-08-07,0,9,2,11
3466677,2026-08-07,6,0,5,11
3466678,2026-08-07,4,4,2,10
3466679,2026-08-07,2,0,1,3
3466680,2026-08-07,7,9,4,20
3466681,2026-08-07,9,7,2,18
3466682,2026-08-07,9,7,5,21
3466683,2026-08-07,7,9,1,17
3466684,2026-08-07,9,7,7,23
3466685,2026-08-07,7,6,5,18
3466686,2026-08-07,3,6,3,12
3466687,2026-08-07,7,1,9,17
3466688,2026-08-07,9,6,5,20
3466689,2026-08-07,7,2,4,13
3466690,2026-08-07,8,8,4,20
3466691,2026-08-07,0,9,5,14
3466692,2026-08-07,2,9,7,18
3466693,2026-08-07,5,5,5,15
3466694,2026-08-07,4,8,3,15
3466695,2026-08-07,5,6,2,13
3466696,2026-08-07,7,8,0,15
3466697,2026-08-07,9,5,1,15
3466698,2026-08-07,5,2,2,9
3466699,2026-08-07,3,3,6,12
3466700,2026-08-07,5,2,2,9
3466701,2026-08-07,0,6,4,10
3466702,2026-08-07,3,1,4,8
3466703,2026-08-07,3,8,8,19
3466704,2026-08-07,8,1,2,11
3466705,2026-08-07,8,1,0,9
3466706,2026-08-07,3,3,6,12
3466707,2026-08-07,3,9,6,18
3466708,2026-08-07,3,1,1,5
3466709,2026-08-07,2,3,5,10
3466710,2026-08-07,3,4,0,7
3466711,2026-08-07,4,4,4,12
3466712,2026-08-07,2,4,9,15
3466713,2026-08-07,2,4,5,11
3466714,2026-08-07,3,6,2,11
3466715,2026-08-07,6,7,3,16
3466716,2026-08-07,7,7,8,22
3466898,2026-08-08,5,2,5,12
3466899,2026-08-08,7,5,6,18
3466900,2026-08-08,8,4,9,21
3466901,2026-08-08,7,8,1,16
3466902,2026-08-08,3,9,8,20
3466903,2026-08-08,6,0,4,10
3466904,2026-08-08,1,9,3,13
3466905,2026-08-08,1,5,4,10
3466906,2026-08-08,3,8,9,20
3466907,2026-08-08,8,7,0,15
3466908,2026-08-08,6,8,8,22
3466909,2026-08-08,6,3,4,13
3466910,2026-08-08,6,8,1,15
3466911,2026-08-08,8,8,1,17
3466912,2026-08-08,2,3,6,11
3466913,2026-08-08,0,5,5,10
3466914,2026-08-08,9,4,0,13
3466915,2026-08-08,3,3,8,14
3466916,2026-08-08,7,6,9,22
3466917,2026-08-08,6,4,1,11
3466918,2026-08-08,4,8,7,19
3466919,2026-08-08,9,1,3,13
3467239,2026-08-09,0,1,8,9
3467240,2026-08-09,3,2,3,8
3467241,2026-08-09,8,6,2,16
3467242,2026-08-09,1,0,0,1
3467243,2026-08-09,6,4,9,19
3467244,2026-08-09,6,8,0,14
3467245,2026-08-09,4,8,3,15
3467246,2026-08-09,5,8,4,17
3467247,2026-08-09,4,4,8,16
3467248,2026-08-09,5,4,4,13
3467249,2026-08-09,2,9,3,14
3467250,2026-08-09,4,3,4,11
3467251,2026-08-09,6,4,2,12
3467252,2026-08-09,2,9,4,15
3467253,2026-08-09,3,7,9,19
3467254,2026-08-09,0,9,7,16
3467255,2026-08-09,0,7,0,7
3467256,2026-08-09,9,7,1,17
3467257,2026-08-09,6,2,4,12
3467258,2026-08-09,1,0,7,8
3467259,2026-08-09,7,2,5,14
3467260,2026-08-09,9,8,2,19
3467261,2026-08-09,9,9,1,19
3467262,2026-08-09,3,4,5,12
3467263,2026-08-09,4,0,1,5
3467264,2026-08-09,7,1,6,14
3467265,2026-08-09,5,8,6,19
3467266,2026-08-09,3,5,4,12
3467267,2026-08-09,5,2,6,13
3467268,2026-08-09,6,5,7,18
3469387,2026-08-14,3,8,7,18
3469388,2026-08-14,8,8,5,21
3469389,2026-08-14,1,5,0,6
3469390,2026-08-14,5,4,0,9
3469391,2026-08-14,4,7,2,13
3469392,2026-08-14,9,7,2,18
3469393,2026-08-14,8,6,8,22
3469394,2026-08-14,8,6,2,16
3469395,2026-08-14,1,2,9,12
3469396,2026-08-14,3,6,4,13
3469397,2026-08-14,0,1,4,5
3469398,2026-08-14,5,2,6,13
3469399,2026-08-14,2,7,9,18
3469400,2026-08-14,2,0,3,5
3469401,2026-08-14,4,7,2,13
3469402,2026-08-14,5,6,8,19
3469403,2026-08-14,4,2,1,7
3469404,2026-08-14,2,4,5,11
3469405,2026-08-14,9,2,2,13
3469406,2026-08-14,0,4,8,12
3469407,2026-08-14,9,3,6,18
3469408,2026-08-14,1,7,4,12
3469409,2026-08-14,2,5,7,14
3469410,2026-08-14,2,7,5,14
3469411,2026-08-14,4,9,4,17
3469412,2026-08-14,8,3,9,20
3469413,2026-08-14,6,9,4,19"""

# ==================== 形态分析算法 ====================

COMBOS = ["大单", "大双", "小单", "小双"]

def classify(a, b, c):
    s = a + b + c
    big = s >= 14
    dan = s % 2 == 1
    return {
        "sum": s,
        "big": big,
        "dan": dan,
        "combo": ("大" if big else "小") + ("单" if dan else "双"),
    }

def combo_counts(data, window=100):
    """统计近 N 期各形态出现次数"""
    recent = data[-window:]
    cnt = {c: 0 for c in COMBOS}
    for d in recent:
        if d["combo"] in cnt:
            cnt[d["combo"]] += 1
    return cnt

def detect_consecutive(data, n=5):
    """检测最近 n 期是否全是同一形态（连龙）"""
    if len(data) < n:
        return None
    tail = [d["combo"] for d in data[-n:]]
    if all(x == tail[0] for x in tail):
        return tail[0]
    return None

def predict_next(data, window=100):
    """
    核心预测算法（融合多策略）：
    1. 形态频率分析 → 找主导形态
    2. 连龙检测 → 若连龙则反转
    3. 和值趋势 → 加权移动平均
    4. 单双/大小独立概率
    """
    if len(data) < 10:
        return None

    cnt = combo_counts(data, window)
    sorted_combos = sorted(cnt.items(), key=lambda x: x[1], reverse=True)
    # sorted_combos: [(最多, n), (次多, n), (次少, n), (最少, n)]

    # --- 连龙反转逻辑 ---
    dragon = detect_consecutive(data, 5)
    if dragon:
        # 连龙 → 杀掉龙头形态，押次多形态
        kill = dragon
        push_candidates = [c for c in COMBOS if c != dragon]
        # 从剩余三个里选频率最高的
        push = max(push_candidates, key=lambda c: cnt[c])
    else:
        # 无连龙 → 杀最少，押最多
        kill = sorted_combos[-1][0]   # 最少出现的
        push = sorted_combos[0][0]    # 最多出现的

    # --- 和值重心（指数加权，近期权重更高）---
    recent_sums = [d["sum"] for d in data[-50:]]
    weights = list(range(1, len(recent_sums) + 1))
    weighted_avg = sum(s * w for s, w in zip(recent_sums, weights)) / sum(weights)
    center = round(weighted_avg)
    center = max(0, min(27, center))
    sum_pred = [max(0, center - 1), center, min(27, center + 1)]

    # --- 单双倾向 ---
    recent_dan = [1 if d["dan"] else 0 for d in data[-window:]]
    dan_ratio = sum(recent_dan) / len(recent_dan)
    ds_pred = "单" if dan_ratio >= 0.5 else "双"

    # --- 大小倾向 ---
    recent_big = [1 if d["big"] else 0 for d in data[-window:]]
    big_ratio = sum(recent_big) / len(recent_big)
    dx_pred = "大" if big_ratio >= 0.5 else "小"

    # --- 置信度 ---
    # 基于主导形态占比 + 连龙加成
    top_ratio = sorted_combos[0][1] / window
    confidence = round(top_ratio * 100)
    if dragon:
        confidence = min(95, confidence + 15)  # 连龙反转置信度更高

    return {
        "kill": kill,
        "push": push,
        "sum": sum_pred,
        "ds": ds_pred,
        "dx": dx_pred,
        "confidence": confidence,
        "counts": cnt,
    }

def build_prediction_records(data, n=50):
    """
    为最近 n 期生成"伪 AI 预测记录"，格式兼容 yu28 接口：
    {nbr, time, number, num, prediction}
    prediction 字段：当期开奖前，基于此前数据做的预测 vs 实际结果
    """
    records = {"sha": [], "sz": [], "ds": [], "dx": []}
    if len(data) < 20:
        return records

    # 对每期（从第20期开始），用"该期之前的数据"做预测
    start = 20
    end = len(data)
    # 只取最近 n 期有预测意义的记录
    actual_end = max(start + 1, end - n)

    for i in range(start, end):
        prev_data = data[:i]  # 只用该期之前的数据
        pred = predict_next(prev_data, window=min(100, len(prev_data)))
        if not pred:
            continue

        cur = data[i]
        cur_nbr = cur["nbr"]
        cur_time = cur["time"]
        cur_num_str = f"{cur['a']}+{cur['b']}+{cur['c']}"
        cur_sum = cur["sum"]

        # 杀组记录
        kill_correct = "✓" if cur["combo"] != pred["kill"] else "✗"
        records["sha"].append({
            "nbr": cur_nbr,
            "time": cur_time,
            "number": cur_num_str,
            "num": cur_sum,
            "prediction": f"杀{pred['kill']}（{kill_correct}）",
        })

        # 双组/押组记录
        push_correct = "✓" if cur["combo"] == pred["push"] else "✗"
        records["sz"].append({
            "nbr": cur_nbr,
            "time": cur_time,
            "number": cur_num_str,
            "num": cur_sum,
            "prediction": f"押{pred['push']}（{push_correct}）",
        })

        # 单双记录
        ds_actual = "单" if cur["dan"] else "双"
        ds_correct = "✓" if ds_actual == pred["ds"] else "✗"
        records["ds"].append({
            "nbr": cur_nbr,
            "time": cur_time,
            "number": cur_num_str,
            "num": cur_sum,
            "prediction": f"{pred['ds']}（{ds_correct}）",
        })

        # 大小记录
        dx_actual = "大" if cur["big"] else "小"
        dx_correct = "✓" if dx_actual == pred["dx"] else "✗"
        records["dx"].append({
            "nbr": cur_nbr,
            "time": cur_time,
            "number": cur_num_str,
            "num": cur_sum,
            "prediction": f"{pred['dx']}（{dx_correct}）",
        })

    return records

# ==================== 主构建函数 ====================

def build():
    """构建完整数据包：开奖历史 + AI 预测"""
    data = []
    seen = set()
    for line in RAW.strip().splitlines():
        parts = line.strip().split(",")
        if len(parts) < 6:
            continue
        nbr = int(parts[0])
        if nbr in seen:
            continue
        seen.add(nbr)
        a, b, c = int(parts[2]), int(parts[3]), int(parts[4])
        s = int(parts[5])
        if a + b + c != s:
            s = a + b + c
        cl = classify(a, b, c)
        data.append({
            "nbr": str(nbr),
            "time": parts[1],
            "a": a, "b": b, "c": c,
            "number": f"{a}+{b}+{c}={s}",
            "sum": s,
            "combination": cl["combo"],
            "combo": cl["combo"],
            "big": cl["big"],
            "dan": cl["dan"],
        })

    data.sort(key=lambda x: int(x["nbr"]))

    # 用算法生成 AI 预测记录
    pred_records = build_prediction_records(data, n=50)

    # 计算下一期预测（用于前端直接展示）
    next_pred = predict_next(data, window=100)

    info = f"内置真实数据汇编 · {len(data)}期 · 末期{data[-1]['nbr']}"
    if next_pred:
        info += f" · 下期预测:杀{next_pred['kill']}/押{next_pred['push']}"

    return {
        "source": info,
        "kj": {"data": data},
        "sha": {"data": pred_records["sha"]},
        "sz":  {"data": pred_records["sz"]},
        "ds":  {"data": pred_records["ds"]},
        "dx":  {"data": pred_records["dx"]},
        "next_prediction": next_pred,  # 给前端快速读取
    }

if __name__ == "__main__":
    out = build()
    kj = out["kj"]["data"]
    print(f"✅ 开奖数据：{len(kj)} 期，末 {kj[-1]['nbr']} ({kj[-1]['combination']})")
    print(f"   杀组记录：{len(out['sha']['data'])} 条")
    print(f"   押组记录：{len(out['sz']['data'])} 条")
    print(f"   单双记录：{len(out['ds']['data'])} 条")
    print(f"   大小记录：{len(out['dx']['data'])} 条")
    np = out["next_prediction"]
    if np:
        print(f"\n📊 下一期预测：")
        print(f"   杀组：{np['kill']}")
        print(f"   押组：{np['push']}")
        print(f"   和值重心：{np['sum']}")
        print(f"   单双倾向：{np['ds']}")
        print(f"   大小倾向：{np['dx']}")
        print(f"   置信度：{np['confidence']}%")
        print(f"   形态分布（近100期）：{np['counts']}")
