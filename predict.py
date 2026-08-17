#!/usr/bin/env python3
"""
predict.py — V8 预测模块（独立可运行）
依赖: v8_algo.py
用法: python predict.py
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from v8_algo import predict, monte_carlo_backtest, combo_of, COMBOS

def load_data(path: str = "data.json") -> list:
    """加载数据"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        # 兼容多种格式
        if isinstance(raw, dict) and "history" in raw:
            return raw["history"]
        if isinstance(raw, list):
            return raw
        return []
    except Exception as e:
        print(f"⚠️ 加载数据失败: {e}")
        return []

def format_prediction(pred: dict) -> str:
    """格式化输出预测结果"""
    lines = []
    lines.append("=" * 55)
    lines.append("🎯 V8 终极算法 · 预测结果")
    lines.append("=" * 55)
    lines.append(f"")
    lines.append(f"  🎯 主推特码:  {pred['tricode_main']}")
    lines.append(f"  🛡️ 候补特码:  {pred['tricode_backup']}")
    lines.append(f"  🔪 杀特码×5:  {pred['tricode_kill']}")
    lines.append(f"")
    lines.append(f"  🎲 押2组:    {pred['combo_push']}")
    lines.append(f"  🔪 杀1组:    {pred['combo_kill']}")
    lines.append(f"")
    lines.append(f"  📊 和值中心:  {pred['sum_center']}")
    lines.append(f"  📈 和值区间:  {pred['sum_range']}")
    lines.append(f"  💪 置信度:    {pred['confidence']}%")
    lines.append(f"")
    if pred.get("signal_details"):
        sd = pred["signal_details"]
        lines.append(f"  📡 信号详情:")
        lines.append(f"     EMA中心: {sd.get('ema_center', '-')}")
        lines.append(f"     主推3概率占比: {sd.get('top3_prob', 0)*100:.1f}%")
        lines.append(f"     杀5概率占比:   {sd.get('kill5_prob', 0)*100:.1f}%")
        lines.append(f"     组合熵: {sd.get('combo_entropy', '-')}")
    lines.append("=" * 55)
    return "\n".join(lines)

def main():
    # 加载数据
    data = load_data()
    if not data:
        print("⚠️ 无数据，使用默认预测")
        from v8_algo import predict as p
        pred = p([])
    else:
        print(f"📊 已加载 {len(data)} 期数据")
        pred = predict(data)

    print(format_prediction(pred))

    # 可选：运行回测
    if "--backtest" in sys.argv:
        print("\n" + "=" * 55)
        print("🧪 蒙特卡洛回测 (5000次 × 200期)")
        print("=" * 55)
        result = monte_carlo_backtest(5000, 200)
        print(f"\n📊 回测结果:")
        print(f"  主推3命中率:   {result['main3_rate']*100:.2f}%  (随机10.71%)")
        print(f"  候补2命中率:   {result['backup2_rate']*100:.2f}%")
        print(f"  押5总命中率:   {result['push5_rate']*100:.2f}%  (随机17.86%)")
        print(f"  杀5正确率:     {result['kill5_rate']*100:.2f}%  (随机82.14%)")
        print(f"  押2组命中率:   {result['push2_rate']*100:.2f}%  (随机50.00%)")
        print(f"  杀1组正确率:   {result['kill1_rate']*100:.2f}%  (随机75.00%)")

if __name__ == "__main__":
    main()
