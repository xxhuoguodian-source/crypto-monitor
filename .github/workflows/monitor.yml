"""
加密货币新闻监控机器人 - 简化版（无 AI 判断，全部推送）
========================================

功能：定时抓取 RSS 信息源 -> 把所有新文章直接推送到 Telegram，由你自己判断是否相关

使用前准备：
1. pip install feedparser requests --break-system-packages
2. 申请 Telegram Bot：
   - 在 Telegram 里找 @BotFather，发送 /newbot，按提示创建，拿到 BOT_TOKEN
   - 和你的新 bot 随便发一条消息，然后访问：
     https://api.telegram.org/bot<你的TOKEN>/getUpdates
     在返回的 JSON 里找 "chat":{"id": xxxx} ，这个数字就是 CHAT_ID
3. 把下面的 RSS_FEEDS 按需增减
4. 用 GitHub Actions 定时运行（见 monitor.yml）

设计要点：
- 用本地 JSON 文件记录已推送过的链接，避免重复通知
- 不依赖任何 AI/LLM API，只需要 Telegram 一个密钥，最简单、最不容易出错
- 每个信息源独立处理，互不影响；某个源抓取失败不会导致整个脚本崩溃
"""

import os
import json
import hashlib
from pathlib import Path

import feedparser
import requests

# ============ 配置区：按需修改 ============

# 你要监控的 RSS 信息源（可以随时增减）
RSS_FEEDS = {
    "Chainlink 官方博客": "https://blog.chain.link/feed/",
    "The Block": "https://www.theblock.co/rss.xml",
    "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    # 没有 RSS 的站点（比如 DTCC 公告页）需要单独写爬虫函数，这里先留空
}

# 环境变量（密钥不写死在代码里，从 GitHub Secrets 传入）
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# 去重记录文件（记录已经推送过的文章链接）
SEEN_FILE = Path(__file__).parent / "seen_articles.json"

# ============ 核心逻辑 ============


def load_seen() -> set:
    """读取已推送过的文章标识"""
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return set()


def save_seen(seen: set):
    SEEN_FILE.write_text(json.dumps(list(seen)))


def article_id(entry) -> str:
    """用链接生成唯一标识，避免重复推送"""
    link = entry.get("link", entry.get("title", ""))
    return hashlib.md5(link.encode()).hexdigest()


def fetch_new_articles(seen: set) -> list:
    """遍历所有 RSS 源，取出还没推送过的新文章"""
    new_articles = []
    for source_name, feed_url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:10]:  # 每个源只看最新 10 条，避免历史存量刷屏
                aid = article_id(entry)
                if aid not in seen:
                    new_articles.append({
                        "id": aid,
                        "source": source_name,
                        "title": entry.get("title", ""),
                        "link": entry.get("link", ""),
                    })
        except Exception as e:
            print(f"[警告] 抓取 {source_name} 失败: {e}")
    return new_articles


def send_telegram(text: str):
    """推送消息到 Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    resp = requests.post(url, data={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    })
    if resp.status_code != 200:
        print(f"[警告] Telegram 推送失败: {resp.text}")


def format_message(article: dict) -> str:
    return (
        f"<b>[{article['source']}]</b> {article['title']}\n\n"
        f"链接：{article['link']}"
    )


def run_once():
    """跑一轮：抓取 -> 全部推送 -> 更新去重记录"""
    seen = load_seen()
    new_articles = fetch_new_articles(seen)
    print(f"发现 {len(new_articles)} 篇新文章，开始推送...")

    for article in new_articles:
        message = format_message(article)
        send_telegram(message)
        print(f"[已推送] {article['title']}")
        seen.add(article["id"])

    save_seen(seen)
    print("本轮处理完成。")


if __name__ == "__main__":
    if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
        raise SystemExit(
            "请先设置环境变量 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID"
        )
    run_once()


# ============ 定时运行方式 ============
#
# 推荐用 GitHub Actions（免费，不用自己开电脑），
# 在仓库里加 .github/workflows/monitor.yml，用 schedule 触发，
# 把两个密钥（TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID）放进仓库 Secrets 里即可。
