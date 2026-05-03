"""
fetch_github_trending.py - 抓取 GitHub 热门 AI 仓库 TOP5

抓取 GitHub Trending 页面，过滤 AI 相关仓库，取 TOP5。
"""

import requests
import re
import time
from datetime import datetime, timezone
from bs4 import BeautifulSoup

TRENDING_URL = "https://github.com/trending"

AI_TOPIC_KEYWORDS = [
    "ai", "artificial-intelligence", "machine-learning", "deep-learning",
    "llm", "language-model", "gpt", "chatgpt", "transformer",
    "generative-ai", "diffusion-model", "stable-diffusion",
    "openai", "anthropic", "huggingface", "langchain",
    "computer-vision", "nlp", "natural-language-processing",
    "reinforcement-learning", "neural-network", "multimodal",
    "ai-agent", "autonomous-agent", "robotics",
    "mistral", "llama", "falcon", "qwen",
]


def is_ai_repo(description: str, topics: list[str], repo_name: str) -> bool:
    """检查仓库是否 AI 相关"""
    desc_lower = (description or "").lower()
    name_lower = repo_name.lower()
    topics_lower = [t.lower() for t in topics]

    # 检查 topics
    for topic in topics_lower:
        for kw in AI_TOPIC_KEYWORDS:
            if kw in topic:
                return True

    # 检查描述
    for kw in AI_TOPIC_KEYWORDS:
        if kw in desc_lower or kw in name_lower:
            return True

    return False


def fetch_trending() -> list[dict]:
    """获取 GitHub Trending AI 仓库 TOP5"""
    print("[GitHub Trending] 正在抓取 Trending 页面...")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }

    all_repos = []

    # 尝试多个语言分类
    languages = ["", "python", "typescript"]
    for lang in languages:
        url = f"{TRENDING_URL}?since=daily"
        if lang:
            url += f"&spoken_language_code={lang}"

        try:
            resp = requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")
            articles = soup.select("article.Box-row")

            for article in articles:
                try:
                    # 仓库名
                    repo_tag = article.select_one("h2 a")
                    if not repo_tag:
                        continue
                    repo_name = repo_tag.get("href", "").strip("/")

                    # 描述
                    desc_tag = article.select_one("p")
                    description = desc_tag.get_text(strip=True) if desc_tag else ""

                    # 语言
                    lang_tag = article.select_one("[itemprop='programmingLanguage']")
                    language = lang_tag.get_text(strip=True) if lang_tag else ""

                    # 总 stars
                    stars_tag = article.select_one("a[href*='/stargazers']")
                    total_stars = 0
                    if stars_tag:
                        stars_text = stars_tag.get_text(strip=True).replace(",", "")
                        total_stars = int(stars_text) if stars_text else 0

                    # 今日 stars（增量的 span.star）
                    today_stars = 0
                    for span in article.find_all("span"):
                        text = span.get_text(strip=True)
                        match = re.search(r"([\d,]+)\s*stars today", text, re.IGNORECASE)
                        if match:
                            today_stars = int(match.group(1).replace(",", ""))
                            break
                        # 也匹配纯数字格式
                        match2 = re.search(r"([\d,]+)\s*\*", text)
                        if match2:
                            today_stars = int(match2.group(1).replace(",", ""))

                    # 避免重复
                    if any(r["repo"] == repo_name for r in all_repos):
                        continue

                    all_repos.append({
                        "repo": repo_name,
                        "description": description,
                        "total_stars": total_stars,
                        "stars_today": today_stars,
                        "language": language,
                        "url": f"https://github.com/{repo_name}",
                        "source": "github_trending",
                    })

                except Exception as e:
                    print(f"  [Trending] 解析条目失败: {e}")
                    continue

            time.sleep(2)

        except requests.RequestException as e:
            print(f"  [Trending] 请求失败: {e}")
            continue

    # 过滤 AI 相关并排序
    ai_repos = []
    for repo in all_repos:
        if is_ai_repo(repo["description"], [], repo["repo"]):
            ai_repos.append(repo)

    ai_repos.sort(key=lambda x: x["stars_today"], reverse=True)
    top5 = ai_repos[:5]

    print(f"[GitHub Trending] 共 {len(all_repos)} 个仓库，AI 相关 {len(ai_repos)} 个，取 TOP5")
    for r in top5:
        print(f"  {r['repo']} - {r['stars_today']} stars today")

    return top5


if __name__ == "__main__":
    repos = fetch_trending()
    import json
    print(json.dumps(repos, ensure_ascii=False, indent=2))
