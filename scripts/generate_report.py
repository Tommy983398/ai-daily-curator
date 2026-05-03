"""
generate_report.py - AI 日报主入口

1. 调用各抓取脚本获取原始数据
2. 使用 GitHub Models API 将内容翻译为中文
3. 生成日报 Markdown 和 JSON 文件
4. 更新 latest.md
"""

import os
import sys
import json
import time
import requests
from datetime import datetime, timezone, timedelta

# 添加脚本目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fetch_hackernews import fetch_top_stories
from fetch_arxiv import fetch_arxiv_papers
from fetch_github_releases import fetch_releases
from fetch_github_trending import fetch_trending

# GitHub Models API
MODELS_API = "https://models.inference.ai.azure.com/chat/completions"
# 使用 DeepSeek-V3-0324: 中文原生模型，free tier rate=high
DEFAULT_MODEL = "deepseek/deepseek-v3-0324"


def get_github_token() -> str:
    """获取 GitHub Token"""
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        token = os.environ.get("GH_TOKEN", "")
    if not token:
        raise ValueError("未设置 GITHUB_TOKEN 环境变量")
    return token


def call_github_model(prompt: str, token: str, model: str = DEFAULT_MODEL, max_tokens: int = 4000) -> str:
    """调用 GitHub Models API，带重试和详细日志"""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    data = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是一位资深 AI 领域中文科技编辑。你的任务是将英文科技内容翻译整理为高质量中文。"
                    "要求：\n"
                    "1. 全部输出必须为中文（人名、产品名、专有名词可保留英文）\n"
                    "2. 翻译要准确、自然、流畅，符合中文阅读习惯\n"
                    "3. 摘要要有深度，不要泛泛而谈\n"
                    "4. 严格按要求的格式输出，不要添加多余的开头/结尾文字"
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": max_tokens,
    }

    for attempt in range(3):
        try:
            resp = requests.post(MODELS_API, headers=headers, json=data, timeout=120)
            if resp.status_code == 429:
                wait = 2 ** (attempt + 1) + 2
                print(f"  [API] 速率限制，等待 {wait}s 重试 (attempt {attempt+1}/3)...")
                time.sleep(wait)
                continue
            if resp.status_code != 200:
                print(f"  [API] HTTP {resp.status_code}: {resp.text[:300]}")
                time.sleep(3)
                continue
            result = resp.json()
            content = result["choices"][0]["message"]["content"].strip()
            if content:
                return content
            print(f"  [API] 返回空内容 (attempt {attempt+1}/3)")
            time.sleep(2)
        except requests.RequestException as e:
            print(f"  [API] 请求失败 (尝试 {attempt+1}/3): {e}")
            time.sleep(3)
        except (KeyError, IndexError) as e:
            print(f"  [API] 响应解析失败: {e}")
            time.sleep(2)

    print("  [API] 所有尝试均失败")
    return ""


