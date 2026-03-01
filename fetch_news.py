# -*- coding: utf-8 -*-
"""
每日科技资讯抓取与推送脚本

功能说明：
  1. 从多个 RSS 订阅源抓取过去 24 小时内发布的科技资讯
  2. 同时从 Hacker News 获取热门帖子作为海外科技动态补充
  3. 生成一份精美的 HTML 新闻页面，部署到 GitHub Pages
  4. 通过 Server酱 API 推送摘要和页面链接到微信

数据来源：
  - 36氪（快讯 RSS）
  - IT之家（RSS）
  - 少数派（RSS）
  - Hacker News（官方 API，取当日热榜 Top 15）
  - Solidot（RSS）

开发者：maorongkang@gmail.com
"""

import os
import sys
import time
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import requests

# ========================================
# 日志配置
# ========================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ========================================
# 常量与配置
# ========================================

# 北京时间时区（UTC+8）
BEIJING_TZ = timezone(timedelta(hours=8))

# 抓取范围：过去 24 小时
HOURS_LOOKBACK = 24

# Server酱 API 地址模板
# 文档：https://sct.ftqq.com/
SERVERCHAN_API_URL = "https://sctapi.ftqq.com/{sendkey}.send"

# GitHub Pages 基础地址（推送后会更新为实际地址）
# 格式为 https://<用户名>.github.io/<仓库名>/
GITHUB_PAGES_BASE = os.environ.get("GITHUB_PAGES_URL", "")

# 输出目录（GitHub Pages 用）
OUTPUT_DIR = Path("public")

# RSS 订阅源列表
RSS_SOURCES = [
    {
        "name": "36氪 · 快讯",
        "url": "https://36kr.com/feed",
        "emoji": "📊",
        "color": "#2F5D8A",  # 商务蓝
    },
    {
        "name": "IT之家",
        "url": "https://www.ithome.com/rss/",
        "emoji": "💻",
        "color": "#2E6A57",  # 墨绿
    },
    {
        "name": "少数派",
        "url": "https://sspai.com/feed",
        "emoji": "📱",
        "color": "#8A5A1F",  # 暖棕
    },
    {
        "name": "Solidot",
        "url": "https://www.solidot.org/index.rss",
        "emoji": "🔬",
        "color": "#2C6275",  # 深青蓝
    },
]

# Hacker News 官方 API
HN_TOP_STORIES_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{item_id}.json"
HN_ITEM_WEB_URL = "https://news.ycombinator.com/item?id={item_id}"
HN_TOP_N = 15


# ========================================
# RSS 源抓取逻辑
# ========================================


def fetch_rss_news(source: dict, cutoff_time: datetime) -> list[dict]:
    """
    从单个 RSS 源抓取指定时间范围内的文章

    参数:
        source: 包含 name, url, emoji, color 的字典
        cutoff_time: 截止时间，只返回这个时间之后发布的文章

    返回:
        文章列表
    """
    articles = []
    feed_url = source["url"]
    source_name = source["name"]

    logger.info(f"正在抓取 RSS 源: {source_name} ({feed_url})")

    try:
        feed = feedparser.parse(feed_url)

        if feed.bozo and not feed.entries:
            logger.warning(f"解析 {source_name} 的 RSS 失败: {feed.bozo_exception}")
            return articles

        for entry in feed.entries:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()

            if not title or not link:
                continue

            # 解析发布时间
            published_parsed = entry.get("published_parsed") or entry.get("updated_parsed")

            if published_parsed:
                pub_time = datetime(*published_parsed[:6], tzinfo=timezone.utc)
                if pub_time < cutoff_time:
                    continue
            else:
                pub_time = None

            # 尝试提取摘要（用于 HTML 页面展示）
            summary = entry.get("summary", "")
            # 简单清理 HTML 标签，只保留纯文本
            if summary:
                import re
                summary = re.sub(r"<[^>]+>", "", summary).strip()
                # 截取前 120 个字符作为摘要
                if len(summary) > 120:
                    summary = summary[:120] + "..."

            articles.append({
                "title": title,
                "link": link,
                "published": pub_time,
                "summary": summary,
                "source": source_name,
                "emoji": source["emoji"],
                "color": source.get("color", "#2F5D8A"),
            })

        logger.info(f"从 {source_name} 获取到 {len(articles)} 篇文章")

    except Exception as e:
        logger.error(f"抓取 {source_name} 时出错: {e}")

    return articles


