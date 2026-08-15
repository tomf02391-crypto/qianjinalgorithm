#!/usr/bin/env python3
"""
fetch_data.py — GitHub Actions 抓取 PC28 真实开奖数据

数据获取策略（三档降级）：
  1) 通过 corsproxy.io 代理访问 yu28.top（含 AI 预测接口）
  2) 失败 → 内置真实开奖数据 + 本地形态分析算法生成 AI 预测
  3) 兜底数据生成失败 → 报错退出（绝不返回假数据）

输出：data.json（供 index.html 在浏览器端 API 不可用时兜底）
"""
import json
import urllib.request
import urllib.parse
import datetime
import sys
import os
import re

API_KEY = "yu28_f9f41d673b447fac"
BASE = "https://yu28.top"
PROXY = "https://corsproxy.io/?url="

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}


def fetch_url(url, headers=None):
    req = urllib.request.Request(url, headers=headers or HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def fetch_via_proxy(path, params=""):
    url = f"{BASE}{path}?{params}"
    target = PROXY + urllib.parse.quote(url, safe=":/?=&")
    h = {
        "User-Agent": HEADERS["User-Agent"],
        "Accept": "application/json",
        "X-Api-Key": API_KEY,
    }
    return fetch_url(target, h)


def extract_data(obj):
    """代理可能把响应包成 list 或加壳，统一抽出 {code,data} 形态"""
    if isinstance(obj, list):
        return {"code": 200, "data": obj}
    if isinstance(obj, dict):
        if "data" in obj and isinstance(obj["data"], list):
            return obj
        for v in obj.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return {"code": 200, "data": v}
    return None


def fetch_all_via_proxy():
    endpoints = {
        "kj":  ("/api/kj.json",  "nbr=350"),
        "sha": ("/api/sha.json", "nbr=50"),
        "sz":  ("/api/sz.json",  "nbr=50"),
        "ds":  ("/api/ds.json",  "nbr=50"),
        "dx":  ("/api/dx.json",  "nbr=50"),
    }
    out = {}
    for k, (p, q) in endpoints.items():
        try:
            raw = fetch_via_proxy(p, q)
            wrapped = extract_data(raw)
            out[k] = wrapped if wrapped else {"code": 0, "data": []}
            print(f"  ✅ {k}: {len(out[k].get('data',[]))} 条")
        except Exception as e:
            print(f"  ⚠ {k} 失败: {e}")
            out[k] = {"code": 0, "data": []}
    return out


def build_from_seed():
    """从内置真实数据 + 本地算法构建完整数据包"""
    sys.path.insert(0, os.path.dirname(__file__))
    import seed_data
    return seed_data.build()


def parse_number(str_):
    if not str_:
        return None
    m = re.match(r"(\d+)\+(\d+)\+(\d+)=(\d+)", str_)
    if m:
        return {"a": int(m.group(1)), "b": int(m.group(2)),
                "c": int(m.group(3)), "sum": int(m.group(4))}
    m = re.match(r"(\d+),(\d+),(\d+)\s*=>\s*(\d+)", str_)
    if m:
        return {"a": int(m.group(1)), "b": int(m.group(2)),
                "c": int(m.group(3)), "sum": int(m.group(4))}
    return None


def norm_item(it):
    p = parse_number(it.get("number", ""))
    a = b = c = s = 0
    if p:
        a, b, c, s = p["a"], p["b"], p["c"], p["sum"]
    else:
        s = int(it.get("num") or it.get("sum") or 0)
    big = s >= 14
    dan = s % 2 == 1
    combo = ("大" if big else "小") + ("单" if dan else "双")
    return {
        "nbr": str(it.get("nbr") or it.get("code") or ""),
        "time": it.get("time") or it.get("date") or "",
        "a": a, "b": b, "c": c,
        "number": it.get("number") or f"{a}+{b}+{c}={s}",
        "sum": s,
        "combination": combo,
    }


def main():
    src = ""
    kj_w = sha_w = sz_w = ds_w = dx_w = None

    # ===== 尝试 1：代理访问 yu28（含 AI 预测）=====
    print("→ 尝试 corsproxy.io → yu28.top ...")
    try:
        d = fetch_all_via_proxy()
        kj_w, sha_w, sz_w, ds_w, dx_w = d["kj"], d["sha"], d["sz"], d["ds"], d["dx"]
        if kj_w.get("data"):
            src = "yu28.top (via corsproxy.io)"
            print(f"  ✅ yu28 全部接口成功")
    except Exception as e:
        print(f"  ❌ 代理整体失败：{e}")

    # ===== 尝试 2：内置真实数据 + 本地算法 =====
    if not (kj_w and kj_w.get("data")):
        print("→ 回退到内置真实数据 + 本地形态分析算法 ...")
        seed = build_from_seed()
        kj_data = seed["kj"]["data"]
        sha_w = seed["sha"]
        sz_w = seed["sz"]
        ds_w = seed["ds"]
        dx_w = seed["dx"]
        src = seed["source"]
        print(f"  ✅ 本地算法生成：sha={len(sha_w.get('data',[]))} "
              f"sz={len(sz_w.get('data',[]))} "
              f"ds={len(ds_w.get('data',[]))} "
              f"dx={len(dx_w.get('data',[]))}")
    else:
        kj_data = [norm_item(x) for x in kj_w["data"]]
        kj_data = [x for x in kj_data if x["nbr"]]

    # ===== 组装输出 =====
    out = {
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "source": src,
        "game": "pc28",
        "kj":  {"data": kj_data},
        "sha": sha_w,
        "sz":  sz_w,
        "ds":  ds_w,
        "dx":  dx_w,
    }

    # 附加下一期预测（方便前端快速读取）
    # 当走种子数据路径时，kj_data 一定有值
    if kj_data and len(kj_data) > 0:
        sys.path.insert(0, os.path.dirname(__file__))
        import seed_data as sd
        np = sd.predict_next(kj_data, window=100)
        if np:
            out["next_prediction"] = np
            print(f"  📊 下期预测已附加：杀{np['kill']}/押{np['push']}")

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 写入 data.json ← {src[:70]}")
    print(f"   开奖数据：{len(kj_data)} 期")
    print(f"   最新期：{kj_data[-1]['nbr'] if kj_data else 'N/A'}")
    if out.get("next_prediction"):
        np = out["next_prediction"]
        print(f"   下期预测：杀{np['kill']} / 押{np['push']} / "
              f"和值{np['sum']} / 置信度{np['confidence']}%")


if __name__ == "__main__":
    main()