def translate_hn_items(items: list[dict], token: str) -> list[dict]:
    """将 Hacker News 帖子翻译为中文（精选 TOP 8，每条详细翻译）"""
    if not items:
        return items

    # 精选 TOP 8（按分数排序已在抓取时完成）
    items = items[:8]
    print(f"[翻译] 正在处理 {len(items)} 条 Hacker News 精选帖子...")

    translated = []

    for item in items:
        prompt = f"""请将以下 Hacker News AI 相关帖子翻译整理为中文。

标题: {item['title']}
链接: {item['url']}
得分: {item['score']}

请输出：
中文标题：xxx
摘要：用2-3句话详细介绍这个帖子的核心内容，让读者快速了解这是一件什么事（100-200字）
3条重点：
- xxx
- xxx
- xxx
为什么值得关注：用1-2句话说明这个帖子为什么值得 AI 从业者关注（50-100字）"""

        result = call_github_model(prompt, token)
        translated_item = item.copy()

        if result:
            cn_title = item["title"]  # 默认值
            cn_abstract = ""
            highlights = []
            cn_why = ""
            current_section = None

            for line in result.strip().split("\n"):
                line = line.strip()
                if not line:
                    continue
                if line.startswith("中文标题：") or line.startswith("中文标题:"):
                    cn_title = line.split("：", 1)[-1].split(":", 1)[-1].strip()
                elif line.startswith("摘要：") or line.startswith("摘要:"):
                    cn_abstract = line.split("：", 1)[-1].split(":", 1)[-1].strip()
                    current_section = "abstract"
                elif line.startswith("3条重点") or line.startswith("重点"):
                    current_section = "highlights"
                elif line.startswith("为什么值得关注：") or line.startswith("为什么值得关注:"):
                    cn_why = line.split("：", 1)[-1].split(":", 1)[-1].strip()
                    current_section = None
                elif line.startswith("- "):
                    if current_section == "highlights":
                        highlights.append(line[2:].strip())
                    elif current_section == "abstract":
                        cn_abstract += line[2:].strip()
                else:
                    if current_section == "abstract":
                        cn_abstract += line

            translated_item["cn_title"] = cn_title
            translated_item["cn_abstract"] = cn_abstract
            translated_item["cn_highlights"] = highlights
            translated_item["cn_why_care"] = cn_why

            print(f"  [OK] {cn_title[:40]}...")
        else:
            print(f"  [FAIL] {item['title'][:40]}... (使用原文)")

        translated.append(translated_item)
        time.sleep(1)

    print(f"[翻译] 完成 {len(translated)} 条")
    return translated


def translate_arxiv_papers(papers: list[dict], token: str) -> list[dict]:
    """将 arXiv 论文翻译为中文"""
    if not papers:
        return papers

    print(f"[翻译] 正在处理 {len(papers)} 篇 arXiv 论文...")

    translated = []
    for i, paper in enumerate(papers):
        prompt = f"""请将以下 AI 论文信息翻译整理为中文。

标题: {paper['title']}
作者: {', '.join(paper.get('authors', [])[:5])}
摘要: {paper['abstract']}

请输出：
中文标题：xxx
摘要：用3-5句话深入概括这篇论文的核心研究内容、方法和结论（150-300字）
3条重点：
- xxx
- xxx
- xxx
为什么值得关注：说明这项研究对 AI 领域的意义和应用前景（50-100字）"""

        result = call_github_model(prompt, token)
        translated_paper = paper.copy()

        if result:
            cn_title = paper["title"]
            cn_abstract = ""
            highlights = []
            cn_why = ""
            current_section = None

            for line in result.strip().split("\n"):
                line = line.strip()
                if not line:
                    continue
                if line.startswith("中文标题：") or line.startswith("中文标题:"):
                    cn_title = line.split("：", 1)[-1].split(":", 1)[-1].strip()
                elif line.startswith("摘要：") or line.startswith("摘要:"):
                    cn_abstract = line.split("：", 1)[-1].split(":", 1)[-1].strip()
                    current_section = "abstract"
                elif line.startswith("3条重点") or line.startswith("重点"):
                    current_section = "highlights"
                elif line.startswith("为什么值得关注：") or line.startswith("为什么值得关注:"):
                    cn_why = line.split("：", 1)[-1].split(":", 1)[-1].strip()
                    current_section = None
                elif line.startswith("- "):
                    if current_section == "highlights":
                        highlights.append(line[2:].strip())
                    elif current_section == "abstract":
                        cn_abstract += " " + line[2:].strip()
                else:
                    if current_section == "abstract":
                        cn_abstract += " " + line

            translated_paper["cn_title"] = cn_title
            translated_paper["cn_abstract"] = cn_abstract.strip()
            translated_paper["cn_highlights"] = highlights
            translated_paper["cn_why_care"] = cn_why

            print(f"  [OK] {cn_title[:40]}...")
        else:
            print(f"  [FAIL] {paper['title'][:40]}... (使用原文)")

        translated.append(translated_paper)
        time.sleep(1)

    print(f"[翻译] 完成 {len(translated)} 篇")
    return translated


