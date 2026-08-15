# 千金星轨 · PC28 真实数据版

> 数据来源：yu28.top 开放平台 + 本地形态分析算法兜底
> 仅供算法研究参考，彩票开奖为随机事件，请理性对待

## 文件说明

| 文件 | 作用 |
|------|------|
| `index.html` | 主页面（单文件，CSS/JS 全内联） |
| `data.json` | 开奖数据 + AI 预测（Actions 自动更新） |
| `fetch_data.py` | Actions 抓取脚本 |
| `seed_data.py` | 内置真实数据 + 本地预测算法 |

## 数据链路（三档降级）

1. **yu28 直连** → 浏览器直接调 `yu28.top`（含4路AI预测）
2. **corsproxy.io 代理** → 直连被拦时自动切换
3. **data.json 静态兜底** → 含本地算法生成的杀组/押组/单双/大小预测

## 部署

已部署到 GitHub Pages：`https://tomf02391-crypto.github.io/qianjinalgorithm/`

Actions 每 5 分钟自动抓取最新数据并 commit。
