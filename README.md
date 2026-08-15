# 千金星轨 · PC28 真实数据预测

> 数据源：pc28.help（浏览器直连）+ yu28.top（预测接口）+ GitHub Actions 自动兜底

## 功能
- 倒计时（pc28.help 真实 countdown）
- 4 路 AI 预测：杀组 / 押组 / 单双 / 大小 / 和值重心
- 近 100 期回测：杀组正确率 / 押组命中率 / 和值命中率
- 形态分布统计（大单/大双/小单/小双）
- 数据链路三档降级：pc28.help 直连 → yu28 代理 → data.json 静态兜底

## 部署
1. Settings → Pages → Source: `main` 分支 → Save
2. Actions → "更新PC28数据快照" → Run workflow（手动跑一次）
3. 之后每 5 分钟自动更新

## 技术栈
- 纯静态单页（零外部依赖，CSS/JS 全内联）
- GitHub Pages 托管
- GitHub Actions 定时抓取

## 声明
仅供算法研究参考，彩票开奖为随机事件，请理性对待。
