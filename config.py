"""每日新闻线索分析 — 配置中心

修改这里即可调整监控主题、关键词、信源与时间窗。无需改动业务代码。
"""
from __future__ import annotations

import os
from datetime import time, timedelta, timezone
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------- 时区与时间窗
# GitHub Actions 使用 UTC；业务口径按北京时间。
LOCAL_TZ = ZoneInfo(os.getenv("NEWS_TZ", "Asia/Shanghai"))
RUN_HOUR = int(os.getenv("NEWS_RUN_HOUR", "10"))  # 每天 10:00 拉取
WINDOW_HOURS = int(os.getenv("NEWS_WINDOW_HOURS", "24"))  # 回溯 24 小时

# ---------------------------------------------------------------- 分类与检索式
# 每个分类下：
#   queries      -> GDELT / Google News 的检索关键词（英文为主，中文源用 zh 分类）
#   gdelt_themes -> GDELT 内置主题标签，可提升召回（可选）
#   zh_queries   -> 中文源检索关键词
CATEGORIES: dict[str, dict] = {
    "tech_ai": {
        "label": "AI · 机器人 · 具身智能",
        "color": "#6C8EEF",
        "queries": [
            'artificial intelligence',
            'generative AI model',
            'humanoid robot',
            'embodied AI robotics',
            'AI chip GPU',
            'autonomous driving',
        ],
        "gdelt_themes": ["AI_ARTIFICIAL_INTELLIGENCE", "ROBOTICS"],
        "zh_queries": ["人工智能", "大模型", "具身智能", "人形机器人", "机器人", "自动驾驶"],
    },
    "tech_ev": {
        "label": "新能源汽车 · 动力电池",
        "color": "#47B39C",
        "queries": [
            'electric vehicle EV',
            'battery technology EV',
            'solid state battery',
            'EV charging infrastructure',
            'Tesla BYD EV',
        ],
        "gdelt_themes": ["ELECTRIC_VEHICLE"],
        "zh_queries": ["新能源汽车", "动力电池", "固态电池", "充电桩", "智能驾驶"],
    },
    "politics_cn": {
        "label": "政治 · 中国",
        "color": "#E8734A",
        "queries": [
            'China government policy',
            'China diplomacy',
            'China United States relations',
            'Chinese Communist Party policy',
        ],
        "gdelt_themes": ["CHINA"],
        "zh_queries": ["中国 政策", "中美关系", "外交部", "国务院", "中国 经济政策"],
    },
    "politics_us": {
        "label": "政治 · 美国",
        "color": "#E0A244",
        "queries": [
            'US government policy',
            'White House announcement',
            'US Congress bill',
            'US China policy',
            'US Europe relations',
        ],
        "gdelt_themes": ["UNITED_STATES"],
        "zh_queries": ["美国 政府", "白宫", "美国国会", "中美 政策"],
    },
    "politics_eu": {
        "label": "政治 · 欧洲",
        "color": "#C58AF9",
        "queries": [
            'European Union policy',
            'EU regulation',
            'European Commission',
            'NATO Europe',
            'Germany France policy',
        ],
        "gdelt_themes": ["EUROPEAN_UNION", "EU"],
        "zh_queries": ["欧盟", "欧洲 政策", "北约", "德国 法国"],
    },
    "economy": {
        "label": "经济 · 宏观",
        "color": "#4FB0C6",
        "queries": [
            'global economy outlook',
            'inflation GDP growth',
            'international trade tariffs',
            'supply chain economy',
            'China economy growth',
        ],
        "gdelt_themes": ["ECONOMY", "TRADE"],
        "zh_queries": ["宏观经济", "通胀", "GDP", "贸易 关税", "供应链"],
    },
    "finance": {
        "label": "金融 · 市场",
        "color": "#E86A92",
        "queries": [
            'Federal Reserve interest rate',
            'stock market rally selloff',
            'bond yield',
            'currency forex market',
            'banking crisis finance',
        ],
        "gdelt_themes": ["FINANCE", "ECON_BANKRUPTCY"],
        "zh_queries": ["美联储", "利率", "股市", "A股", "汇率", "金融 风险"],
    },
    "military": {
        "label": "军事 · 国防",
        "color": "#8D8F98",
        "queries": [
            'military defense news',
            'NATO deployment',
            'naval exercise',
            'defense budget missile',
            'cyber warfare military',
        ],
        "gdelt_themes": ["MILITARY", "CYBER_ATTACK"],
        "zh_queries": ["军事", "国防", "北约 军演", "导弹", "台海 军事"],
    },
}

