#!/usr/bin/env python3
"""
fetch_data.py — GitHub Actions 每天 21:30 调用
数据源：福彩官网 cwl.gov.cn（服务端可达、无需 Key）
输出：data.json（供 index.html 在 API 不可用时兜底）
"""
import json, urllib.request, datetime

CWL = "https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def fetch_recent(n=100):
    url = f"{CWL}?name=3d&issueCount={n}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())

def to_kj_format(items):
    """把福彩 result 转成和 yu28 kj 接口一致的 shape，便于前端复用"""
    out = []
    for it in items:
        red = it.get("red", "") or ""
        nums = [int(x) for x in red.split(",") if x.strip()]
        if len(nums) != 3:
            continue
        a, b, c = nums
        s = a + b + c
        big = s >= 14
        dan = s % 2 == 1
        combo = ("大" if big else "小") + ("单" if dan else "双")
        out.append({
            "nbr": str(it["code"]),
            "time": it.get("date", "").replace("(一)", "").replace("(二)", "")
                    .replace("(三)", "").replace("(四)", "").replace("(五)", "")
                    .replace("(六)", "").replace("(日)", "").strip(),
            "number": f"{a}+{b}+{c}={s}",
            "combination": combo,
        })
    return out

def main():
    raw = fetch_recent(100)
    items = raw.get("result") or raw.get("data") or []
    kj = to_kj_format(items)
    kj.sort(key=lambda x: int(x["nbr"]))  # 升序

    out = {
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "source": "cwl.gov.cn",
        "kj": {"data": kj},
        # 预测字段留空——由前端基于历史用本地算法生成
        "sha": {"data": []}, "sz": {"data": []},
        "ds":  {"data": []}, "dx": {"data": []},
    }
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"OK · 写入 {len(kj)} 期 → data.json（最新 {kj[-1]['nbr']}）")

if __name__ == "__main__":
    main()