def fetch_all_rss_news(cutoff_time: datetime) -> list[dict]:
    """遍历所有 RSS 源，汇总抓取结果"""
    all_articles = []

    for source in RSS_SOURCES:
        articles = fetch_rss_news(source, cutoff_time)
        all_articles.extend(articles)
        time.sleep(1)

    return all_articles


# ========================================
# Hacker News 抓取逻辑
# ========================================


def fetch_hacker_news(top_n: int = HN_TOP_N) -> list[dict]:
    """从 Hacker News 官方 API 获取当前热榜"""
    articles = []
    logger.info(f"正在抓取 Hacker News 热榜 Top {top_n}")

    try:
        resp = requests.get(HN_TOP_STORIES_URL, timeout=15)
        resp.raise_for_status()
        story_ids = resp.json()[:top_n]

        for story_id in story_ids:
            try:
                item_resp = requests.get(
                    HN_ITEM_URL.format(item_id=story_id),
                    timeout=10,
                )
                item_resp.raise_for_status()
                item = item_resp.json()

                if not item or item.get("type") != "story":
                    continue

                title = item.get("title", "").strip()
                link = item.get("url") or HN_ITEM_WEB_URL.format(item_id=story_id)
                score = item.get("score", 0)
                descendants = item.get("descendants", 0)  # 评论数

                articles.append({
                    "title": title,
                    "link": link,
                    "score": score,
                    "comments": descendants,
                    "hn_id": story_id,
                    "source": "Hacker News",
                    "emoji": "🔥",
                    "color": "#C23A3A",
                })

            except Exception as e:
                logger.warning(f"获取 HN 帖子 {story_id} 详情失败: {e}")
                continue

            time.sleep(0.3)

        logger.info(f"从 Hacker News 获取到 {len(articles)} 条帖子")

    except Exception as e:
        logger.error(f"抓取 Hacker News 热榜失败: {e}")

    return articles


# ========================================
# HTML 页面生成（核心：好看的浅色调新闻界面）
# ========================================


