# -*- coding: utf-8 -*-
"""
每日科技资讯抓取与推送脚本

功能说明：
  1. 从多个 RSS 订阅源抓取过去 24 小时内发布的科技资讯
  2. 同时从 Hacker News 获取热门帖子作为海外科技动态补充
  3. 将整理好的资讯通过 Server酱 API 推送到微信

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

# RSS 订阅源列表
# 每个源包含名称和对应的 RSS 地址
RSS_SOURCES = [
    {
        "name": "36氪 · 快讯",
        "url": "https://36kr.com/feed",
        "emoji": "📊",
    },
    {
        "name": "IT之家",
        "url": "https://www.ithome.com/rss/",
        "emoji": "💻",
    },
    {
        "name": "少数派",
        "url": "https://sspai.com/feed",
        "emoji": "📱",
    },
    {
        "name": "Solidot",
        "url": "https://www.solidot.org/index.rss",
        "emoji": "🔬",
    },
]

# Hacker News 官方 API
# 文档：https://github.com/HackerNews/API
HN_TOP_STORIES_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{item_id}.json"
HN_ITEM_WEB_URL = "https://news.ycombinator.com/item?id={item_id}"
HN_TOP_N = 15  # 取热榜前 15 条


# ========================================
# RSS 源抓取逻辑
# ========================================


def fetch_rss_news(source: dict, cutoff_time: datetime) -> list[dict]:
    """
    从单个 RSS 源抓取指定时间范围内的文章

    参数:
        source: 包含 name, url, emoji 的字典
        cutoff_time: 截止时间，只返回这个时间之后发布的文章

    返回:
        文章列表，每篇文章包含 title, link, published, source 字段
    """
    articles = []
    feed_url = source["url"]
    source_name = source["name"]

    logger.info(f"正在抓取 RSS 源: {source_name} ({feed_url})")

    try:
        # feedparser 会自动处理各种 RSS/Atom 格式
        feed = feedparser.parse(feed_url)

        # 检查是否解析成功
        if feed.bozo and not feed.entries:
            logger.warning(f"解析 {source_name} 的 RSS 失败: {feed.bozo_exception}")
            return articles

        for entry in feed.entries:
            # 拿到文章标题和链接
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()

            if not title or not link:
                continue

            # 解析发布时间
            # feedparser 会把各种时间格式统一转成 time_struct
            published_parsed = entry.get("published_parsed") or entry.get("updated_parsed")

            if published_parsed:
                # time_struct 转 datetime（UTC）
                pub_time = datetime(*published_parsed[:6], tzinfo=timezone.utc)

                # 只保留截止时间之后的文章
                if pub_time < cutoff_time:
                    continue
            else:
                # 如果没有时间信息，默认保留（宁可多推不遗漏）
                pub_time = None

            articles.append({
                "title": title,
                "link": link,
                "published": pub_time,
                "source": source_name,
                "emoji": source["emoji"],
            })

        logger.info(f"从 {source_name} 获取到 {len(articles)} 篇文章")

    except Exception as e:
        logger.error(f"抓取 {source_name} 时出错: {e}")

    return articles


def fetch_all_rss_news(cutoff_time: datetime) -> list[dict]:
    """
    遍历所有 RSS 源，汇总抓取结果

    参数:
        cutoff_time: 截止时间

    返回:
        所有源的文章汇总列表
    """
    all_articles = []

    for source in RSS_SOURCES:
        articles = fetch_rss_news(source, cutoff_time)
        all_articles.extend(articles)

        # 请求间隔，别太频繁
        time.sleep(1)

    return all_articles


# ========================================
# Hacker News 抓取逻辑
# ========================================


def fetch_hacker_news(top_n: int = HN_TOP_N) -> list[dict]:
    """
    从 Hacker News 官方 API 获取当前热榜的前 N 条

    Hacker News 的热榜是实时排名的，不按时间过滤，
    所以这里直接取排名靠前的帖子就行。

    参数:
        top_n: 取前几条

    返回:
        帖子列表
    """
    articles = []
    logger.info(f"正在抓取 Hacker News 热榜 Top {top_n}")

    try:
        # 先拿到热榜的帖子 ID 列表
        resp = requests.get(HN_TOP_STORIES_URL, timeout=15)
        resp.raise_for_status()
        story_ids = resp.json()[:top_n]

        for story_id in story_ids:
            try:
                # 逐条获取帖子详情
                item_resp = requests.get(
                    HN_ITEM_URL.format(item_id=story_id),
                    timeout=10,
                )
                item_resp.raise_for_status()
                item = item_resp.json()

                if not item or item.get("type") != "story":
                    continue

                title = item.get("title", "").strip()
                # 有些帖子是 Ask HN / Show HN 之类的，没有外链
                link = item.get("url") or HN_ITEM_WEB_URL.format(item_id=story_id)
                score = item.get("score", 0)

                articles.append({
                    "title": title,
                    "link": link,
                    "score": score,
                    "source": "Hacker News",
                    "emoji": "🔥",
                })

            except Exception as e:
                logger.warning(f"获取 HN 帖子 {story_id} 详情失败: {e}")
                continue

            # 控制请求频率
            time.sleep(0.3)

        logger.info(f"从 Hacker News 获取到 {len(articles)} 条帖子")

    except Exception as e:
        logger.error(f"抓取 Hacker News 热榜失败: {e}")

    return articles


# ========================================
# 消息格式化
# ========================================


def format_news_markdown(rss_articles: list[dict], hn_articles: list[dict]) -> str:
    """
    把抓取到的资讯整理成 Markdown 格式，方便在微信里阅读

    Server酱 的消息内容字段 (desp) 支持 Markdown，
    这样推送到微信后排版会好看些。

    参数:
        rss_articles: RSS 源抓取的文章
        hn_articles: Hacker News 的帖子

    返回:
        格式化后的 Markdown 字符串
    """
    now_beijing = datetime.now(BEIJING_TZ)
    date_str = now_beijing.strftime("%Y年%m月%d日")

    lines = []
    lines.append(f"## 📰 每日科技资讯 · {date_str}")
    lines.append("")
    lines.append(f"> 数据抓取时间：{now_beijing.strftime('%H:%M')}（北京时间）")
    lines.append("")

    # ---- 国内科技资讯部分 ----
    if rss_articles:
        # 按来源分组
        sources_grouped: dict[str, list[dict]] = {}
        for article in rss_articles:
            src = article["source"]
            if src not in sources_grouped:
                sources_grouped[src] = []
            sources_grouped[src].append(article)

        lines.append("---")
        lines.append("")
        lines.append("### 🇨🇳 国内科技动态")
        lines.append("")

        for source_name, articles in sources_grouped.items():
            # 找到这个源对应的 emoji
            emoji = articles[0].get("emoji", "📌")
            lines.append(f"#### {emoji} {source_name}")
            lines.append("")

            # 每个源最多展示 10 条，避免消息过长
            for i, article in enumerate(articles[:10]):
                title = article["title"]
                link = article["link"]
                lines.append(f"{i + 1}. [{title}]({link})")

            if len(articles) > 10:
                lines.append(f"\n> 还有 {len(articles) - 10} 条未展示")

            lines.append("")
    else:
        lines.append("### 🇨🇳 国内科技动态")
        lines.append("")
        lines.append("暂无新资讯，各 RSS 源可能未更新。")
        lines.append("")

    # ---- 海外科技资讯部分（Hacker News） ----
    lines.append("---")
    lines.append("")
    lines.append("### 🌍 海外科技热榜（Hacker News）")
    lines.append("")

    if hn_articles:
        for i, article in enumerate(hn_articles):
            title = article["title"]
            link = article["link"]
            score = article.get("score", 0)
            lines.append(f"{i + 1}. [{title}]({link})  ⬆️ {score}")
    else:
        lines.append("Hacker News 数据获取失败，请稍后手动查看。")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"*由 GitHub Actions 自动抓取并推送 · {date_str}*")

    return "\n".join(lines)


# ========================================
# Server酱 推送
# ========================================


def push_to_serverchan(title: str, content: str, sendkey: str) -> bool:
    """
    通过 Server酱 API 将消息推送到微信

    API 文档：https://sct.ftqq.com/

    参数:
        title:   消息标题（会显示在微信通知上）
        content: 消息正文（支持 Markdown）
        sendkey: 你在 sct.ftqq.com 上获取的 SendKey

    返回:
        是否推送成功
    """
    api_url = SERVERCHAN_API_URL.format(sendkey=sendkey)

    # Server酱的接口很简洁，只需要 title 和 desp 两个参数
    payload = {
        "title": title,
        "desp": content,
    }

    logger.info("正在通过 Server酱 推送消息...")

    try:
        resp = requests.post(api_url, data=payload, timeout=15)
        resp.raise_for_status()

        result = resp.json()

        # Server酱返回的 JSON 里，data.pushid 存在就说明推送成功
        if result.get("data", {}).get("pushid"):
            logger.info(f"推送成功！pushid: {result['data']['pushid']}")
            return True
        elif result.get("code") == 0:
            # 有些版本返回 code=0 表示成功
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
    """主入口：抓取 -> 格式化 -> 推送"""

    logger.info("=== 每日科技资讯抓取任务开始 ===")

    # 从环境变量读取 Server酱 SendKey
    sendkey = os.environ.get("SERVERCHAN_SENDKEY", "").strip()
    if not sendkey:
        logger.error(
            "未找到 SERVERCHAN_SENDKEY 环境变量！"
            "请在仓库的 Settings -> Secrets and variables -> Actions 中配置。"
        )
        sys.exit(1)

    # 计算截止时间：当前 UTC 时间往前推 24 小时
    now_utc = datetime.now(timezone.utc)
    cutoff_time = now_utc - timedelta(hours=HOURS_LOOKBACK)
    logger.info(f"抓取范围：{cutoff_time.isoformat()} 之后发布的内容")

    # 1. 抓取各 RSS 源
    rss_articles = fetch_all_rss_news(cutoff_time)

    # 2. 抓取 Hacker News 热榜
    hn_articles = fetch_hacker_news()

    # 统计一下
    total = len(rss_articles) + len(hn_articles)
    logger.info(f"共获取到 {total} 条资讯（RSS: {len(rss_articles)}, HN: {len(hn_articles)}）")

    # 就算没抓到任何内容也推送一条，至少让你知道脚本跑了
    if total == 0:
        logger.warning("本次未抓取到任何资讯，将推送空报告")

    # 3. 格式化消息
    content = format_news_markdown(rss_articles, hn_articles)

    # 生成标题（带日期，微信通知一眼就能看到）
    now_beijing = datetime.now(BEIJING_TZ)
    title = f"📰 科技日报 · {now_beijing.strftime('%m月%d日')}"

    # 4. 推送到微信
    success = push_to_serverchan(title, content, sendkey)

    if success:
        logger.info("=== 任务完成，推送成功 ===")
    else:
        logger.error("=== 任务完成，但推送失败 ===")
        sys.exit(1)


if __name__ == "__main__":
    main()
