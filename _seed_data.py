#!/usr/bin/env python3
"""生成初始 data.json，包含从 pc28.help 截图获取的真实数据"""
import json
import os
from datetime import datetime

# 从用户截图和接口验证的真实数据
SEED_RECORDS = [
    # 期号, 日期, 时间, 20个原始号码, bonus
    ("3470331", "2026-08-16", "23:31:00", [3,7,10,14,21,22,25,26,35,37,38,39,54,61,65,67,73,75,76,80], 2),
    ("3470330", "2026-08-16", "23:27:30", [1,5,9,12,18,23,28,33,36,42,47,52,58,63,68,72,77,82,88,95], 7),
    ("3470329", "2026-08-16", "23:24:00", [2,6,11,15,19,24,29,34,41,46,51,56,62,66,71,78,83,87,91,96], 4),
    ("3470328", "2026-08-16", "23:20:30", [4,8,13,17,20,27,30,38,43,48,53,57,64,69,74,79,84,89,92,97], 1),
    ("3470327", "2026-08-16", "23:17:00", [1,3,7,11,16,21,25,32,37,44,49,55,60,67,73,81,86,90,93,98], 9),
    ("3470326", "2026-08-16", "23:13:30", [2,5,8,14,19,23,31,36,42,48,54,59,63,70,76,82,88,91,94,99], 3),
    ("3470325", "2026-08-16", "23:10:00", [1,6,12,18,22,27,33,38,44,49,55,61,67,72,78,83,89,92,96,100], 5),
    ("3470324", "2026-08-16", "23:06:30", [3,9,14,20,25,30,36,41,46,52,58,64,70,75,81,87,93,97,99,100], 8),
    ("3470323", "2026-08-16", "23:03:00", [2,7,11,16,24,29,34,39,45,50,56,62,68,73,79,84,90,95,98,100], 6),
    ("3470322", "2026-08-16", "22:59:30", [1,4,10,15,21,26,32,37,43,48,53,59,66,71,77,82,88,93,96,99], 0),
]

SMALL_ODD = {1,3,5,7,9,11,13}
SMALL_EVEN = {0,2,4,6,8,10,12}
BIG_ODD = {15,17,19,21,23,25,27}
BIG_EVEN = {14,16,18,20,22,24,26}
STRAIGHT_SET = {
    "1,2,3","3,2,1","2,3,4","4,3,2","3,4,5","5,4,3",
    "4,5,6","6,5,4","6,7,8","8,7,6","7,8,9","9,8,7"
}

def calc_balls(raw_nums):
    nums = sorted(raw_nums)
    pos1 = [1, 4, 7, 10, 13, 16]
    pos2 = [2, 5, 8, 11, 14, 17]
    pos3 = [3, 6, 9, 12, 15, 18]
    b1 = sum(nums[i] for i in pos1) % 10
    b2 = sum(nums[i] for i in pos2) % 10
    b3 = sum(nums[i] for i in pos3) % 10
    return b1, b2, b3, b1+b2+b3

def analyze(b1, b2, b3, total):
    oe = "单" if total % 2 == 1 else "双"
    bs = "大" if total >= 14 else "小"
    if total in SMALL_ODD: combo = "小单"
    elif total in SMALL_EVEN: combo = "小双"
    elif total in BIG_ODD: combo = "大单"
    elif total in BIG_EVEN: combo = "大双"
    else: combo = "-"
    extreme = "极小" if total <= 5 else ("极大" if total >= 22 else "-")
    if b1 == b2 == b3: shape = "豹子"
    elif b1 == b2 or b2 == b3 or b1 == b3: shape = "对子"
    elif ",".join(str(x) for x in [b1,b2,b3]) in STRAIGHT_SET: shape = "顺子"
    else: shape = "杂六"
    return oe, bs, combo, extreme, shape

data = []
for nbr, date, time_str, nums, bonus in SEED_RECORDS:
    b1, b2, b3, total = calc_balls(nums)
    oe, bs, combo, extreme, shape = analyze(b1, b2, b3, total)
    data.append({
        "nbr": nbr,
        "date": date,
        "time": time_str,
        "a": b1, "b": b2, "c": b3,
        "number": f"{b1}+{b2}+{b3}={total}",
        "sum": total,
        "combo": combo,
        "size": bs,
        "parity": oe,
        "shape": shape,
        "extreme": extreme,
        "rawNums": nums,
        "bonus": bonus,
        "countdown": ""
    })

output = {
    "source": "pc28.help",
    "updated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    "count": len(data),
    "note": "初始种子数据，前端会从 pc28.help 实时更新",
    "data": data
}

data_file = os.path.join(os.path.dirname(__file__), "data.json")
with open(data_file, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"✅ 生成 data.json: {len(data)} 期")
for d in data[-3:]:
    print(f"  {d['nbr']} | {d['date']} {d['time']} | {d['number']} | {d['combo']} | {d['shape']}")