def translate_releases(releases: list[dict], token: str) -> list[dict]:
    """翻译 GitHub Release 信息"""
    if not releases:
        return releases

    print(f"[翻译] 正在处理 {len(releases)} 个 Release...")

    translated = []
    for release in releases:
        translated_release = release.copy()
        prompt = f"""请将以下 GitHub 项目 Release 信息翻译整理为中文。

项目: {release['repo']}
版本: {release['tag_name']}
更新说明: {release['body'][:800]}

请输出：
中文标题：xxx（项目名-版本号 + 一句话概括核心更新）
摘要：详细介绍本次更新的核心内容、新功能和改进（100-200字）
为什么值得关注：说明这个更新对开发者的影响（50-100字）"""

        result = call_github_model(prompt, token)
        if result:
            cn_title = f"{release['repo']} - {release['tag_name']}"
            cn_abstract = ""
            cn_why = ""
            current_section = None

            for line in result.strip().split("\n"):
                line = line.strip()
                if not line:
                    continue
                if line.startswith("中文标题：") or line.startswith("中文标题:"):
                    cn_title = line.split("：", 1)[-1].split(":", 1)[-1].strip()
                elif line.startswith("摘要：") or line.startswith("摘要:"):
                    cn_abstract = line.split("：", 1)[-1].split(":", 1)[-1].strip()
                    current_section = "abstract"
                elif line.startswith("为什么值得关注：") or line.startswith("为什么值得关注:"):
                    cn_why = line.split("：", 1)[-1].split(":", 1)[-1].strip()
                    current_section = None
                elif not line.startswith("-") and current_section == "abstract":
                    cn_abstract += " " + line
                elif line.startswith("- ") and current_section == "abstract":
                    cn_abstract += " " + line[2:]

            translated_release["cn_title"] = cn_title
            translated_release["cn_abstract"] = cn_abstract.strip()
            translated_release["cn_why_care"] = cn_why
            print(f"  [OK] {cn_title[:40]}...")
        else:
            print(f"  [FAIL] {release['repo']} - {release['tag_name']} (使用原文)")

        translated.append(translated_release)
        time.sleep(1)

    print(f"[翻译] 完成 {len(translated)} 个 Release")
    return translated


def translate_trending(repos: list[dict], token: str) -> list[dict]:
    """翻译 GitHub Trending 信息"""
    if not repos:
        return repos

    print(f"[翻译] 正在处理 {len(repos)} 个 Trending 仓库...")

    translated = []
    for repo in repos:
        translated_repo = repo.copy()
        prompt = f"""请将以下 GitHub 热门仓库信息翻译整理为中文。

仓库: {repo['repo']}
描述: {repo['description']}
今日新增: {repo['stars_today']} stars
语言: {repo['language']}

请输出：
中文描述：详细介绍这个项目的功能和用途（100-200字）
为什么值得关注：说明这个项目为什么突然火爆、解决了什么问题、适合谁使用（50-100字）"""

        result = call_github_model(prompt, token)
        if result:
            cn_desc = repo["description"]
            cn_why = ""
            current_section = None

            for line in result.strip().split("\n"):
                line = line.strip()
                if not line:
                    continue
                if line.startswith("中文描述：") or line.startswith("中文描述:"):
                    cn_desc = line.split("：", 1)[-1].split(":", 1)[-1].strip()
                    current_section = "desc"
                elif line.startswith("为什么值得关注：") or line.startswith("为什么值得关注:"):
                    cn_why = line.split("：", 1)[-1].split(":", 1)[-1].strip()
                    current_section = None
                elif current_section == "desc" and not line.startswith("-"):
                    cn_desc += " " + line

            translated_repo["cn_description"] = cn_desc.strip()
            translated_repo["cn_why_care"] = cn_why
            print(f"  [OK] {repo['repo']}")
        else:
            print(f"  [FAIL] {repo['repo']} (使用原文)")

        translated.append(translated_repo)
        time.sleep(1)

    print(f"[翻译] 完成 {len(translated)} 个仓库")
    return translated