def generate_html_page(rss_articles: list[dict], hn_articles: list[dict]) -> str:
    """
    生成一份精美的 HTML 新闻页面

    设计原则：
    - 浅色调，以白色和浅灰为主背景
    - 商务蓝灰色系作为品牌色点缀
    - 卡片式布局，层级清晰
    - 移动端适配，微信里打开也好看
    - 不搞花哨的动画和渐变，走专业路线

    参数:
        rss_articles: 国内 RSS 源的文章列表
        hn_articles: Hacker News 帖子列表

    返回:
        完整的 HTML 字符串
    """
    now_beijing = datetime.now(BEIJING_TZ)
    date_str = now_beijing.strftime("%Y年%m月%d日")
    date_short = now_beijing.strftime("%m.%d")
    weekday_map = ["一", "二", "三", "四", "五", "六", "日"]
    weekday = weekday_map[now_beijing.weekday()]
    time_str = now_beijing.strftime("%H:%M")

    # 按来源分组国内资讯
    sources_grouped: dict[str, list[dict]] = {}
    for article in rss_articles:
        src = article["source"]
        if src not in sources_grouped:
            sources_grouped[src] = []
        sources_grouped[src].append(article)

    # 生成国内资讯的 HTML 卡片
    domestic_cards_html = ""
    for source_name, articles in sources_grouped.items():
        emoji = articles[0].get("emoji", "📌")
        color = articles[0].get("color", "#2F5D8A")

        items_html = ""
        for i, article in enumerate(articles[:10]):
            title = _escape_html(article["title"])
            link = _escape_html(article["link"])
            summary = _escape_html(article.get("summary", ""))

            # 格式化发布时间
            time_badge = ""
            if article.get("published"):
                pub_beijing = article["published"].astimezone(BEIJING_TZ)
                time_badge = f'<span class="news-time">{pub_beijing.strftime("%H:%M")}</span>'

            # 如果有摘要就显示
            summary_html = ""
            if summary:
                summary_html = f'<p class="news-summary">{summary}</p>'

            items_html += f"""
            <a href="{link}" target="_blank" class="news-item" rel="noopener">
                <div class="news-item-header">
                    <span class="news-index" style="background:{color};">{i + 1}</span>
                    <h3 class="news-title">{title}</h3>
                    {time_badge}
                </div>
                {summary_html}
            </a>
            """

        overflow_note = ""
        if len(articles) > 10:
            overflow_note = f'<p class="overflow-note">还有 {len(articles) - 10} 条未展示</p>'

        domestic_cards_html += f"""
        <div class="source-section">
            <div class="source-header">
                <span class="source-icon">{emoji}</span>
                <span class="source-name">{source_name}</span>
                <span class="source-count">{len(articles)} 条</span>
            </div>
            <div class="news-list">
                {items_html}
            </div>
            {overflow_note}
        </div>
        """

    # 生成 Hacker News 部分的 HTML
    hn_items_html = ""
    if hn_articles:
        for i, article in enumerate(hn_articles):
            title = _escape_html(article["title"])
            link = _escape_html(article["link"])
            score = article.get("score", 0)
            comments = article.get("comments", 0)
            hn_id = article.get("hn_id", "")

            # 根据分数决定热度标签的样式
            heat_class = "heat-normal"
            if score >= 300:
                heat_class = "heat-hot"
            elif score >= 100:
                heat_class = "heat-warm"

            hn_items_html += f"""
            <div class="hn-item">
                <div class="hn-rank">{i + 1}</div>
                <div class="hn-content">
                    <a href="{link}" target="_blank" class="hn-title-link" rel="noopener">
                        <h3 class="hn-title">{title}</h3>
                    </a>
                    <div class="hn-meta">
                        <span class="hn-score {heat_class}">▲ {score}</span>
                        <a href="https://news.ycombinator.com/item?id={hn_id}" target="_blank"
                           class="hn-comments" rel="noopener">💬 {comments}</a>
                    </div>
                </div>
            </div>
            """

    # 没有数据时的提示
    if not domestic_cards_html:
        domestic_cards_html = """
        <div class="empty-state">
            <span class="empty-icon">📭</span>
            <p>暂无新资讯，RSS 源可能尚未更新</p>
        </div>
        """

    if not hn_items_html:
        hn_items_html = """
        <div class="empty-state">
            <span class="empty-icon">🌐</span>
            <p>Hacker News 数据暂时获取失败</p>
        </div>
        """

    # 统计信息
    total_count = len(rss_articles) + len(hn_articles)
    source_count = len(sources_grouped) + (1 if hn_articles else 0)

    # 拼装完整的 HTML 页面
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>科技日报 · {date_str}</title>
    <meta name="description" content="{date_str}的科技资讯汇总，涵盖国内外科技动态">
    <style>
        /* ======================================== */
        /* 基础重置与全局变量                         */
        /* 设计风格：浅色调、商务蓝灰、专业工作台感    */
        /* ======================================== */

        :root {{
            /* 基础层 - 浅色调背景体系 */
            --bg-page: #F5F7FA;
            --bg-surface: #FFFFFF;
            --bg-subtle: #EEF2F6;
            --bg-hover: #F8FAFC;

            /* 边框 */
            --border-default: #DDE3EA;
            --border-strong: #C8D1DC;
            --border-light: #E8ECF1;

            /* 文字 */
            --text-primary: #1F2937;
            --text-secondary: #4B5563;
            --text-muted: #6B7280;
            --text-disabled: #9CA3AF;

            /* 品牌色 - 低饱和商务蓝 */
            --brand-primary: #2F5D8A;
            --brand-hover: #274F75;
            --brand-soft: #EAF2FA;
            --brand-soft-border: #C9DBEE;

            /* 语义色 */
            --success-text: #2F6B43;
            --success-bg: #EAF6EE;
            --warning-text: #8A5A1F;
            --warning-bg: #FFF5E8;
            --error-text: #8A2C2C;
            --error-bg: #FDEEEE;

            /* 圆角 */
            --radius-sm: 8px;
            --radius-md: 10px;
            --radius-lg: 12px;

            /* 阴影 - 柔和低对比 */
            --shadow-sm: 0 1px 3px rgba(0, 0, 0, 0.04), 0 1px 2px rgba(0, 0, 0, 0.03);
            --shadow-md: 0 4px 12px rgba(0, 0, 0, 0.05), 0 1px 3px rgba(0, 0, 0, 0.03);
            --shadow-lg: 0 8px 24px rgba(0, 0, 0, 0.06), 0 2px 6px rgba(0, 0, 0, 0.03);
        }}

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI",
                         "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei",
                         "Helvetica Neue", Helvetica, Arial, sans-serif;
            background-color: var(--bg-page);
            color: var(--text-primary);
            line-height: 1.6;
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
        }}

        /* ======================================== */
        /* 页面容器                                   */
        /* ======================================== */

        .container {{
            max-width: 680px;
            margin: 0 auto;
            padding: 20px 16px 40px;
        }}

        /* ======================================== */
        /* 顶部头部区域                               */
        /* ======================================== */

        .header {{
            background: var(--bg-surface);
            border-radius: var(--radius-lg);
            padding: 28px 24px;
            margin-bottom: 20px;
            border: 1px solid var(--border-light);
            box-shadow: var(--shadow-sm);
        }}

        .header-top {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 16px;
        }}

        .header-brand {{
            display: flex;
            align-items: center;
            gap: 10px;
        }}

        .header-logo {{
            width: 40px;
            height: 40px;
            background: var(--brand-soft);
            border: 1px solid var(--brand-soft-border);
            border-radius: var(--radius-sm);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 20px;
        }}

        .header-title {{
            font-size: 18px;
            font-weight: 600;
            color: var(--text-primary);
            letter-spacing: -0.3px;
        }}

        .header-date-badge {{
            display: flex;
            align-items: center;
            gap: 6px;
            padding: 6px 12px;
            background: var(--bg-subtle);
            border-radius: 20px;
            font-size: 13px;
            color: var(--text-secondary);
            border: 1px solid var(--border-light);
        }}

        .header-divider {{
            height: 1px;
            background: var(--border-light);
            margin-bottom: 16px;
        }}

        .header-stats {{
            display: flex;
            gap: 24px;
        }}

        .stat-item {{
            display: flex;
            flex-direction: column;
            gap: 2px;
        }}

        .stat-value {{
            font-size: 22px;
            font-weight: 700;
            color: var(--brand-primary);
            line-height: 1.2;
        }}

        .stat-label {{
            font-size: 12px;
            color: var(--text-muted);
        }}

        /* ======================================== */
        /* 分区标题                                   */
        /* ======================================== */

        .section-title {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 0 4px;
            margin-bottom: 12px;
            margin-top: 8px;
        }}

        .section-flag {{
            font-size: 15px;
        }}

        .section-text {{
            font-size: 15px;
            font-weight: 600;
            color: var(--text-primary);
        }}

        .section-line {{
            flex: 1;
            height: 1px;
            background: var(--border-default);
        }}

        /* ======================================== */
        /* 来源分区卡片                               */
        /* ======================================== */

        .source-section {{
            background: var(--bg-surface);
            border-radius: var(--radius-lg);
            border: 1px solid var(--border-light);
            margin-bottom: 12px;
            overflow: hidden;
            box-shadow: var(--shadow-sm);
        }}

        .source-header {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 14px 18px;
            border-bottom: 1px solid var(--border-light);
            background: var(--bg-subtle);
        }}

        .source-icon {{
            font-size: 16px;
        }}

        .source-name {{
            font-size: 14px;
            font-weight: 600;
            color: var(--text-primary);
            flex: 1;
        }}

        .source-count {{
            font-size: 12px;
            color: var(--text-muted);
            padding: 2px 8px;
            background: var(--bg-surface);
            border-radius: 10px;
            border: 1px solid var(--border-default);
        }}

        /* ======================================== */
        /* 新闻条目                                   */
        /* ======================================== */

        .news-list {{
            padding: 4px 0;
        }}

        .news-item {{
            display: block;
            padding: 12px 18px;
            text-decoration: none;
            color: inherit;
            border-bottom: 1px solid var(--border-light);
            transition: background-color 0.15s ease;
        }}

        .news-item:last-child {{
            border-bottom: none;
        }}

        .news-item:hover {{
            background-color: var(--bg-hover);
        }}

        .news-item-header {{
            display: flex;
            align-items: flex-start;
            gap: 10px;
        }}

        .news-index {{
            flex-shrink: 0;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 22px;
            height: 22px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 600;
            color: #FFFFFF;
            margin-top: 2px;
        }}

        .news-title {{
            flex: 1;
            font-size: 14px;
            font-weight: 500;
            color: var(--text-primary);
            line-height: 1.5;
        }}

        .news-time {{
            flex-shrink: 0;
            font-size: 12px;
            color: var(--text-disabled);
            margin-top: 3px;
        }}

        .news-summary {{
            margin-top: 6px;
            margin-left: 32px;
            font-size: 13px;
            color: var(--text-muted);
            line-height: 1.5;
        }}

        .overflow-note {{
            padding: 10px 18px;
            font-size: 13px;
            color: var(--text-muted);
            text-align: center;
            border-top: 1px solid var(--border-light);
            background: var(--bg-subtle);
        }}

        /* ======================================== */
        /* Hacker News 专区                          */
        /* ======================================== */

        .hn-section {{
            background: var(--bg-surface);
            border-radius: var(--radius-lg);
            border: 1px solid var(--border-light);
            margin-bottom: 12px;
            overflow: hidden;
            box-shadow: var(--shadow-sm);
        }}

        .hn-header {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 14px 18px;
            border-bottom: 1px solid var(--border-light);
            background: var(--bg-subtle);
        }}

        .hn-item {{
            display: flex;
            align-items: flex-start;
            gap: 12px;
            padding: 12px 18px;
            border-bottom: 1px solid var(--border-light);
            transition: background-color 0.15s ease;
        }}

        .hn-item:last-child {{
            border-bottom: none;
        }}

        .hn-item:hover {{
            background-color: var(--bg-hover);
        }}

        .hn-rank {{
            flex-shrink: 0;
            width: 24px;
            height: 24px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            font-weight: 700;
            color: var(--text-muted);
            background: var(--bg-subtle);
            border-radius: 6px;
            margin-top: 1px;
        }}

        .hn-content {{
            flex: 1;
            min-width: 0;
        }}

        /* HN 标题链接：去掉默认下划线，保持颜色 */
        .hn-title-link {{
            text-decoration: none;
            color: inherit;
        }}

        .hn-title-link:hover .hn-title {{
            color: var(--brand-primary);
        }}

        .hn-title {{
            font-size: 14px;
            font-weight: 500;
            color: var(--text-primary);
            line-height: 1.5;
            word-break: break-word;
        }}

        .hn-meta {{
            display: flex;
            align-items: center;
            gap: 12px;
            margin-top: 4px;
        }}

        .hn-score {{
            font-size: 12px;
            font-weight: 600;
            padding: 1px 6px;
            border-radius: 4px;
        }}

        .heat-normal {{
            color: var(--text-muted);
            background: var(--bg-subtle);
        }}

        .heat-warm {{
            color: var(--warning-text);
            background: var(--warning-bg);
        }}

        .heat-hot {{
            color: var(--error-text);
            background: var(--error-bg);
        }}

        .hn-comments {{
            font-size: 12px;
            color: var(--text-muted);
            text-decoration: none;
        }}

        .hn-comments:hover {{
            color: var(--brand-primary);
        }}

        /* ======================================== */
        /* 空状态                                     */
        /* ======================================== */

        .empty-state {{
            padding: 40px 20px;
            text-align: center;
        }}

        .empty-icon {{
            font-size: 32px;
            display: block;
            margin-bottom: 8px;
        }}

        .empty-state p {{
            font-size: 14px;
            color: var(--text-muted);
        }}

        /* ======================================== */
        /* 页脚                                       */
        /* ======================================== */

        .footer {{
            text-align: center;
            padding: 24px 16px;
            color: var(--text-disabled);
            font-size: 12px;
            line-height: 1.8;
        }}

        .footer-divider {{
            width: 40px;
            height: 2px;
            background: var(--border-default);
            border-radius: 1px;
            margin: 0 auto 12px;
        }}

        /* ======================================== */
        /* 移动端适配（微信内置浏览器）                 */
        /* ======================================== */

        @media (max-width: 480px) {{
            .container {{
                padding: 12px 10px 32px;
            }}

            .header {{
                padding: 20px 16px;
            }}

            .header-top {{
                flex-direction: column;
                align-items: flex-start;
                gap: 10px;
            }}

            .header-stats {{
                gap: 20px;
            }}

            .stat-value {{
                font-size: 20px;
            }}

            .news-item {{
                padding: 10px 14px;
            }}

            .hn-item {{
                padding: 10px 14px;
            }}

            .source-header, .hn-header {{
                padding: 12px 14px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- 头部区域 -->
        <div class="header">
            <div class="header-top">
                <div class="header-brand">
                    <div class="header-logo">📰</div>
                    <span class="header-title">科技日报</span>
                </div>
                <div class="header-date-badge">
                    📅 {date_str} 星期{weekday}
                </div>
            </div>
            <div class="header-divider"></div>
            <div class="header-stats">
                <div class="stat-item">
                    <span class="stat-value">{total_count}</span>
                    <span class="stat-label">资讯总数</span>
                </div>
                <div class="stat-item">
                    <span class="stat-value">{source_count}</span>
                    <span class="stat-label">数据来源</span>
                </div>
                <div class="stat-item">
                    <span class="stat-value">{time_str}</span>
                    <span class="stat-label">更新时间</span>
                </div>
            </div>
        </div>

        <!-- 国内科技动态 -->
        <div class="section-title">
            <span class="section-flag">🇨🇳</span>
            <span class="section-text">国内科技动态</span>
            <span class="section-line"></span>
        </div>

        {domestic_cards_html}

        <!-- 海外科技热榜 -->
        <div class="section-title">
            <span class="section-flag">🌍</span>
            <span class="section-text">Hacker News 热榜</span>
            <span class="section-line"></span>
        </div>

        <div class="hn-section">
            <div class="hn-header">
                <span class="source-icon">🔥</span>
                <span class="source-name">Hacker News</span>
                <span class="source-count">Top {len(hn_articles)}</span>
            </div>
            {hn_items_html}
        </div>

        <!-- 页脚 -->
        <div class="footer">
            <div class="footer-divider"></div>
            由 GitHub Actions 自动生成<br>
            {date_str} {time_str} · 北京时间
        </div>
    </div>
</body>
</html>"""

    return html


def _escape_html(text: str) -> str:
    """转义 HTML 特殊字符，防止 XSS"""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


# ========================================
# Server酱推送（发送摘要 + 页面链接）
# ========================================


def format_push_summary(
    rss_articles: list[dict],
    hn_articles: list[dict],
    page_url: str,
) -> tuple[str, str]:
    """
    生成 Server酱推送的标题和简短摘要

    推送内容保持简洁，重点放链接引导用户去看完整页面

    参数:
        rss_articles: RSS 源文章
        hn_articles: Hacker News 帖子
        page_url: GitHub Pages 上的完整页面地址

    返回:
        (标题, 正文Markdown)
    """
    now_beijing = datetime.now(BEIJING_TZ)
    date_str = now_beijing.strftime("%m月%d日")
    title = f"📰 科技日报 · {date_str}"

    lines = []

    # 如果有页面链接，放在最前面
    if page_url:
        lines.append(f"📖 [点击查看完整资讯页面]({page_url})")
        lines.append("")
        lines.append("---")
        lines.append("")

    total = len(rss_articles) + len(hn_articles)
    lines.append(f"今日共收录 **{total}** 条科技资讯")
    lines.append("")

    # 国内资讯摘要（每个源取前 3 条标题）
    sources_grouped: dict[str, list[dict]] = {}
    for article in rss_articles:
        src = article["source"]
        if src not in sources_grouped:
            sources_grouped[src] = []
        sources_grouped[src].append(article)

    if sources_grouped:
        lines.append("### 🇨🇳 国内动态")
        lines.append("")
        for source_name, articles in sources_grouped.items():
            emoji = articles[0].get("emoji", "📌")
            lines.append(f"**{emoji} {source_name}**（{len(articles)} 条）")
            for article in articles[:3]:
                lines.append(f"- [{article['title']}]({article['link']})")
            if len(articles) > 3:
                lines.append(f"- *...还有 {len(articles) - 3} 条*")
            lines.append("")

    # HN 摘要（取前 5 条）
    if hn_articles:
        lines.append("### 🌍 HN 热榜")
        lines.append("")
        for article in hn_articles[:5]:
            score = article.get("score", 0)
            lines.append(f"- [{article['title']}]({article['link']}) ⬆️{score}")
        if len(hn_articles) > 5:
            lines.append(f"- *...还有 {len(hn_articles) - 5} 条*")

    lines.append("")
    lines.append("---")
    if page_url:
        lines.append(f"*[查看完整页面]({page_url})*")

    content = "\n".join(lines)
    return title, content


def push_to_serverchan(title: str, content: str, sendkey: str) -> bool:
    """通过 Server酱 API 将消息推送到微信"""
    api_url = SERVERCHAN_API_URL.format(sendkey=sendkey)

    payload = {
        "title": title,
        "desp": content,
    }

    logger.info("正在通过 Server酱 推送消息...")

    try:
        resp = requests.post(api_url, data=payload, timeout=15)
        resp.raise_for_status()

        result = resp.json()

        if result.get("data", {}).get("pushid"):
            logger.info(f"推送成功！pushid: {result['data']['pushid']}")
            return True
        elif result.get("code") == 0:
            logger.info("推送成功！")
            return True
        else:
            logger.error(f"推送返回异常: {result}")
            return False

    except requests.exceptions.HTTPError as e:
        logger.error(f"推送请求失败 (HTTP {e.response.status_code}): {e}")
        return False
    except Exception as e:
        logger.error(f"推送过程中出错: {e}")
        return False


# ========================================
# 主流程
# ========================================


def main():
    """主入口：抓取 -> 生成 HTML -> 推送"""

    logger.info("=== 每日科技资讯抓取任务开始 ===")

    # 从环境变量读取配置
    sendkey = os.environ.get("SERVERCHAN_SENDKEY", "").strip()
    if not sendkey:
        logger.error(
            "未找到 SERVERCHAN_SENDKEY 环境变量！"
            "请在仓库的 Settings -> Secrets and variables -> Actions 中配置。"
        )
        sys.exit(1)

    # GitHub Pages 的地址，由 workflow 传入
    pages_url = os.environ.get("GITHUB_PAGES_URL", "").strip()

    # 计算截止时间
    now_utc = datetime.now(timezone.utc)
    cutoff_time = now_utc - timedelta(hours=HOURS_LOOKBACK)
    logger.info(f"抓取范围：{cutoff_time.isoformat()} 之后发布的内容")

    # 1. 抓取各 RSS 源
    rss_articles = fetch_all_rss_news(cutoff_time)

    # 2. 抓取 Hacker News 热榜
    hn_articles = fetch_hacker_news()

    total = len(rss_articles) + len(hn_articles)
    logger.info(f"共获取到 {total} 条资讯（RSS: {len(rss_articles)}, HN: {len(hn_articles)}）")

    if total == 0:
        logger.warning("本次未抓取到任何资讯，将推送空报告")

    # 3. 生成精美的 HTML 页面
    html_content = generate_html_page(rss_articles, hn_articles)

    # 写入到输出目录，供 GitHub Pages 部署
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / "index.html"
    output_file.write_text(html_content, encoding="utf-8")
    logger.info(f"HTML 页面已生成: {output_file}")

    # 同时保存一份带日期的归档
    now_beijing = datetime.now(BEIJING_TZ)
    archive_name = f"{now_beijing.strftime('%Y-%m-%d')}.html"
    archive_file = OUTPUT_DIR / "archive" / archive_name
    archive_file.parent.mkdir(parents=True, exist_ok=True)
    archive_file.write_text(html_content, encoding="utf-8")
    logger.info(f"归档页面已保存: {archive_file}")

    # 4. 推送摘要到微信
    push_title, push_content = format_push_summary(rss_articles, hn_articles, pages_url)
    success = push_to_serverchan(push_title, push_content, sendkey)

    if success:
        logger.info("=== 任务完成，推送成功 ===")
    else:
        logger.error("=== 任务完成，但推送失败 ===")
        sys.exit(1)


if __name__ == "__main__":
    main()
