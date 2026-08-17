#!/usr/bin/env python3
"""将121期数据转换为V8格式"""
import json, os

src = "/data/workspace/data.json"
dst = "/data/workspace/qianjinalgorithm/data.json"

with open(src) as f:
    raw = json.load(f)

items = raw.get("kj", {}).get("data", [])
print(f"源数据: {len(items)} 期")

v8data = []
for item in items:
    nbr = item.get("nbr", "")
    # time字段在这里是日期
    date = item.get("time", "")
    a = item.get("a", 0)
    b = item.get("b", 0)
    c = item.get("c", 0)
    total = a + b + c
    combo = item.get("combo") or item.get("combination") or ""
    if not combo:
        if total >= 14:
            combo = "大单" if total % 2 == 1 else "大双"
        else:
            combo = "小单" if total % 2 == 1 else "小双"

    v8data.append({
        "nbr": str(nbr),
        "date": date,
        "time": "",
        "raw": [a, b, c] + [0]*17,  # 填充到20个
        "b1": a, "b2": b, "b3": c,
        "sum": total,
        "combo": combo,
        "odd": total % 2 == 1,
        "big": total >= 14,
    })

print(f"转换后: {len(v8data)} 期")
print(f"  首期: {v8data[0]['nbr']} sum={v8data[0]['sum']} combo={v8data[0]['combo']}")
print(f"  末期: {v8data[-1]['nbr']} sum={v8data[-1]['sum']} combo={v8data[-1]['combo']}")

# 用V8预测
sys_path = os.path.dirname(dst)
import sys
sys.path.insert(0, "/data/workspace/qianjinalgorithm")
from v8_algo import predict

pred = predict(v8data)
print(f"\n🎯 V8 预测 (基于{len(v8data)}期):")
print(f"  主推3: {pred['tricode_main']}")
print(f"  候补2: {pred['tricode_backup']}")
print(f"  杀5:   {pred['tricode_kill']}")
print(f"  押2组: {pred['combo_push']}")
print(f"  杀1组: {pred['combo_kill']}")
print(f"  和值中心: {pred['sum_center']} 区间: {pred['sum_range']}")
print(f"  置信度: {pred['confidence']}%")

output = {
    "meta": {
        "source": "pc28.help",
        "count": len(v8data),
        "updated": "2026-08-17 12:00:00",
        "engine": "V8",
        "v8_signals": pred.get("signal_details", {}),
    },
    "history": v8data,
    "prediction": pred,
}

with open(dst, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

sz = os.path.getsize(dst)
print(f"\n✅ 写入 {dst} ({sz} bytes)")