def build_markdown_report(
    hn_items: list[dict],
    arxiv_papers: list[dict],
    releases: list[dict],
    trending: list[dict],
    date_str: str,
) -> str:
    """构建 Markdown 格式的日报"""
    lines = [
        f"# AI 日报 - {date_str}",
        "",
        f"> 自动生成于 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC | "
        f" Powered by GitHub Actions + GitHub Models",
        "",
        "---",
        "",
    ]

    # Hacker News 板块
    if hn_items:
        lines.append("## 🔥 Hacker News AI 热帖精选")
        lines.append("")
        for item in hn_items:
            cn_title = item.get("cn_title", item["title"])
            lines.append(f"### {cn_title}")
            cn_abstract = item.get("cn_abstract", "")
            if cn_abstract:
                lines.append(f"> {cn_abstract}")
            highlights = item.get("cn_highlights", [])
            if highlights:
                lines.append("**核心看点：**")
                for h in highlights:
                    if h:
                        lines.append(f"- {h}")
            cn_why = item.get("cn_why_care", "")
            if cn_why:
                lines.append(f"**为什么值得关注：** {cn_why}")
            lines.append(f"")
            lines.append(f"- 🔗 [查看原文]({item['url']}) | 👍 得分: {item['score']}")
            lines.append("")
    else:
        lines.append("## 🔥 Hacker News AI 热帖精选")
        lines.append("")
        lines.append("_今日暂无高分 AI 相关帖子_")
        lines.append("")

    lines.append("---")
    lines.append("")

    # arXiv 论文板块
    if arxiv_papers:
        lines.append("## 📄 arXiv AI 论文精选")
        lines.append("")
        for paper in arxiv_papers:
            cn_title = paper.get("cn_title", paper["title"])
            lines.append(f"### {cn_title}")
            authors = ", ".join(paper.get("authors", [])[:4])
            lines.append(f"**作者：** {authors}")
            lines.append(f"**发布日期：** {paper.get('published', 'N/A')}")
            lines.append("")
            cn_abstract = paper.get("cn_abstract", "")
            if cn_abstract:
                lines.append(cn_abstract)
                lines.append("")
            highlights = paper.get("cn_highlights", [])
            if highlights:
                lines.append("**核心贡献：**")
                for h in highlights:
                    if h:
                        lines.append(f"- {h}")
                lines.append("")
            cn_why = paper.get("cn_why_care", "")
            if cn_why:
                lines.append(f"**为什么值得关注：** {cn_why}")
                lines.append("")
            lines.append(f"- 📄 [论文链接]({paper['abs_url']}) | 📥 [PDF]({paper['pdf_url']})")
            lines.append("")
    else:
        lines.append("## 📄 arXiv AI 论文精选")
        lines.append("")
        lines.append("_今日暂无新论文_")
        lines.append("")

    lines.append("---")
    lines.append("")

    # GitHub Release 板块
    if releases:
        lines.append("## 🚀 GitHub 项目 Release 动态")
        lines.append("")
        for rel in releases:
            cn_title = rel.get("cn_title", f"{rel['repo']} - {rel['tag_name']}")
            lines.append(f"### {cn_title}")
            cn_abstract = rel.get("cn_abstract", "")
            if cn_abstract:
                lines.append(f"> {cn_abstract}")
            cn_why = rel.get("cn_why_care", "")
            if cn_why:
                lines.append(f"**为什么值得关注：** {cn_why}")
            lines.append(f"- 🔗 [查看 Release]({rel['html_url']})")
            lines.append("")
    else:
        lines.append("## 🚀 GitHub 项目 Release 动态")
        lines.append("")
        lines.append("_今日暂无新 Release_")
        lines.append("")

    lines.append("---")
    lines.append("")

    # GitHub Trending 板块
    if trending:
        lines.append("## ⭐ GitHub AI 热门仓库 TOP5")
        lines.append("")
        for i, repo in enumerate(trending, 1):
            lines.append(f"### {i}. {repo['repo']}")
            lines.append(
                f"- **今日新增：** ⭐ {repo['stars_today']} | **总计：** {repo['total_stars']} | **语言：** {repo['language']}"
            )
            cn_desc = repo.get("cn_description", repo["description"])
            if cn_desc:
                lines.append(f"- **项目介绍：** {cn_desc}")
            cn_why = repo.get("cn_why_care", "")
            if cn_why:
                lines.append(f"- **为什么值得关注：** {cn_why}")
            lines.append(f"- 🔗 [查看仓库]({repo['url']})")
            lines.append("")
    else:
        lines.append("## ⭐ GitHub AI 热门仓库 TOP5")
        lines.append("")
        lines.append("_今日暂无数据_")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("_本日报由 AI Daily Curator 自动生成 | Powered by GitHub Actions + GitHub Models_")

    return "\n".join(lines)


