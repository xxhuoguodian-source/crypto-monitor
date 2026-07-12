name: Crypto News Monitor

on:
  # 定时触发：每 30 分钟跑一次（cron 用的是 UTC 时间，和你本地时区无关）
  schedule:
    - cron: "*/30 * * * *"
  # 保留手动触发按钮，方便你随时测试
  workflow_dispatch:

# 允许工作流把去重记录文件写回仓库
permissions:
  contents: write

jobs:
  run-monitor:
    runs-on: ubuntu-latest
    steps:
      - name: 拉取仓库代码
        uses: actions/checkout@v4

      - name: 安装 Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: 安装依赖包
        run: pip install feedparser anthropic requests

      - name: 运行监控脚本
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: python3 crypto_news_monitor.py

      - name: 保存去重记录（把 seen_articles.json 的更新提交回仓库）
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add seen_articles.json
          git diff --quiet --cached || git commit -m "更新已推送文章记录"
          git push