# ---------------------------------------------------------------- 信源配置
# GDELT DOC 2.0 — 全球新闻全文检索引擎，覆盖 100+ 国家、65+ 语言，无需 API Key
GDELT_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_REQUEST_INTERVAL = 6.0  # 秒；官方要求请求间隔 >= 5s
GDELT_MAX_RECORDS = int(os.getenv("GDELT_MAX_RECORDS", "150"))

# Google News RSS — 每个关键词一个 RSS 流，按 when:1d 限制近 24h
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
GOOGLE_NEWS_LOCALES = [
    {"hl": "en-US", "gl": "US", "ceid": "US:en"},
    {"hl": "zh-CN", "gl": "CN", "ceid": "CN:zh-Hans"},
]

# 媒体官方 RSS 兜底（GDELT / Google News 不可用时仍能出报告）
MEDIA_RSS: list[dict] = [
    {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "category": "tech_ai"},
    {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index", "category": "tech_ai"},
    {"name": "BBC World", "url": "https://feeds.bbci.co.uk/news/world/rss.xml", "category": "politics_eu"},
    {"name": "BBC Business", "url": "https://feeds.bbci.co.uk/news/business/rss.xml", "category": "economy"},
    {"name": "NYT World", "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml", "category": "politics_us"},
    {"name": "Defense News", "url": "https://www.defensenews.com/arc/outboundfeeds/rss/", "category": "military"},
    {"name": "央视网科技", "url": "https://news.cctv.com/tech/rss.xml", "category": "tech_ai"},
]

# 热榜补充（国内科技情绪）。留空则跳过。
HOT_API_BASE = os.getenv("HOT_API_BASE", "https://api-hot.imsyy.top")

# 媒体 RSS 相关性过滤：每个分类的强信号词（命中任一即保留）
# 用于剔除媒体综合流里的航天、健康、文化等无关内容
RELEVANCE_KEYWORDS: dict[str, list[str]] = {
    "tech_ai": [
        "artificial intelligence", " ai ", "ai-", "machine learning", "robot",
        "autonomous", "chip", "gpu", "nvidia", "openai", "cyber",
        "hacker", "algorithm", "大模型", "机器人", "人工智能",
        "芯片", "自动驾驶", "智能",
    ],
    "tech_ev": [
        "electric vehicle", "ev", "battery", "tesla", "byd", "charging",
        "automaker", "car", "新能源汽车", "电池", "汽车",
    ],
    "politics_cn": ["china", "chinese", "beijing", "xi jinping", "中国", "中美"],
    "politics_us": [
        "white house", "congress", "trump", "biden", "u.s. government",
        "pentagon", "american", "united states", "美国", "白宫",
    ],
    "politics_eu": [
        "european union", "brussels", "nato", "germany", "france",
        "europe", "欧盟", "北约", "欧洲",
    ],
    "economy": [
        "economy", "economic", "inflation", "gdp", "trade", "tariff",
        "supply chain", "recession", "growth", "经济", "通胀", "贸易",
    ],
    "finance": [
        "federal reserve", "interest rate", "stock", "market",
        "bond", "currency", "bank", "investor", "美联储", "利率", "股市",
    ],
    "military": [
        "military", "defense", "defence", "army", "navy", "air force",
        "missile", "warship", "warmonger", "troops", "pentagon", "weapon",
        "军事", "国防", "导弹", "军演",
    ],
}

# ---------------------------------------------------------------- 采集与筛选
MAX_ARTICLES_PER_CATEGORY = int(os.getenv("MAX_ARTICLES_PER_CATEGORY", "120"))
MIN_TITLE_LEN = 8
DEDUPE_SIMILARITY = 0.72  # 标题相似度阈值
FETCH_TIMEOUT = 20  # 秒
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 DailyNewsLeads/1.0"

# ---------------------------------------------------------------- LLM
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
LLM_BATCH_SIZE = int(os.getenv("LLM_BATCH_SIZE", "12"))  # 每批送入的文章数
LLM_MAX_TOKENS = 8192


def compute_window() -> tuple:
    """返回 (start, end) 北京时间对象，表示 [昨日10:00, 今日10:00)。"""
    from datetime import datetime

    now = datetime.now(LOCAL_TZ)
    today_run = now.replace(hour=RUN_HOUR, minute=0, second=0, microsecond=0)
    end = today_run if now >= today_run else today_run - timedelta(days=1)
    start = end - timedelta(hours=WINDOW_HOURS)
    return start, end
