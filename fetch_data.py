#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_data.py — 千金星轨 V10 · 数据仓库版
==========================================
变更说明（V10）：
  - 数据源统一从 Liquid-Glass-Profil 数据仓库读取
  - 不再直接调用外部API，避免限流和依赖
  - BCLC官方规则计算由数据仓库统一完成
  - 本地缓存兜底，永不返回空数据

数据流:
  BCLC官网 → Liquid-Glass-Profil/scripts/fetch_data.py (每5分钟)
  → data/latest.json (GitHub Pages托管)
  → 本脚本读取 → 写入 data.json (供前端使用)

用法：
  python fetch_data.py           # 抓取+预测+写data.json
  python fetch_data.py --dry     # 只测试数据源连通性
  python fetch_data.py --health  # 健康检查
"""

import json
import sys
import os
import math
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ============================================================
# 配置
# ============================================================
BJT = timezone(timedelta(hours=8))
DRAW_INTERVAL = 210  # 3分30秒

# Liquid-Glass-Profil 数据仓库 URL (GitHub Pages)
DATA_URLS = [
    "https://tomf02391-crypto.github.io/Liquid-Glass-Profil/data/latest.json",
    "https://raw.githubusercontent.com/tomf02391-crypto/Liquid-Glass-Profil/main/data/latest.json",
]

# 本地缓存路径
CACHE_DIR = Path(__file__).parent
DATA_FILE = CACHE_DIR / "data.json"
RECORDS_FILE = CACHE_DIR / "records.json"


# ============================================================
# 时区工具（与数据仓库保持一致）
# ============================================================
def is_dst_utc(utc_dt):
    """判断UTC时间是否处于北美夏令时"""
    year = utc_dt.year
    march1 = datetime(year, 3, 1, tzinfo=timezone.utc)
    days = (6 - march1.weekday() + 7) % 7 + 7
    dst_start = march1 + timedelta(days=days, hours=10)
    nov1 = datetime(year, 11, 1, tzinfo=timezone.utc)
    days2 = (6 - nov1.weekday()) % 7
    dst_end = nov1 + timedelta(days=days2, hours=9)
    return dst_start <= utc_dt < dst_end


def get_session_bounds(bj_dt):
    utc = bj_dt.astimezone(timezone.utc)
    dst = is_dst_utc(utc)
    if dst:
        start = bj_dt.replace(hour=20, minute=0, second=0, microsecond=0)
        end = (start + timedelta(days=1)).replace(hour=19, minute=0, second=0)
    else:
        start = bj_dt.replace(hour=21, minute=0, second=0, microsecond=0)
        end = (start + timedelta(days=1)).replace(hour=20, minute=0, second=0)
    return start, end, dst


def is_open(bj_dt):
    s, e, _ = get_session_bounds(bj_dt)
    return s <= bj_dt <= e


def period_info(bj_dt):
    s, e, dst = get_session_bounds(bj_dt)
    if bj_dt < s:
        prev = bj_dt - timedelta(days=1)
        s, _, _ = get_session_bounds(prev)
    elapsed = (bj_dt - s).total_seconds()
    seq = max(1, int(elapsed / DRAW_INTERVAL) + 1)
    date_str = s.strftime('%y%m%d')
    period = f"{date_str}{seq:04d}"
    next_draw = s + timedelta(seconds=seq * DRAW_INTERVAL)
    cd = max(0, int((next_draw - bj_dt).total_seconds()))
    return period, cd, next_draw, seq, s


# ============================================================
# 从数据仓库获取数据
# ============================================================
def fetch_from_warehouse() -> dict:
    """从 Liquid-Glass-Profil 数据仓库获取最新数据"""
    last_err = None
    for url in DATA_URLS:
        try:
            print(f"  [FETCH] 尝试: {url}", flush=True)
            req = urllib.request.Request(
                url + f"?t={int(time.time())}",
                headers={"User-Agent": "qianjinalgorithm/10.0", "Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = json.loads(resp.read().decode("utf-8"))

            data = raw.get("data", [])
            if not data:
                print(f"  [WARN] {url} 返回空数据", flush=True)
                continue

            # 标准化格式
            normalized = []
            for d in data:
                item = {
                    "nbr": str(d.get("nbr", "")),
                    "date": d.get("date", ""),
                    "time": d.get("time", ""),
                    "b1": int(d.get("b1", 0)),
                    "b2": int(d.get("b2", 0)),
                    "b3": int(d.get("b3", 0)),
                    "sum": int(d.get("num", d.get("sum", 0))),
                    "combo": d.get("combination", d.get("combo", "")),
                    "raw_nums": d.get("raw_nums", []),
                }
                if not item["combo"]:
                    item["combo"] = ("大" if item["sum"] >= 14 else "小") + ("单" if item["sum"] % 2 == 1 else "双")
                normalized.append(item)

            src_name = "Liquid-Glass-Profil数据仓库(BCLC官方规则)"
            print(f"  [OK] {src_name} → {len(normalized)}期", flush=True)
            return {
                "data": normalized,
                "source": src_name,
                "countdown": raw.get("countdown", ""),
                "fetched_at": raw.get("fetched_at", ""),
            }

        except Exception as e:
            last_err = str(e)
            print(f"  [ERR] {url}: {e}", flush=True)
            continue

    raise RuntimeError(f"所有数据仓库URL均失败: {last_err}")


# ============================================================
# 本地缓存兜底
# ============================================================
def load_cache() -> list:
    """从本地 data.json 读取缓存"""
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE) as f:
                old = json.load(f)
            return old.get("history", [])
        except:
            pass
    # 也试试 records
    if RECORDS_FILE.exists():
        try:
            with open(RECORDS_FILE) as f:
                return json.load(f)
        except:
            pass
    return []


# ============================================================
# PC28 规则工具
# ============================================================
def combo_of(sum_val):
    if sum_val >= 14:
        return "大单" if sum_val % 2 == 1 else "大双"
    return "小单" if sum_val % 2 == 1 else "小双"


def detect_pattern(a, b, c):
    s = sorted([a, b, c])
    if a == b == c:
        return "豹子"
    if a == b or b == c or a == c:
        return "对子"
    if s[1] - s[0] == 1 and s[2] - s[1] == 1:
        return "顺子"
    return "杂六"


def decompose_sum(s):
    results = []
    for a in range(10):
        for b in range(10):
            for c in range(10):
                if a + b + c == s:
                    results.append(tuple(sorted([a, b, c])))
    seen = set()
    unique = []
    for r in results:
        if r not in seen:
            seen.add(r)
            unique.append(list(r))
    unique.sort(key=lambda x: (not (x[0] == x[1] or x[1] == x[2]), x[0]))
    return unique[0] if unique else [0, 0, 0]


# ============================================================
# V9 预测引擎（保留原算法）
# ============================================================
def gaussian_probs(center, sigma):
    probs = {}
    for x in range(28):
        d = x - center
        probs[x] = math.exp(-d * d / (2 * sigma * sigma))
    return probs


def normalize(probs):
    total = sum(probs.values()) or 1
    return {k: v / total for k, v in probs.items()}


def signal_ema(data, alpha=0.3):
    if not data:
        return {}
    ema = data[0]["sum"]
    for d in data[1:]:
        ema = alpha * d["sum"] + (1 - alpha) * ema
    return gaussian_probs(round(ema), 2.0)


def signal_double_ema(data):
    if len(data) < 3:
        return {}
    e1 = e2 = data[0]["sum"]
    for d in data[1:]:
        e1 = 0.3 * d["sum"] + 0.7 * e1
        e2 = 0.15 * e1 + 0.85 * e2
    c = max(0, min(27, round(e1 + (e1 - e2))))
    return gaussian_probs(c, 1.5)


def signal_weighted_freq(data, decay=0.95):
    if not data:
        return {}
    weights = [decay ** (len(data) - 1 - i) for i in range(len(data))]
    counts = {}
    for i, d in enumerate(data):
        counts[d["sum"]] = counts.get(d["sum"], 0) + weights[i]
    total = sum(counts.values()) or 1
    return {x: counts.get(x, 0) / total for x in range(28)}


def signal_markov1(data):
    if len(data) < 5:
        return {}
    trans = {}
    for i in range(len(data) - 1):
        k = data[i]["sum"]
        nxt = data[i + 1]["sum"]
        if k not in trans:
            trans[k] = {}
        trans[k][nxt] = trans[k].get(nxt, 0) + 1
    last = data[-1]["sum"]
    if last not in trans:
        return {}
    c = trans[last]
    total = sum(c.values()) or 1
    return {x: c.get(x, 0) / total for x in range(28)}


def signal_diff_reversal(data):
    if len(data) < 6:
        return {}
    diffs = [data[i]["sum"] - data[i - 1]["sum"] for i in range(1, len(data))]
    recent = diffs[-5:]
    avg = sum(recent) / len(recent)
    center = max(0, min(27, round(data[-1]["sum"] - avg * 0.5)))
    return gaussian_probs(center, 1.0)


def signal_combo_constraint(data):
    if len(data) < 10:
        return {}
    combos = [d["combo"] for d in data[-30:]]
    counts = {}
    for c in combos:
        counts[c] = counts.get(c, 0) + 1
    top = max(counts, key=counts.get)
    return {x: 1.0 if combo_of(x) == top else 0.01 for x in range(28)}


def v9_predict(data):
    """多信号融合预测"""
    if not data or len(data) < 5:
        return {
            "tricode_main": [13, 14, 15],
            "tricode_backup": [10, 17],
            "tricode_kill": [0, 1, 2, 26, 27],
            "combo_push": ["小单", "大双"],
            "combo_kill": "大单",
            "sum_center": 13,
            "sum_range": [10, 17],
            "confidence": 15,
        }

    signals = {
        "ema": normalize(signal_ema(data)),
        "double_ema": normalize(signal_double_ema(data)),
        "freq": normalize(signal_weighted_freq(data)),
        "mk1": normalize(signal_markov1(data)),
        "diff": normalize(signal_diff_reversal(data)),
        "combo": normalize(signal_combo_constraint(data)),
    }

    weights = {"ema": 3.0, "double_ema": 2.0, "freq": 2.5, "mk1": 2.0, "diff": 1.5, "combo": 1.2}

    fused = {x: 0.0 for x in range(28)}
    total_w = 0
    for name, probs in signals.items():
        if not probs:
            continue
        w = weights.get(name, 1.0)
        for x in range(28):
            fused[x] += probs.get(x, 0) * w
        total_w += w
    if total_w > 0:
        for x in range(28):
            fused[x] /= total_w

    ranked = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)
    main3 = [kv[0] for kv in ranked[:3]]
    backup2 = [kv[0] for kv in ranked[3:5]]

    # 杀5
    theo = {}
    for x in range(28):
        count = sum(1 for a in range(10) for b in range(10) for c in range(10) if a + b + c == x)
        theo[x] = count / 1000
    combined = {x: (1 - fused.get(x, 0)) * 0.5 + theo[x] * 0.5 for x in range(28)}
    kill5 = [kv[0] for kv in sorted(combined.items(), key=lambda kv: kv[1])[:5]]

    # 组合
    combo_counts = {}
    for d in data[-20:]:
        c = d["combo"]
        combo_counts[c] = combo_counts.get(c, 0) + 1
    combo_ranked = sorted(combo_counts.items(), key=lambda kv: kv[1], reverse=True)
    push2 = [kv[0] for kv in combo_ranked[:2]]
    kill1 = combo_ranked[-1][0] if combo_ranked else "大单"

    # 置信度
    ema = data[0]["sum"]
    for d in data[1:]:
        ema = 0.3 * d["sum"] + 0.7 * ema
    center = round(ema)
    variance = sum((d["sum"] - ema) ** 2 for d in data[-20:]) / min(20, len(data))
    spread = max(2, round((variance ** 0.5) * 0.8))
    lo = max(0, center - spread)
    hi = min(27, center + spread)

    entropy = -sum(p * (math.log2(p) if p > 0 else 0) for p in fused.values())
    max_e = math.log2(28)
    consistency = 1 - entropy / max_e
    conf = min(55, max(15, round(ranked[0][1] * 30 + consistency * 15)))

    return {
        "tricode_main": main3,
        "tricode_backup": backup2,
        "tricode_kill": kill5,
        "combo_push": push2,
        "combo_kill": kill1,
        "sum_center": center,
        "sum_range": [lo, hi],
        "confidence": conf,
    }


# ============================================================
# 对错记录
# ============================================================
def update_records(data, pred, old_records):
    if not pred or not data:
        return old_records
    latest = data[-1]
    nbr = latest["nbr"]
    if any(r.get("nbr") == nbr for r in old_records):
        return old_records
    record = {
        "nbr": nbr,
        "sum": latest["sum"],
        "combo": latest["combo"],
        "main_hit": latest["sum"] in pred["tricode_main"],
        "backup_hit": latest["sum"] in pred["tricode_backup"],
        "kill_correct": latest["sum"] not in pred["tricode_kill"],
        "combo_hit": latest["combo"] in pred["combo_push"],
        "main_pred": pred["tricode_main"],
        "kill_pred": pred["tricode_kill"],
        "date": latest.get("date", ""),
    }
    old_records.append(record)
    return old_records[-100:]


# ============================================================
# 主流程
# ============================================================
def main():
    bjt = datetime.now(BJT)
    per, cd, next_draw, seq, sess_start = period_info(bjt)
    _, _, dst = get_session_bounds(bjt)
    tz_name = "PDT" if dst else "PST"

    print("=" * 55, flush=True)
    print(f"  千金星轨 V10 · 数据仓库版", flush=True)
    print(f"  北京时间: {bjt.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    print(f"  时区: {tz_name}  开奖中: {is_open(bjt)}  倒计时: {cd}秒", flush=True)
    print(f"  当期期号: {per}", flush=True)
    print("=" * 55, flush=True)

    # 1. 从数据仓库获取
    try:
        result = fetch_from_warehouse()
        data = result["data"]
        source = result["source"]
        countdown = result.get("countdown", "")
        print(f"\n  [OK] 数据源: {source}", flush=True)
        print(f"  [OK] 获取 {len(data)} 期数据", flush=True)
        if data:
            latest = data[-1]
            print(f"  [OK] 最新: 期{latest['nbr']} {latest['b1']}+{latest['b2']}+{latest['b3']}={latest['sum']} {latest['combo']}", flush=True)
    except Exception as e:
        print(f"\n  [WARN] 数据仓库不可用: {e}", flush=True)
        print(f"  [WARN] 尝试本地缓存...", flush=True)
        cached = load_cache()
        if not cached:
            print(f"  [ERROR] 无缓存数据，无法继续", flush=True)
            return 1
        data = cached
        source = "💾 本地缓存(数据仓库不可用)"
        countdown = ""
        print(f"  [KEEP] 使用本地缓存 {len(data)} 期", flush=True)

    # 2. 数据校验
    valid = []
    for d in data:
        if d["sum"] < 0 or d["sum"] > 27:
            continue
        if d.get("b1", 0) + d.get("b2", 0) + d.get("b3", 0) != d["sum"]:
            balls = decompose_sum(d["sum"])
            d["b1"], d["b2"], d["b3"] = balls[0], balls[1], balls[2]
        valid.append(d)

    print(f"\n  有效数据: {len(valid)}期 (来源: {source})", flush=True)

    # 3. 预测
    if len(valid) < 5:
        print("  [WARN] 数据不足5期，跳过预测", flush=True)
        pred = None
    else:
        pred = v9_predict(valid)
        print(f"\n  [PREDICT]", flush=True)
        print(f"    主推: {pred['tricode_main']}", flush=True)
        print(f"    候补: {pred['tricode_backup']}", flush=True)
        print(f"    杀5:  {pred['tricode_kill']}", flush=True)
        print(f"    押2组: {pred['combo_push']}", flush=True)
        print(f"    杀1组: {pred['combo_kill']}", flush=True)
        print(f"    和值: {pred['sum_center']} 区间{pred['sum_range']}", flush=True)
        print(f"    置信度: {pred['confidence']}%", flush=True)

    # 4. 对错记录
    old_records = []
    if RECORDS_FILE.exists():
        try:
            with open(RECORDS_FILE) as f:
                old_records = json.load(f)
        except:
            old_records = []

    new_records = update_records(valid, pred, old_records)

    if new_records:
        main_hits = sum(1 for r in new_records if r.get("main_hit"))
        backup_hits = sum(1 for r in new_records if r.get("backup_hit"))
        kill_ok = sum(1 for r in new_records if r.get("kill_correct"))
        total = len(new_records)
        print(f"\n  对错记录 (共{total}期):", flush=True)
        print(f"    主推命中: {main_hits}/{total} ({main_hits/total*100:.1f}%)", flush=True)
        print(f"    含候补: {main_hits+backup_hits}/{total} ({(main_hits+backup_hits)/total*100:.1f}%)", flush=True)
        print(f"    杀特码正确: {kill_ok}/{total} ({kill_ok/total*100:.1f}%)", flush=True)

    # 5. 写入 data.json
    output = {
        "meta": {
            "source": source,
            "count": len(valid),
            "updated": bjt.strftime("%Y-%m-%d %H:%M:%S"),
            "engine": "V10-warehouse",
            "timezone": tz_name,
            "is_open": is_open(bjt),
            "countdown": cd if not countdown else countdown,
            "next_draw": next_draw.strftime("%Y-%m-%d %H:%M:%S"),
            "current_period": per,
            "records_total": len(new_records),
            "data_warehouse": "Liquid-Glass-Profil",
            "rule": "BCLC官方规则: b1=(pos2+5+8+11+14+17)%10, b2=(pos3+6+9+12+15+18)%10, b3=(pos4+7+10+13+16+19)%10",
        },
        "history": valid,
        "prediction": pred,
        "records": new_records[-20:],
    }

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    with open(RECORDS_FILE, "w", encoding="utf-8") as f:
        json.dump(new_records, f, ensure_ascii=False, indent=2)

    size = DATA_FILE.stat().st_size
    print(f"\n  [OK] 写入 {DATA_FILE} ({size} bytes)", flush=True)
    print(f"  [OK] 写入 {RECORDS_FILE}", flush=True)
    return 0


if __name__ == "__main__":
    if "--dry" in sys.argv:
        print("  数据源连通性测试模式")
        try:
            r = fetch_from_warehouse()
            print(f"  ✅ 成功: {len(r['data'])}期 from {r['source']}")
        except Exception as e:
            print(f"  ❌ 失败: {e}")
        sys.exit(0)
    if "--health" in sys.argv:
        print("  健康检查模式")
        for url in DATA_URLS:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "health-check"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    count = len(data.get("data", []))
                    print(f"  ✅ {url}: {count}期")
            except Exception as e:
                print(f"  ❌ {url}: {e}")
        sys.exit(0)
    sys.exit(main())
