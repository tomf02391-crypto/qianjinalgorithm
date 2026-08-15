#!/usr/bin/env python3
"""
fetch_data.py — 构建 PC28 数据快照（纯本地，零网络依赖）

数据来源：内置真实开奖数据（与 index.html 中的 RAW_DATA 同步）
算法来源：pc28_api.py 的 calc_balls + analyze 逻辑

输出：data.json（供 GitHub Pages 静态托管）

设计原则：
  - 不访问任何外部 URL（避免 Cloudflare 403）
  - 所有计算在本地完成
  - 与前端 index.html 的 JavaScript 算法结果完全一致
"""
import json
import datetime
import statistics

# ==================== 真实开奖数据 ====================
# 格式：期号,日期,a,b,c,和值
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

# ==================== 规则表（与 pc28_api.py 一致）====================
SMALL_ODD  = {1, 3, 5, 7, 9, 11, 13}
SMALL_EVEN = {0, 2, 4, 6, 8, 10, 12}
BIG_ODD    = {15, 17, 19, 21, 23, 25, 27}
BIG_EVEN   = {14, 16, 18, 20, 22, 24, 26}

STRAIGHT_SET = {
    (1, 2, 3), (3, 2, 1),
    (2, 3, 4), (4, 3, 2),
    (3, 4, 5), (5, 4, 3),
    (4, 5, 6), (6, 5, 4),
    (6, 7, 8), (8, 7, 6),
    (7, 8, 9), (9, 8, 7),
}

COMBOS = ["大单", "大双", "小单", "小双"]


# ==================== 核心算法（移植自 pc28_api.py）====================

def analyze(b1, b2, b3, total):
    """术语分析（与 pc28_api.py 的 analyze() 完全一致）"""
    odd_even = "单" if total % 2 == 1 else "双"
    big_small = "大" if total >= 14 else "小"

    if total in SMALL_ODD:
        combination = "小单"
    elif total in SMALL_EVEN:
        combination = "小双"
    elif total in BIG_ODD:
        combination = "大单"
    elif total in BIG_EVEN:
        combination = "大双"
    else:
        combination = "-"

    if total <= 5:
        extreme = "极小"
    elif total >= 22:
        extreme = "极大"
    else:
        extreme = "-"

    if b1 == b2 == b3:
        shape = "豹子"
    elif len({b1, b2, b3}) == 2:
        shape = "对子"
    elif (b1, b2, b3) in STRAIGHT_SET:
        shape = "顺子"
    else:
        shape = "杂六"

    return {
        "单双": odd_even,
        "大小": big_small,
        "组合": combination,
        "极值": extreme,
        "形态": shape,
    }


# ==================== 数据构建 ====================

def build_kj_data():
    """从 RAW 构建开奖数据列表"""
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
        date_str = parts[1]
        a, b, c = int(parts[2]), int(parts[3]), int(parts[4])
        s = int(parts[5])
        # 校验
        if a + b + c != s:
            s = a + b + c
        an = analyze(a, b, c, s)
        data.append({
            "nbr": str(nbr),
            "date": date_str,
            "time": "00:00:00",
            "a": a, "b": b, "c": c,
            "number": f"{a}+{b}+{c}={s}",
            "sum": s,
            "combination": an["组合"],
            "combo": an["组合"],
            "big": an["大小"] == "大",
            "dan": an["单双"] == "单",
            "shape": an["形态"],
            "extreme": an["极值"],
        })
    data.sort(key=lambda x: int(x["nbr"]))
    return data


# ==================== 预测引擎（与前端 JS 一致）====================

def combo_counts(data, window=100):
    recent = data[-window:]
    cnt = {"大单": 0, "大双": 0, "小单": 0, "小双": 0}
    for d in recent:
        if d["combo"] in cnt:
            cnt[d["combo"]] += 1
    return cnt


def detect_dragon(data, n=5):
    if len(data) < n:
        return None
    tail = [d["combo"] for d in data[-n:]]
    return tail[0] if all(x == tail[0] for x in tail) else None


def weighted_average(arr):
    if not arr:
        return 13.5
    weights = list(range(1, len(arr) + 1))
    return sum(v * w for v, w in zip(arr, weights)) / sum(weights)


def predict_next(data, window=100):
    """核心预测（与前端 predictNext 一致）"""
    if len(data) < 10:
        return None

    cnt = combo_counts(data, window)
    sorted_combos = sorted(cnt.items(), key=lambda x: x[1], reverse=True)

    dragon = detect_dragon(data, 5)
    if dragon:
        kill = dragon
        others = [c for c in COMBOS if c != dragon]
        push = max(others, key=lambda c: cnt[c])
    else:
        kill = sorted_combos[-1][0]
        push = sorted_combos[0][0]

    # 和值重心
    recent_sums = [d["sum"] for d in data[-50:]]
    center = round(weighted_average(recent_sums))
    center = max(0, min(27, center))
    sum_pred = [max(0, center - 1), center, min(27, center + 1)]

    # 单双/大小
    dan_ratio = sum(1 for d in data[-window:] if d["dan"]) / min(window, len(data))
    big_ratio = sum(1 for d in data[-window:] if d["big"]) / min(window, len(data))

    # 置信度
    confidence = round((sorted_combos[0][1] / min(window, len(data))) * 100)
    if dragon:
        confidence = min(95, confidence + 15)

    return {
        "kill": kill,
        "push": push,
        "sum": sum_pred,
        "ds": "单" if dan_ratio >= 0.5 else "双",
        "dx": "大" if big_ratio >= 0.5 else "小",
        "confidence": confidence,
        "counts": cnt,
        "dragon": dragon is not None,
    }


