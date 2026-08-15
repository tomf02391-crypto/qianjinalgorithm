# 千金星轨 · PC28

> 真实数据驱动的 PC28（加拿大28）开奖分析 + AI 预测面板，纯静态单页，零后端，可直接部署到 GitHub Pages。

## 🎯 这是什么

- **PC28 每 3.5 分钟开一期**，全天约 400 期
- 和值 0–27，**≥14 为大，<14 为小**；**奇数为单，偶数为双**
- 数据源：`yu28.top` 开放平台（4 路预测：杀组 / 双组 / 单双 / 大小）
- 完全免费、无需服务器、无需数据库

## 📊 数据架构（三档自动降级）

| 优先级 | 来源 | 触发条件 |
|--------|------|----------|
| ① | `yu28.top` 直连 | 浏览器能直连（部分网络放行） |
| ② | `corsproxy.io` → `yu28.top` | 直连被 CORS 拦截时自动切换 |
| ③ | 同目录 `data.json` | 上面全挂时兜底（内置 121 期真实开奖数据） |

> 页面右上角徽章实时显示当前用哪一档：`● 真实数据 · yu28 直连` / `● 真实数据 · corsproxy.io` / `● 静态快照 · data.json`

## 🚀 部署到 GitHub Pages

1. **建仓库**：在 GitHub 上新建公开仓库（如 `qianjinu-ghpages`）
2. **推送代码**：
   ```bash
   git init && git add . && git commit -m "init"
   git remote add origin https://github.com/<你>/<仓库>.git
   git push -u origin main
   ```
3. **开启 Pages**：Settings → Pages → Source 选 `main` 分支 → Save
4. 等待 1–2 分钟，访问 `https://<你>.github.io/<仓库>/`

## 🔄 自动更新（GitHub Actions）

`.github/workflows/update-data.yml` 每 5 分钟运行一次：
- 尝试通过 `corsproxy.io` 抓取 `yu28.top` 最新 350 期开奖 + 4 路预测
- 抓取成功 → 写入 `data.json` 并 commit
- 抓取失败 → 回退到内置真实数据汇编（jnd25.com / kuai28.com 等公开记录）
- **维护窗口（北京时间 19:00–19:30）自动跳过**

> ⚠️ 由于 PC28 数据站统一使用 WAF 屏蔽云服务器 IP，Actions 服务端抓取可能不稳定。这是行业普遍现象——**真实数据永远来自浏览器端**。Actions 的角色是"定期刷新兜底快照"，确保即使断网/被屏蔽，页面仍有真实历史可看。

## 📁 文件结构

```
.
├── index.html               # 主页面（CSS+JS 全内联，单文件）
├── data.json               # 开奖数据快照（Actions 自动更新）
├── fetch_data.py           # Actions 抓取脚本
├── seed_data.py            # 内置真实数据汇编（兜底用）
├── README.md
└── .github/workflows/
    └── update-data.yml    # 每5分钟自动更新
```

## 🛠 本地调试

```bash
# 生成 data.json（测试兜底路径）
python3 fetch_data.py

# 启动本地服务器（必须 http:// 才能 fetch）
python3 -m http.server 8000
# 浏览器打开 http://localhost:8000/
```

## ⚠️ 声明

**仅供算法研究与数据分析参考**。彩票开奖为独立随机事件，任何预测模型均无法保证准确，请理性对待。

## 📜 License

MIT
