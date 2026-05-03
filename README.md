# AI Daily Curator (ai-curate)

基于 GitHub Actions + GitHub Models 的自动化中文 AI 资讯日报系统。

## 功能

- 每天自动抓取 AI 资讯：
  - Hacker News AI 相关高分帖子
  - arXiv 最新 AI/LLM 论文
  - GitHub 热门 AI 项目 Release 动态
  - GitHub 热门 AI 仓库 TOP5
- 使用 GitHub Models 将英文内容处理成中文
- 自动生成日报文件（Markdown + JSON）
- 每天北京时间 8:00 发送邮件到指定邮箱

## 文件结构

```
ai-daily-curator/
├── .github/workflows/ai-curate.yml   # GitHub Actions 定时任务
├── scripts/                           # Python 脚本
│   ├── fetch_hackernews.py            # Hacker News 数据抓取
│   ├── fetch_arxiv.py                 # arXiv 论文抓取
│   ├── fetch_github_releases.py       # GitHub Release 监控
│   ├── fetch_github_trending.py       # GitHub Trending 抓取
│   ├── generate_report.py             # 主入口：汇总 + AI 中文处理
│   └── send_email.py                  # 邮件发送
├── reports/daily/                     # 日报归档
│   ├── YYYY-MM-DD.md
│   └── YYYY-MM-DD.json
├── latest.md                          # 最新日报
└── requirements.txt                   # Python 依赖
```

## 部署步骤

1. Fork 或 Clone 本仓库
2. 在 GitHub 仓库 Settings > Secrets and variables > Actions 中添加：
   - `QQ_MAIL_AUTH_CODE`：QQ 邮箱 SMTP 授权码
3. 启用 GitHub Actions
4. 在 Actions 标签页手动触发 `ai-curate` workflow 进行测试

## 本地测试

```bash
pip install -r requirements.txt
export GITHUB_TOKEN="your_github_token"
python scripts/generate_report.py
```

## License

MIT