def build_json_report(
    hn_items: list[dict],
    arxiv_papers: list[dict],
    releases: list[dict],
    trending: list[dict],
    date_str: str,
) -> dict:
    """构建 JSON 格式的日报"""
    return {
        "date": date_str,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": DEFAULT_MODEL,
        "hackernews": hn_items,
        "arxiv": arxiv_papers,
        "github_releases": releases,
        "github_trending": trending,
    }


def main():
    print("=" * 60)
    print(f"AI Daily Curator - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"模型: {DEFAULT_MODEL}")
    print("=" * 60)

    token = get_github_token()
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Step 1: 抓取数据
    print("\n📡 Step 1: 抓取原始数据...")
    hn_items = fetch_top_stories()
    arxiv_papers = fetch_arxiv_papers()
    releases = fetch_releases()
    trending = fetch_trending()

    # Step 2: AI 翻译
    print(f"\n🤖 Step 2: GitHub Models 中文处理 (model={DEFAULT_MODEL})...")
    hn_items = translate_hn_items(hn_items, token)
    arxiv_papers = translate_arxiv_papers(arxiv_papers, token)
    releases = translate_releases(releases, token)
    trending = translate_trending(trending, token)

    # Step 3: 生成报告文件
    print("\n📝 Step 3: 生成日报文件...")

    # 确保 reports/daily 目录存在
    os.makedirs("reports/daily", exist_ok=True)

    # 生成 Markdown
    md_content = build_markdown_report(hn_items, arxiv_papers, releases, trending, date_str)
    md_path = f"reports/daily/{date_str}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"  ✅ Markdown: {md_path}")

    # 生成 JSON
    json_data = build_json_report(hn_items, arxiv_papers, releases, trending, date_str)
    json_path = f"reports/daily/{date_str}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)
    print(f"  ✅ JSON: {json_path}")

    # 更新 latest.md
    with open("latest.md", "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"  ✅ latest.md 已更新")

    # 统计
    hn_ok = sum(1 for x in hn_items if x.get("cn_title") and x["cn_title"] != x.get("title"))
    arxiv_ok = sum(1 for x in arxiv_papers if x.get("cn_title") and x["cn_title"] != x.get("title"))
    print(f"\n📊 日报统计:")
    print(f"  - Hacker News: {len(hn_items)} 条 (翻译成功 {hn_ok})")
    print(f"  - arXiv 论文: {len(arxiv_papers)} 篇 (翻译成功 {arxiv_ok})")
    print(f"  - GitHub Release: {len(releases)} 个")
    print(f"  - GitHub Trending: {len(trending)} 个")
    print("\n✨ 日报生成完成！")


if __name__ == "__main__":
    main()
