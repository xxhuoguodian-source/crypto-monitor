"""
加密货币新闻监控机器人 - 脚本骨架
========================================

功能：定时抓取 RSS 信息源 -> 用 Claude API 判断相关性并摘要 -> 相关的推送到 Telegram

使用前准备：
1. pip install feedparser requests --break-system-packages
2. 申请 Telegram Bot：
   - 在 Telegram 里找 @BotFather，发送 /newbot，按提示创建，拿到 BOT_TOKEN
   - 和你的新 bot 随便发一条消息，然后访问：
     https://api.telegram.org/bot<你的TOKEN>/getUpdates
     在返回的 JSON 里找 "chat":{"id": xxxx} ，这个数字就是 CHAT_ID
3. 准备好 Gemini API Key（在 aistudio.google.com 免费申请，有免费额度）
4. 把下面的 RSS_FEEDS、KEYWORDS_HINT、环境变量填好
5. 本地测试跑通后，用 cron 或者云端定时任务（见文末说明）定时运行

本版本使用 Google Gemini API（有免费额度）替代 Anthropic API，
不需要额外安装 anthropic 库，直接用 requests 调用 Gemini 的 REST 接口即可。

设计要点：
- 用本地 JSON 文件记录已推送过的链接，避免重复通知（"存储去重"那一层）
- 相关性判断 + 摘要一起交给 Claude 做，一次调用完成，省 token 也省时间
- 每个信息源独立处理，互不影响；某个源抓取失败不会导致整个脚本崩溃
"""

import os
import json
import time
import hashlib
from pathlib import Path

import feedparser
import requests

# ============ 配置区：按需修改 ============

# 1. 你要监控的 RSS 信息源（先从几个开始，跑通了再加）
RSS_FEEDS = {
    "Chainlink 官方博客": "https://blog.chain.link/feed/",
    "The Block": "https://www.theblock.co/rss.xml",
    "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    # 没有 RSS 的站点（比如 DTCC 公告页）需要单独写爬虫函数，这里先留空
}

# 2. 你关心的主题提示（会写进 prompt，帮助 Claude 判断相关性）
#    根据你的投资框架自由调整，比如你的十一个代币、RWA 代币化主题等
TOPIC_HINT = """
用户是加密货币投资者，重点关注以下方向的新闻：
- RWA（真实世界资产）代币化基础设施
- 以下代币的重大进展、合作、上线、监管动态：SYRUP, CFG, LINK, POLYX, PLUME, CC, AAVE, MORPHO, EUL, PENDLE, HOOD
- DTCC / Canton Network 相关的机构级区块链结算基础设施进展
- 影响加密市场整体的重大宏观或监管事件
"""

# 3. 环境变量（不要把密钥直接写进代码，用环境变量传入更安全）
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Gemini 免费模型的接口地址（gemini-1.5-flash 免费额度较高，速度也快）
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-1.5-flash:generateContent"
)

# 4. 去重记录文件（记录已经处理过的文章链接）
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
    """遍历所有 RSS 源，取出还没处理过的新文章"""
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
                        "summary": entry.get("summary", "")[:800],  # 截断，控制 token 消耗
                        "link": entry.get("link", ""),
                    })
        except Exception as e:
            print(f"[警告] 抓取 {source_name} 失败: {e}")
    return new_articles


def judge_relevance_and_summarize(article: dict) -> dict | None:
    """
    调用 Gemini API 判断这篇文章是否相关，如果相关就顺便生成摘要。
    返回 None 表示不相关，跳过。
    """
    prompt = f"""{TOPIC_HINT}

请判断下面这篇文章是否与用户关注的方向相关。只返回 JSON，不要有其他文字：

文章标题：{article['title']}
文章摘要：{article['summary']}

返回格式（严格 JSON，不要加代码块标记）：
{{"relevant": true/false, "reason": "一句话说明为什么相关或不相关", "key_points": ["要点1", "要点2"]}}
如果不相关，key_points 留空数组即可。
"""
    try:
        resp = requests.post(
            f"{GEMINI_URL}?key={GEMINI_API_KEY}",
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        # 兼容模型偶尔加代码块标记的情况
        text = text.replace("```json", "").replace("```", "").strip()
        result = json.loads(text)
        return result if result.get("relevant") else None
    except Exception as e:
        print(f"[警告] LLM 判断失败: {e}")
        return None


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


def format_message(article: dict, judgement: dict) -> str:
    points = "\n".join(f"• {p}" for p in judgement.get("key_points", []))
    return (
        f"<b>[{article['source']}]</b> {article['title']}\n\n"
        f"{points}\n\n"
        f"相关性：{judgement.get('reason', '')}\n"
        f"链接：{article['link']}"
    )


def run_once():
    """跑一轮：抓取 -> 筛选 -> 推送 -> 更新去重记录"""
    seen = load_seen()
    new_articles = fetch_new_articles(seen)
    print(f"发现 {len(new_articles)} 篇新文章，开始逐一判断相关性...")

    for article in new_articles:
        judgement = judge_relevance_and_summarize(article)
        if judgement:
            message = format_message(article, judgement)
            send_telegram(message)
            print(f"[已推送] {article['title']}")
        else:
            print(f"[跳过] {article['title']}")

        seen.add(article["id"])
        time.sleep(1)  # 简单限速，避免过快触发 API 速率限制

    save_seen(seen)
    print("本轮处理完成。")


if __name__ == "__main__":
    if not all([GEMINI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
        raise SystemExit(
            "请先设置环境变量 GEMINI_API_KEY / TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID"
        )
    run_once()


# ============ 定时运行方式（任选一种） ============
#
# 方式一：本地 cron（Mac/Linux），每小时跑一次
#   crontab -e 里加一行：
#   0 * * * * cd /path/to/script && ANTHROPIC_API_KEY=xxx TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=xxx python3 crypto_news_monitor.py >> log.txt 2>&1
#
# 方式二：GitHub Actions（免费，不用自己开电脑）
#   在仓库里加 .github/workflows/monitor.yml，用 schedule 触发，
#   把三个密钥放进仓库的 Secrets 里，跑起来更省心，推荐这个方式。
#
# 方式三：云服务器 + systemd timer / crontab，适合已经有服务器的情况
