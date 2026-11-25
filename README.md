# SIGNAL · 每日新闻线索分析

每天北京时间 10:00 自动采集前一日 10:00 至当日 10:00 的全球新闻，经去重与正文抽取后，由 Gemini 提炼为结构化新闻线索，输出 **Markdown 报告 + 网页看板**。

## 覆盖范围

| 板块 | 主题 |
|---|---|
| 科技 | AI、大模型、机器人、具身智能、AI 芯片、自动驾驶 |
| 科技 | 新能源汽车、动力电池、固态电池、充电设施 |
| 政治 | 中国、美国、欧洲（欧盟/北约/德法） |
| 经济 | 宏观经济、通胀、GDP、贸易关税、供应链 |
| 金融 | 美联储、利率、股市、汇率、银行风险 |
| 军事 | 国防、北约部署、军演、导弹、网络战 |

## 数据链路

```
GDELT DOC 2.0（全球 100+ 国家 / 65+ 语言）
Google News RSS（按主题 + when:1d）
媒体官方 RSS（The Verge / Ars / BBC / NYT / Defense News 等兜底）
国内科技热榜（DailyHotApi 风格端点）
        ↓ 24h 时间窗过滤 + URL/标题跨源去重 + 正文抽取
Gemini 2.5 Flash（免费额度）→ 合并同源报道、事实校验、影响研判
        ↓
outputs/news-leads-YYYY-MM-DD.md  +  data.js  →  网页看板
```

**任何单一信源失败都不会中断整体流程**，错误会记录在报告的「运行提示」中。

## 本地运行

```bash
pip install -r requirements.txt
cp .env.example .env        # 填入 GEMINI_API_KEY
python main.py              # 完整运行
python main.py --dry-run    # 不调用 LLM，验证采集链路
```

产物：
- `data.js` — 看板数据源（页面通过 `<script src="data.js">` 加载）
- `outputs/news-leads-YYYY-MM-DD.md` — 当日报告

直接双击 `index.html` 即可查看看板。

## 部署到 GitHub Actions（免费）

### 1. 创建仓库并推送

```bash
git init
git add .
git commit -m "init: daily news leads pipeline"
git remote add origin https://github.com/<你的用户名>/daily-news-leads.git
git push -u origin main
```

### 2. 配置 Secrets

进入仓库 **Settings → Secrets and variables → Actions → New repository secret**：

| 名称 | 值 | 说明 |
|---|---|---|
| `GEMINI_API_KEY` | `AQ...` 或 `AIza...` | [Google AI Studio](https://aistudio.google.com/app/apikey) 免费获取 |

可选 Variables：`GEMINI_MODEL`（默认 `gemini-2.5-flash`）。

> **新版 AQ. Key 注意事项**：2026 年 5 月起 AI Studio 只发 `AQ.` 前缀的 53 字符 Authentication Key。
> 代码已按官方推荐用 `x-goog-api-key` 请求头传递。若遇到 `401 ACCESS_TOKEN_TYPE_UNSUPPORTED`，
> 请先在 AI Studio 的 Key 详情页点 **Copy key** 确认复制了完整 53 字符，并确认该项目已启用 Gemini API。
> 可在 Actions 里临时加一步 `python check_key.py` 做预检（见下文）。

### 3. 启用定时

工作流文件 `.github/workflows/daily.yml` 已配置 `cron: '0 2 * * *'`（UTC 02:00 = 北京 10:00）。推送后自动生效，也可以在 Actions 页面手动点 **Run workflow** 立即测试。

> GitHub Actions 免费额度：公开仓库无限分钟；私有仓库每月 2000 分钟。本管线每天约跑 5–15 分钟，完全在免费范围内。
> 定时触发可能延迟 5–30 分钟（GitHub 高峰期常见），如需精确到分钟请改用 Oracle Cloud 永久免费 ARM 机。

### 4. 查看结果

- 网页看板：仓库开启 **Settings → Pages → Source: Deploy from a branch → main**，即可通过 `https://<用户名>.github.io/<仓库名>/` 访问，每天自动更新。
- Markdown 报告：仓库 `outputs/` 目录。

## 关键配置（`config.py`）

- `CATEGORIES` — 主题分类与检索式，增删板块只需改这里
- `GDELT_REQUEST_INTERVAL` — GDELT 请求间隔，官方要求 ≥ 5 秒，默认 6 秒
- `MAX_ARTICLES_PER_CATEGORY` — 每类送入 LLM 的最大文章数，控制 token 成本
- `LLM_BATCH_SIZE` — 每批送入 LLM 的文章数
- `MEDIA_RSS` — 媒体源列表

## Gemini 免费额度说明

Gemini API 免费层对 `gemini-2.5-flash` 提供每日请求配额，本管线每天约 10–20 次调用，远低于免费上限。免费层的数据可能被 Google 用于改进产品，若涉及敏感内容请改用付费层或本地模型。

## 常见问题

**Q: 报告里很多"待分析（当前为无 Key 降级输出）"？**
A: 说明 `GEMINI_API_KEY` 未生效。检查 Secrets 名称是否完全一致，或在本地 `.env` 中配置（可用 `python-dotenv` 加载）。

**Q: 怎么验证我的 Key 到底能不能用？**
A: 运行 `python check_key.py`，它会依次检查格式、网络、认证和实际生成四步并给出诊断。注意本地若屏蔽 Google 域名会卡在「网络连通性」一步，此时应把脚本放到 GitHub Actions 或境外服务器跑。

**Q: GDELT 返回 429？**
A: 本地出口 IP 可能与其他用户共享。GitHub Actions 的出口 IP 通常不受影响；也可增大 `GDELT_REQUEST_INTERVAL` 到 10 秒。

**Q: 想加新的新闻主题？**
A: 在 `config.py` 的 `CATEGORIES` 中新增一个键，填写 `label`、`color`、`queries`、`gdelt_themes`、`zh_queries`，看板会自动出现对应筛选标签。
