#!/usr/bin/env python3
"""
fetch_data.py — BCLC Keno 数据抓取 + V8 预测引擎
数据源优先级：
  1) BCLC 官方 lotto.bclc.com
  2) 第三方镜像（yu28.top / pc28.help bclc）
  3) CORS 代理
  4) 本地种子兜底（确定性生成，永不返回空）
输出：data.json（供 index.html 在浏览器端 API 不可用时兜底）
"""
import json, sys, os, datetime
import urllib.request, urllib.error

# 导入 BCLC 数据接口模块
sys.path.insert(0, os.path.dirname(__file__))
import bclc_api as bc

# ===== V8 预测引擎 =====

def v8_predict(draws, window=100):
    """基于近期开奖数据预测下一期（V8 融合算法）"""
    if len(draws) < 10:
        return None
    recent = draws[-window:]
    sums = [d["sum"] for d in recent]
    n = len(sums)

    # 1. EMA 中心
    alpha = 0.3
    ema = sums[0]
    for s in sums[1:]:
        ema = alpha * s + (1 - alpha) * ema
    ema_int = round(ema)

    # 2. 加权频率（近期权重高）
    freq = {}
    for i, s in enumerate(sums):
        freq[s] = freq.get(s, 0) + (i + 1)
    top_sums = sorted(freq.items(), key=lambda x: -x[1])[:5]

    # 3. 马尔可夫-1
    mk1 = {}
    for i in range(1, n):
        p, c = sums[i-1], sums[i]
        if p not in mk1:
            mk1[p] = {}
        mk1[p][c] = mk1[p].get(c, 0) + 1
    last = sums[-1]
    mk1_top = sorted(mk1.get(last, {}).items(), key=lambda x: -x[1])[:3]

    # 4. 趋势
    r10 = sums[-10:]
    trend = sum(r10[-5:])/5 - sum(r10[:5])/5
    trend_adj = round(trend * 2)

    # 5. 组合投票
    combos = [bc.sum_to_combo(d["sum"]) for d in recent]
    cw = {}
    for i, c in enumerate(combos):
        cw[c] = cw.get(c, 0) + (i+1)**1.5
    top_combo = sorted(cw.items(), key=lambda x: -x[1])[:2]

    # ===== 融合投票 =====
    votes = {}
    def vote(val, weight):
        votes[val] = votes.get(val, 0) + weight

    for off in range(-2, 3):
        v = max(0, min(27, ema_int + off))
        vote(v, 3.0 - abs(off)*0.5)
    for v, w in top_sums:
        vote(v, w * 0.5)
    for v, w in mk1_top:
        vote(v, w * 0.4)
    tv = max(0, min(27, ema_int + trend_adj))
    vote(tv, 1.5)

    ranked = sorted(votes.items(), key=lambda x: -x[1])
    top5 = [v for v, _ in ranked[:5]]
    top3 = [v for v, _ in ranked[:3]]

    # 杀号：频率最低 + 远离 EMA
    inv = {s: 1.0/(freq.get(s,0)+1) for s in range(28)}
    kill5 = [v for v, _ in sorted(inv.items(), key=lambda x: -x[1])[:5]]

    push_combo = top_combo[0][0] if top_combo else "小单"
    kill_combo = "大单" if push_combo != "大单" else "小双"

    spread = len(set([v for v, _ in ranked[:5]]))
    conf = min(55, 28 + spread * 120/5)

    return {
        "push_sums": top5,
        "main3": top3,
        "kill_sums": kill5,
        "push_combo": push_combo,
        "kill_combo": kill_combo,
        "ema": ema_int,
        "trend": trend_adj,
        "confidence": round(conf, 1),
        "window": n,
    }

def main():
    print("=" * 55)
    print("BCLC Keno 数据抓取 + V8 预测引擎")
    print("=" * 55)

    # 获取真实数据（多路降级）
    data = bc.get_latest_data(30)
    draws = data.get("draws", [])

    print(f"\n数据源: {data['source']}")
    print(f"信息: {data['message']}")
    print(f"开奖中: {data['isOpen']}  时区: {data['timezone']}")
    print(f"倒计时: {data['countdown']}秒")
    print(f"下一期: {data['nextDraw']}")
    print(f"数据条数: {len(draws)}")

    if not draws:
        print("\n❌ 未获取到任何数据，保留旧 data.json")
        sys.exit(0)

    # 标准化为前端格式
    kj_data = []
    for d in draws:
        combo = bc.sum_to_combo(d["sum"])
        pattern = bc.detect_pattern(d["a"], d["b"], d["c"])
        kj_data.append({
            "nbr": d.get("period", ""),
            "date": d.get("date", ""),
            "time": d.get("time", ""),
            "a": d["a"], "b": d["b"], "c": d["c"],
            "number": f"{d['a']}+{d['b']}+{d['c']}={d['sum']}",
            "sum": d["sum"],
            "combination": combo,
            "shape": pattern,
            "raw_nums": d.get("rawNums", []),
            "source": d.get("source", ""),
        })

    # V8 预测
    pred = v8_predict(kj_data, min(100, len(kj_data)))
    if pred:
        print(f"\n📊 V8 预测：")
        print(f"  主推3: {pred['main3']}")
        print(f"  押5:   {pred['push_sums']}")
        print(f"  杀5:   {pred['kill_sums']}")
        print(f"  押组合: {pred['push_combo']}  杀组合: {pred['kill_combo']}")
        print(f"  和值EMA: {pred['ema']}  置信度: {pred['confidence']}%")

    out = {
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "source": data["source"],
        "game": "pc28_bclc",
        "timezone": data["timezone"],
        "countdown": data["countdown"],
        "nextDraw": data["nextDraw"],
        "isOpen": data["isOpen"],
        "kj": {"data": kj_data},
        "next_prediction": pred if pred else None,
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 写入 data.json ← {data['source']}")
    print(f"   数据: {len(kj_data)} 期")
    if kj_data:
        last = kj_data[-1]
        print(f"   最新: {last['nbr']} {last['date']} {last['time']} "
              f"球={last['a']}{last['b']}{last['c']} 和={last['sum']} "
              f"{last['combination']} {last['shape']}")

if __name__ == "__main__":
    main()
