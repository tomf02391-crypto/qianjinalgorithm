# 千金星轨 · 福彩3D 预测（GitHub Pages 版）

纯静态站点，部署到 GitHub Pages 即可使用，无需服务器。

## 📁 文件结构

```
qianjinu-ghpages/
├── index.html                     ← 主页面（单文件，CSS/JS 全内联）
├── data.json                      ← 100 期真实开奖数据（Actions 自动更新）
├── fetch_data.py                  ← Actions 调用的抓取脚本
├── setup_repo.sh                  ← 一键建仓+推送脚本
├── README.md                      ← 本文件
└── .github/
    └── workflows/
        └── update-data.yml        ← 每天 21:30 自动抓数据并 commit
```

## 🔗 数据链路（自动降级）

| 优先级 | 数据源 | 说明 |
|--------|--------|------|
| ① | `yu28.top` 直连 | 开奖历史 + 杀组/双组/单双/大小 4 路 AI 预测 |
| ② | `corsproxy.io` → yu28 | 直连被 CORS 拦截时自动切换 |
| ③ | 同目录 `data.json` | Actions 用福彩官网 `cwl.gov.cn` 生成兜底 |

右上角徽章实时显示当前用哪一档数据源。

## 🚀 部署方式一：让 AI 帮你一键推（推荐）

在对话里提供两个信息：
1. 你的 **GitHub 用户名**
2. 一个 **Personal Access Token (PAT)**，权限勾选 `repo`（全选）

AI 会调用 `setup_repo.sh` 自动完成建仓、推送、输出 Pages 地址。

## 🚀 部署方式二：自己手动推

```bash
# 1. 克隆/拷入本目录后初始化
cd qianjinu-ghpages
git init && git checkout -b main
git add . && git commit -m "init"

# 2. 在 GitHub 网页上建一个公开仓库（如 qianjinu-ghpages）
# 3. 推送
git remote add origin https://<USER>:<TOKEN>@github.com/<USER>/qianjinu-ghpages.git
git push -u origin main
```

## ⚙️ 开启 GitHub Pages

1. 打开 `https://github.com/<你>/qianjinu-ghpages/settings/pages`
2. **Source** 选 `Deploy from a branch`
3. **Branch** 选 `main` → Save
4. 等待 1-2 分钟，访问 `https://<你>.github.io/qianjinu-ghpages/`

## ⚡ 首次手动触发 Actions

仓库刚建好时 `data.json` 还不存在，需要手动跑一次工作流生成它：

1. 打开 `https://github.com/<你>/qianjinu-ghpages/actions`
2. 选 `更新数据快照` → `Run workflow` → 确认
3. 等约 30 秒变绿勾，页面即可正常显示数据

之后每天北京时间 **21:30**（开奖后 15 分钟）会自动跑一次。

## 🔑 关于 yu28 API Key

`index.html` 中已内置公开 Demo Key `yu28_f9f41d673b447fac`，文档允许前端使用。
如要换成你自己的 Key：
1. 去 https://yu28.top 注册获取
2. 替换 `index.html` 里 `CONFIG.API_KEY` 的值
3. 重新推送

## ⚠️ 声明

仅供算法研究参考，彩票开奖为随机事件，任何预测均无法保证准确，请理性对待。