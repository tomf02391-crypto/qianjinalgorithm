#!/usr/bin/env python3
"""
fetch_data.py — GitHub Actions 抓取 PC28 真实开奖数据

数据源：pc28.help（无需认证，GET 即可，支持 JSON/XML 双格式）
接口文档：https://pc28.help/api

降级策略：
  1) pc28.help/api/kj.json?nbr=350（主源，含倒计时）
  2) pc28.help/api/sha.json /sz.json /ds.json /dx.json（AI 预测）
  3) 全部失败 → 内置真实数据 + 本地形态分析算法

输出：data.json（供 index.html 在浏览器端 API 不可用时兜底）
"""
import json
import urllib.request
import datetime
import sys
import os
import re

BASE = "https://pc28.help"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://pc28.help/",
}


def fetch_url(url, headers=None):
    req = urllib.request.Request(url, headers=headers or HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def fetch_all():
    """从 pc28.help 抓取全部数据"""
    endpoints = {
        "kj":  "/api/kj.json?nbr=350",
        "sha": "/api/sha.json?nbr=50",
        "sz":  "/api/sz.json?nbr=50",
        "ds":  "/api/ds.json?nbr=50",
        "dx":  "/api/dx.json?nbr=50",
    }
    out = {}
    for k, path in endpoints.items():
        url = BASE + path
        try:
            d = fetch_url(url)
            if isinstance(d, dict) and d.get("message") == "success" and d.get("data"):
                out[k] = d
                print(f"  ✅ {k}: {len(d['data'])} 条")
            else:
                print(f"  ⚠ {k}: 响应异常 {str(d)[:80]}")
                out[k] = {"message": "error", "data": []}
        except Exception as e:
            print(f"  ❌ {k} 失败: {e}")
            out[k] = {"message": "error", "data": []}
    return out


def build_from_seed():
    """从内置真实数据 + 本地算法构建完整数据包"""
    sys.path.insert(0, os.path.dirname(__file__))
    import seed_data
    return seed_data.build()


def norm_kj_item(it):
    """统一 kj 数据字段格式"""
    nbr = str(it.get("nbr") or it.get("drawNbr") or "")
    # number 字段可能是 "a+b+c=sum" 或纯数字
    num_str = it.get("number") or it.get("numStr") or ""
    s = it.get("num") or it.get("sum")
    if s is None and num_str:
        m = re.match(r".*=(\d+)", str(num_str))
        if m:
            s = int(m.group(1))
    if s is None:
        # 尝试从 a/b/c 计算
        a = it.get("a") or it.get("ball1")
        b = it.get("b") or it.get("ball2")
        c = it.get("c") or it.get("ball3")
        if a is not None and b is not None and c is not None:
            s = int(a) + int(b) + int(c)
            num_str = f"{a}+{b}+{c}={s}"
    s = int(s) if s else 0
    big = s >= 14
    dan = s % 2 == 1
    combo = ("大" if big else "小") + ("单" if dan else "双")

    # date/time 分离
    date_raw = it.get("date") or ""
    time_raw = it.get("time") or ""
    if not date_raw and " " in str(time_raw):
        parts = str(time_raw).split(" ", 1)
        date_raw = parts[0].strip()
        time_raw = parts[1].strip() if len(parts) > 1 else ""
    if not time_raw:
        time_raw = "00:00:00"

    return {
        "nbr": str(nbr),
        "date": date_raw if re.match(r"^\d{4}-\d{2}-\d{2}$", str(date_raw)) else "",
        "time": time_raw,
        "a": int(it.get("a") or 0),
        "b": int(it.get("b") or 0),
        "c": int(it.get("c") or 0),
        "number": num_str or f"{s}",
        "sum": s,
        "combination": combo,
    }


def norm_pred_item(it, pred_type):
    """统一预测接口数据格式"""
    nbr = str(it.get("nbr") or "")
    return {
        "nbr": nbr,
        "date": it.get("date") or "",
        "time": it.get("time") or "",
        "number": it.get("number") or "",
        "num": it.get("num") or it.get("sum") or 0,
        "prediction": it.get("prediction") or it.get("predict") or "",
    }


def main():
    src = ""
    kj_data = None

    # ===== 尝试 1：pc28.help 主源 =====
    print("→ 尝试 pc28.help 主源 ...")
    try:
        d = fetch_all()
        if d["kj"].get("data"):
            kj_raw = d["kj"]["data"]
            kj_data = [norm_kj_item(x) for x in kj_raw]
            kj_data = [x for x in kj_data if x["nbr"] and x["sum"] > 0]
            # 去重 + 按期号升序
            seen = set()
            deduped = []
            for x in kj_data:
                if x["nbr"] in seen:
                    continue
                seen.add(x["nbr"])
                deduped.append(x)
            deduped.sort(key=lambda r: int(r["nbr"]))
            kj_data = deduped
            src = f"pc28.help (实时 {len(kj_data)}期)"
            print(f"  ✅ 主源成功：{len(kj_data)} 期真实数据")

            # 处理预测数据
            sha_data = [norm_pred_item(x, "sha") for x in d["sha"].get("data", [])]
            sz_data  = [norm_pred_item(x, "sz")  for x in d["sz"].get("data", [])]
            ds_data  = [norm_pred_item(x, "ds")  for x in d["ds"].get("data", [])]
            dx_data  = [norm_pred_item(x, "dx")  for x in d["dx"].get("data", [])]
        else:
            print(f"  ⚠ 主源返回空数据")
    except Exception as e:
        print(f"  ❌ 主源失败：{e}")

    # ===== 尝试 2：内置真实数据 + 本地算法 =====
    if not kj_data or len(kj_data) < 20:
        print("→ 回退到内置真实数据 + 本地形态分析算法 ...")
        seed = build_from_seed()
        kj_wrapped = seed["kj"]
        kj_data = kj_wrapped.get("data", [])
        sha_data = seed["sha"].get("data", [])
        sz_data  = seed["sz"].get("data", [])
        ds_data  = seed["ds"].get("data", [])
        dx_data  = seed["dx"].get("data", [])
        src = seed.get("source", "本地算法")
        print(f"  ✅ 本地数据：{len(kj_data)} 期")

    # ===== 组装输出 =====
    out = {
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "source": src,
        "game": "pc28",
        "kj":  {"data": kj_data},
        "sha": {"data": sha_data},
        "sz":  {"data": sz_data},
        "ds":  {"data": ds_data},
        "dx":  {"data": dx_data},
    }

    # 附加下一期预测
    if kj_data:
        sys.path.insert(0, os.path.dirname(__file__))
        import seed_data as sd
        np = sd.predict_next(kj_data, window=100)
        if np:
            out["next_prediction"] = np
            print(f"  📊 下期预测已附加：杀{np['kill']}/押{np['push']}")

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 写入 data.json ← {src[:70]}")
    if kj_data:
        print(f"   开奖数据：{len(kj_data)} 期（全部为真实数据）")
        print(f"   最早：{kj_data[0]['nbr']} {kj_data[0]['date']}")
        print(f"   最新：{kj_data[-1]['nbr']} {kj_data[-1]['date']} {kj_data[-1]['time']}")
    if out.get("next_prediction"):
        np = out["next_prediction"]
        print(f"   下期预测：杀{np['kill']} / 押{np['push']} / "
              f"和值{np['sum']} / 置信度{np['confidence']}%")


if __name__ == "__main__":
    main()
