"""
fetch_github_trending.py - 抓取 GitHub 热门 AI 仓库 TOP5

策略：
1. 抓取 GitHub Trending 页面（全语言 + Python + TypeScript 分别抓取）
2. 宽松的 AI 相关性判断
3. 如果 AI 严格匹配不够 5 个，从高分仓库中补充相关度较高的
"""

import requests
import re
import time
from bs4 import BeautifulSoup

TRENDING_URL = "https://github.com/trending"

# 核心关键词（命中即判定为 AI 相关）
CORE_AI_KW = [
    "ai", "artificial intelligence", "machine learning", "deep learning",
    "llm", "language model", "gpt", "chatgpt", "claude", "gemini",
    "transformer", "diffusion", "generative", "huggingface",
    "langchain", "openai", "anthropic", "mistral", "llama",
    "autonomous agent", "multi-agent", "ai agent", "agent framework",
    "computer vision", "nlp", "multimodal", "text-to-image",
    "stable diffusion", "dall-e", "midjourney", "copilot",
    "coding agent", "code generation", "code assistant",
    "reinforcement learning", "neural network", "embedding",
    "vector database", "rag", "retrieval augmented",
    "deepseek", "qwen", "ollama", "vllm", "tensorrt",
    "fine-tun", "finetune", "prompt engineering",
]

# 扩展关键词（降低优先级，用于补充不够时使用）
EXTENDED_AI_KW = [
    "automation", "workflow", "orchestration", "pipeline",
    "data science", "analytics", "visualization",
    "webhook", "api", "framework", "toolkit",
    "security", "privacy", "encryption",
    "robotics", "iot", "edge computing",
    "speech", "audio", "voice", "tts",
    "ocr", "document", "extraction",
    "search engine", "recommendation", "personalization",
    "model serving", "inference", "deployment",
    "distributed", "scalable", "parallel",
    "docker", "kubernetes", "devops",
    "websocket", "real-time", "streaming",
    "macos", "desktop", "automation tool",
]


def score_ai_relevance(text: str) -> tuple[int, bool]:
    """对文本进行 AI 相关性打分，返回 (分数, 是否核心AI)"""
    text_lower = text.lower()
    core_score = sum(1 for kw in CORE_AI_KW if kw in text_lower)
    ext_score = sum(1 for kw in EXTENDED_AI_KW if kw in text_lower)
    return (core_score * 3 + ext_score, core_score > 0)


def fetch_trending_page(url: str, headers: dict) -> list[dict]:
    """抓取单个 Trending 页面"""
    repos = []
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        articles = soup.select("article.Box-row")

        for article in articles:
            try:
                repo_tag = article.select_one("h2 a")
                if not repo_tag:
                    continue
                repo_name = repo_tag.get("href", "").strip("/")

                desc_tag = article.select_one("p")
                description = desc_tag.get_text(strip=True) if desc_tag else ""

                lang_tag = article.select_one("[itemprop='programmingLanguage']")
                language = lang_tag.get_text(strip=True) if lang_tag else ""

                stars_tag = article.select_one("a[href*='/stargazers']")
                total_stars = 0
                if stars_tag:
                    stars_text = stars_tag.get_text(strip=True).replace(",", "")
                    total_stars = int(stars_text) if stars_text.isdigit() else 0

                today_stars = 0
                for span in article.find_all("span"):
                    text = span.get_text(strip=True)
                    match = re.search(r"([\d,]+)\s*stars today", text, re.IGNORECASE)
                    if match:
                        today_stars = int(match.group(1).replace(",", ""))
                        break

                repos.append({
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

    except requests.RequestException as e:
        print(f"  [Trending] 请求失败: {e}")

    return repos


def fetch_trending(top_n: int = 5) -> list[dict]:
    """获取 GitHub Trending AI 仓库 TOP5"""
    print("[GitHub Trending] 正在抓取 Trending 页面...")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }

    all_repos = []
    seen = set()

    # 多维度抓取
    urls = [
        f"{TRENDING_URL}?since=daily",
        f"{TRENDING_URL}?since=daily&spoken_language_code=",
        f"{TRENDING_URL}/python?since=daily",
        f"{TRENDING_URL}/typescript?since=daily",
    ]

    for url in urls:
        page_repos = fetch_trending_page(url, headers)
        for repo in page_repos:
            if repo["repo"] not in seen:
                seen.add(repo["repo"])
                # 计算 AI 相关性得分
                check_text = f"{repo['repo']} {repo['description']}"
                score, is_core = score_ai_relevance(check_text)
                repo["_ai_score"] = score
                repo["_is_core_ai"] = is_core
                all_repos.append(repo)
        time.sleep(2)

    # 优先选核心 AI 仓库，按 stars_today 排序
    core_ai = [r for r in all_repos if r["_is_core_ai"]]
    core_ai.sort(key=lambda x: (x["_ai_score"], x["stars_today"]), reverse=True)

    # 如果核心 AI 不够 5 个，从扩展匹配中补充
    extended = [r for r in all_repos if not r["_is_core_ai"] and r["_ai_score"] >= 2]
    extended.sort(key=lambda x: (x["_ai_score"], x["stars_today"]), reverse=True)

    selected = (core_ai + extended)[:top_n]

    # 清理内部字段
    for r in selected:
        del r["_ai_score"]
        del r["_is_core_ai"]

    print(f"[GitHub Trending] 共 {len(all_repos)} 个仓库，AI 相关 {len(core_ai)} 个，精选 {len(selected)} 个")
    for r in selected:
        print(f"  {r['repo']} - {r['stars_today']} stars today")

    return selected


if __name__ == "__main__":
    repos = fetch_trending()
    import json
    print(json.dumps(repos, ensure_ascii=False, indent=2))
