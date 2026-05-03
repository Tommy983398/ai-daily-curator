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
DEFAULT_MODEL = "gpt-4o-mini"


def get_github_token() -> str:
    """获取 GitHub Token"""
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        token = os.environ.get("GH_TOKEN", "")
    if not token:
        raise ValueError("未设置 GITHUB_TOKEN 环境变量")
    return token


def call_github_model(prompt: str, token: str, model: str = DEFAULT_MODEL) -> str:
    """调用 GitHub Models API"""
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
                    "你是一个专业的 AI 领域编辑，擅长将英文科技内容翻译和整理为中文。"
                    "你的输出必须是纯中文，格式严格按照要求。不要输出任何 markdown 代码块标记。"
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 2000,
    }

    for attempt in range(3):
        try:
            resp = requests.post(MODELS_API, headers=headers, json=data, timeout=60)
            if resp.status_code == 429:
                wait = 2 ** attempt + 1
                print(f"  [API] 速率限制，等待 {wait}s 重试...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            result = resp.json()
            return result["choices"][0]["message"]["content"].strip()
        except requests.RequestException as e:
            print(f"  [API] 请求失败 (尝试 {attempt + 1}/3): {e}")
            if attempt < 2:
                time.sleep(3)
            continue
        except (KeyError, IndexError) as e:
            print(f"  [API] 响应解析失败: {e}")
            continue

    print("  [API] 所有尝试均失败，返回原文")
    return ""


def translate_hn_items(items: list[dict], token: str) -> list[dict]:
    """将 Hacker News 帖子翻译为中文"""
    if not items:
        return items

    print(f"[翻译] 正在处理 {len(items)} 条 Hacker News 帖子...")

    # 批量处理（每批最多 5 条，避免 token 过长）
    batch_size = 5
    translated = []

    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]

        item_list = ""
        for j, item in enumerate(batch, 1):
            item_list += f"{j}. 标题: {item['title']}\n   链接: {item['url']}\n   得分: {item['score']}\n\n"

        prompt = f"""请将以下 Hacker News AI 帖子列表翻译并整理为中文。
对每条帖子输出：
- 中文标题
- 中文摘要（一句话概括，50字以内）
- 重点（1条核心看点）

{item_list}
请用以下格式输出每一条（不要编号以外的多余文字）：
---
中文标题：xxx
中文摘要：xxx
重点：xxx
---"""

        result = call_github_model(prompt, token)

        if result:
            # 解析翻译结果
            blocks = result.split("---")
            for j, item in enumerate(batch):
                if j < len(blocks) - 1:
                    block = blocks[j + 1] if j + 1 < len(blocks) else blocks[j]
                    translated_item = item.copy()
                    for line in block.strip().split("\n"):
                        line = line.strip()
                        if line.startswith("中文标题：") or line.startswith("中文标题:"):
                            translated_item["cn_title"] = line.split("：")[-1].split(":")[-1].strip()
                        elif line.startswith("中文摘要：") or line.startswith("中文摘要:"):
                            translated_item["cn_summary"] = line.split("：")[-1].split(":")[-1].strip()
                        elif line.startswith("重点：") or line.startswith("重点:"):
                            translated_item["cn_highlight"] = line.split("：")[-1].split(":")[-1].strip()
                    translated.append(translated_item)
                else:
                    translated.append(item)
        else:
            translated.extend(batch)

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
        prompt = f"""请将以下 AI 论文信息翻译为中文：
标题: {paper['title']}
摘要: {paper['abstract']}

请输出：
中文标题：xxx
中文摘要：xxx（100-200字）
3条重点：
- xxx
- xxx
- xxx
为什么值得关注：xxx（50字以内）"""

        result = call_github_model(prompt, token)
        translated_paper = paper.copy()

        if result:
            for line in result.strip().split("\n"):
                line = line.strip()
                if line.startswith("中文标题：") or line.startswith("中文标题:"):
                    translated_paper["cn_title"] = line.split("：")[-1].split(":")[-1].strip()
                elif line.startswith("中文摘要：") or line.startswith("中文摘要:"):
                    translated_paper["cn_abstract"] = line.split("：")[-1].split(":")[-1].strip()
                elif line.startswith("为什么值得关注：") or line.startswith("为什么值得关注:"):
                    translated_paper["cn_why_care"] = line.split("：")[-1].split(":")[-1].strip()
                elif line.startswith("- ") and "cn_highlights" not in translated_paper:
                    translated_paper["cn_highlights"] = line[2:].strip()
                elif "cn_highlights" in translated_paper and line.startswith("- "):
                    translated_paper["cn_highlights"] += "\n" + line[2:].strip()

        translated.append(translated_paper)
        print(f"  [翻译] 论文 {i + 1}/{len(papers)}: {paper['title'][:50]}...")
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
        # Release 翻译只需翻译 body 摘要
        prompt = f"""请将以下 GitHub Release 信息翻译为中文摘要（100字以内）：

项目: {release['repo']}
版本: {release['tag_name']}
说明: {release['body']}

只输出中文摘要，不要其他内容。"""

        result = call_github_model(prompt, token)
        if result:
            translated_release["cn_summary"] = result.strip()
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
        prompt = f"""请将以下 GitHub 仓库信息翻译为中文：

仓库: {repo['repo']}
描述: {repo['description']}

请输出：
中文描述：xxx（100字以内）
为什么值得关注：xxx（50字以内）

只输出上述两行，不要其他内容。"""

        result = call_github_model(prompt, token)
        if result:
            for line in result.strip().split("\n"):
                line = line.strip()
                if line.startswith("中文描述：") or line.startswith("中文描述:"):
                    translated_repo["cn_description"] = line.split("：")[-1].split(":")[-1].strip()
                elif line.startswith("为什么值得关注：") or line.startswith("为什么值得关注:"):
                    translated_repo["cn_why_care"] = line.split("：")[-1].split(":")[-1].strip()
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
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        f"# AI 日报 - {date_str}",
        "",
        f"> 自动生成于 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC",
        "",
        "---",
        "",
    ]

    # Hacker News 板块
    if hn_items:
        lines.append("## Hacker News AI 热帖")
        lines.append("")
        for item in hn_items:
            cn_title = item.get("cn_title", item["title"])
            cn_summary = item.get("cn_summary", "")
            cn_highlight = item.get("cn_highlight", "")
            lines.append(f"### {cn_title}")
            if cn_summary:
                lines.append(f"> {cn_summary}")
            if cn_highlight:
                lines.append(f"- **重点**: {cn_highlight}")
            lines.append(f"- **得分**: {item['score']} | [原文链接]({item['url']})")
            lines.append("")
    else:
        lines.append("## Hacker News AI 热帖")
        lines.append("")
        lines.append("_今日暂无高分 AI 相关帖子_")
        lines.append("")

    lines.append("---")
    lines.append("")

    # arXiv 论文板块
    if arxiv_papers:
        lines.append("## arXiv AI 论文精选")
        lines.append("")
        for paper in arxiv_papers:
            cn_title = paper.get("cn_title", paper["title"])
            cn_abstract = paper.get("cn_abstract", "")
            cn_highlights = paper.get("cn_highlights", "")
            cn_why = paper.get("cn_why_care", "")
            authors = ", ".join(paper.get("authors", [])[:3])
            lines.append(f"### {cn_title}")
            lines.append(f"**作者**: {authors}")
            lines.append("")
            if cn_abstract:
                lines.append(cn_abstract)
                lines.append("")
            if cn_highlights:
                for h in cn_highlights.split("\n"):
                    h = h.strip()
                    if h.startswith("- "):
                        h = h[2:]
                    if h:
                        lines.append(f"- {h}")
                lines.append("")
            if cn_why:
                lines.append(f"**值得关注**: {cn_why}")
                lines.append("")
            lines.append(f"[论文链接]({paper['abs_url']}) | [PDF]({paper['pdf_url']})")
            lines.append("")
    else:
        lines.append("## arXiv AI 论文精选")
        lines.append("")
        lines.append("_今日暂无新论文_")
        lines.append("")

    lines.append("---")
    lines.append("")

    # GitHub Release 板块
    if releases:
        lines.append("## GitHub 项目 Release 动态")
        lines.append("")
        for rel in releases:
            cn_summary = rel.get("cn_summary", rel["body"][:200])
            lines.append(f"### {rel['repo']} - {rel['tag_name']}")
            if rel.get("name"):
                lines.append(f"**Release 名称**: {rel['name']}")
            if cn_summary:
                lines.append(f"> {cn_summary}")
            lines.append(f"- [查看详情]({rel['html_url']})")
            lines.append("")
    else:
        lines.append("## GitHub 项目 Release 动态")
        lines.append("")
        lines.append("_今日暂无新 Release_")
        lines.append("")

    lines.append("---")
    lines.append("")

    # GitHub Trending 板块
    if trending:
        lines.append("## GitHub AI 热门仓库 TOP5")
        lines.append("")
        for i, repo in enumerate(trending, 1):
            cn_desc = repo.get("cn_description", repo["description"])
            cn_why = repo.get("cn_why_care", "")
            lines.append(f"### {i}. {repo['repo']}")
            lines.append(f"- **今日新增**: ⭐ {repo['stars_today']} | 总计: {repo['total_stars']} | 语言: {repo['language']}")
            if cn_desc:
                lines.append(f"- **描述**: {cn_desc}")
            if cn_why:
                lines.append(f"- **值得关注**: {cn_why}")
            lines.append(f"- [查看仓库]({repo['url']})")
            lines.append("")
    else:
        lines.append("## GitHub AI 热门仓库 TOP5")
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
        "hackernews": hn_items,
        "arxiv": arxiv_papers,
        "github_releases": releases,
        "github_trending": trending,
    }


def main():
    print("=" * 60)
    print(f"AI Daily Curator - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")
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
    print("\n🤖 Step 2: GitHub Models 中文处理...")
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
    print(f"\n📊 日报统计:")
    print(f"  - Hacker News: {len(hn_items)} 条")
    print(f"  - arXiv 论文: {len(arxiv_papers)} 篇")
    print(f"  - GitHub Release: {len(releases)} 个")
    print(f"  - GitHub Trending: {len(trending)} 个")
    print("\n✨ 日报生成完成！")


if __name__ == "__main__":
    main()