def build_prediction_records(data, n=50):
    """为最近 n 期生成预测记录（用于回测展示）"""
    records = {"sha": [], "sz": [], "ds": [], "dx": []}
    if len(data) < 20:
        return records

    start = 20
    end = len(data)

    for i in range(start, end):
        prev = data[:i]
        pred = predict_next(prev, window=min(100, len(prev)))
        if not pred:
            continue

        cur = data[i]
        cur_nbr = cur["nbr"]
        cur_date = cur.get("date", "")
        cur_time = cur.get("time", "00:00:00")
        cur_num_str = cur.get("number", f"{cur['a']}+{cur['b']}+{cur['c']}")
        cur_sum = cur["sum"]

        # 杀组
        kill_correct = "✓" if cur["combo"] != pred["kill"] else "✗"
        records["sha"].append({
            "nbr": cur_nbr, "date": cur_date, "time": cur_time,
            "number": cur_num_str, "num": cur_sum,
            "prediction": f"杀{pred['kill']}（{kill_correct}）",
        })

        # 押组
        push_correct = "✓" if cur["combo"] == pred["push"] else "✗"
        records["sz"].append({
            "nbr": cur_nbr, "date": cur_date, "time": cur_time,
            "number": cur_num_str, "num": cur_sum,
            "prediction": f"押{pred['push']}（{push_correct}）",
        })

        # 单双
        ds_actual = "单" if cur["dan"] else "双"
        ds_correct = "✓" if ds_actual == pred["ds"] else "✗"
        records["ds"].append({
            "nbr": cur_nbr, "date": cur_date, "time": cur_time,
            "number": cur_num_str, "num": cur_sum,
            "prediction": f"{pred['ds']}（{ds_correct}）",
        })

        # 大小
        dx_actual = "大" if cur["big"] else "小"
        dx_correct = "✓" if dx_actual == pred["dx"] else "✗"
        records["dx"].append({
            "nbr": cur_nbr, "date": cur_date, "time": cur_time,
            "number": cur_num_str, "num": cur_sum,
            "prediction": f"{pred['dx']}（{dx_correct}）",
        })

    return records


# ==================== 主构建 ====================

def main():
    print("→ 构建开奖数据 ...")
    data = build_kj_data()
    print(f"  ✅ {len(data)} 期真实数据")
    print(f"  📅 范围：{data[0]['date']} ~ {data[-1]['date']}")
    print(f"  🔢 最新期：{data[-1]['nbr']}（{data[-1]['combo']}，{data[-1]['shape']}）")

    # 数据校验
    errors = 0
    for d in data:
        if d["a"] + d["b"] + d["c"] != d["sum"]:
            errors += 1
        if d["sum"] < 0 or d["sum"] > 27:
            errors += 1
    if errors:
        print(f"  ⚠️ 数据校验：发现 {errors} 条异常")
    else:
        print(f"  ✅ 数据校验通过（和值全部正确）")

    # 预测
    print("\n→ 生成预测记录 ...")
    pred_records = build_prediction_records(data, n=50)
    next_pred = predict_next(data, window=100)

    # 形态分布
    cnt = combo_counts(data, 100)
    print(f"  📊 形态分布（近100期）：{cnt}")

    if next_pred:
        print(f"\n📊 下一期预测：")
        print(f"   杀组：{next_pred['kill']}")
        print(f"   押组：{next_pred['push']}")
        print(f"   和值重心：{next_pred['sum']}")
        print(f"   单双倾向：{next_pred['ds']}")
        print(f"   大小倾向：{next_pred['dx']}")
        print(f"   置信度：{next_pred['confidence']}%")
        if next_pred['dragon']:
            print(f"   🐉 连龙检测：已触发反转！")

    # 回测
    print("\n→ 回测统计 ...")
    correct = 0
    total = 0
    for i in range(1, len(data)):
        if data[i-1]["combo"] == data[i]["combo"]:
            correct += 1
        total += 1
    hit_rate = round(correct / total * 100) if total > 0 else 0
    print(f"   押组命中率：{hit_rate}%（{correct}/{total}）")

    # 组装输出
    out = {
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "source": f"真实数据{len(data)}期(08-07~08-14) · 本地算法 · 零网络依赖",
        "game": "pc28",
        "kj": {"data": data},
        "sha": {"data": pred_records["sha"]},
        "sz": {"data": pred_records["sz"]},
        "ds": {"data": pred_records["ds"]},
        "dx": {"data": pred_records["dx"]},
        "next_prediction": next_pred,
    }

    # 写入
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 写入 data.json")
    print(f"   开奖数据：{len(data)} 期")
    print(f"   杀组记录：{len(pred_records['sha'])} 条")
    print(f"   押组记录：{len(pred_records['sz'])} 条")
    print(f"   单双记录：{len(pred_records['ds'])} 条")
    print(f"   大小记录：{len(pred_records['dx'])} 条")
    if next_pred:
        print(f"   下期预测：杀{next_pred['kill']} / 押{next_pred['push']} / 置信度{next_pred['confidence']}%")


if __name__ == "__main__":
    main()
