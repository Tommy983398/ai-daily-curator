"""
fetch_arxiv.py - 抓取 arXiv 最新 AI/LLM 论文

使用 arXiv Atom API 搜索 cs.AI, cs.LG, cs.CL 分类的最新论文。
"""

import requests
import re
import time
from datetime import datetime, timezone, timedelta
import xml.etree.ElementTree as ET

ARXIV_API = "http://export.arxiv.org/api/query"

# 搜索参数：AI / 机器学习 / 自然语言处理
SEARCH_QUERY = "cat:cs.AI OR cat:cs.LG OR cat:cs.CL"
MAX_RESULTS = 30

# 额外的 AI/LLM 关键词过滤（arXiv 标题中出现的）
ARXIV_AI_KEYWORDS = [
    "large language model", "llm", "gpt", "chatgpt", "claude",
    "generative", "diffusion", "transformer", "bert", "attention",
    "prompt", "fine-tun", "reinforcement learning from human feedback",
    "rlhf", "alignment", "agent", "multi-agent", "reasoning",
    "instruction following", "in-context learning", "chain-of-thought",
    "retrieval augmented", "rag", "embedding", "language model",
    "vision-language", "multimodal", "text-to-image", "image generation",
    "code generation", "speech", "autoregressive", "decoder",
    "foundation model", "scaling law", "parameter-efficient",
]


def is_ai_paper(title: str) -> bool:
    """额外过滤：标题含 AI/LLM 核心关键词"""
    title_lower = title.lower()
    return any(kw in title_lower for kw in ARXIV_AI_KEYWORDS)


def clean_html(text: str) -> str:
    """移除 HTML 标签"""
    return re.sub(r"<[^>]+>", "", text)


def parse_arxiv_date(date_str: str) -> datetime:
    """解析 arXiv 日期格式（带时区）"""
    # arXiv 格式: 2024-01-15T10:30:00Z
    date_str = date_str.strip().rstrip("Z")
    try:
        return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.strptime(date_str.split("T")[0], "%Y-%m-%d").replace(tzinfo=timezone.utc)


def fetch_arxiv_papers() -> list[dict]:
    """获取 arXiv 最新 AI 论文"""
    print("[arXiv] 正在搜索最新论文...")

    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)

    params = {
        "search_query": SEARCH_QUERY,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": MAX_RESULTS,
    }

    resp = requests.get(ARXIV_API, params=params, timeout=30)
    resp.raise_for_status()

    root = ET.fromstring(resp.text)
    ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

    results = []

    for entry in root.findall("atom:entry", ns):
        # 解析字段
        title = clean_html(entry.find("atom:title", ns).text.strip())
        published = parse_arxiv_date(entry.find("atom:published", ns).text)
        updated = parse_arxiv_date(entry.find("atom:updated", ns).text)

        # 只取 48 小时内的论文
        if published < cutoff:
            continue

        # 额外的 AI 关键词过滤
        if not is_ai_paper(title):
            continue

        authors = []
        for author in entry.findall("atom:author", ns):
            name = author.find("atom:name", ns)
            if name is not None:
                authors.append(name.text.strip())

        abstract = clean_html(entry.find("atom:summary", ns).text.strip())

        # 提取 arXiv ID
        id_text = entry.find("atom:id", ns).text
        arxiv_id = id_text.split("/abs/")[-1] if "/abs/" in id_text else id_text

        # 提取分类
        categories = []
        for cat in entry.findall("atom:category", ns):
            term = cat.get("term")
            if term:
                categories.append(term)

        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
        abs_url = f"https://arxiv.org/abs/{arxiv_id}"

        results.append({
            "title": title,
            "authors": authors[:5],  # 最多取前5位作者
            "abstract": abstract[:500],  # 截断过长摘要
            "arxiv_id": arxiv_id,
            "pdf_url": pdf_url,
            "abs_url": abs_url,
            "categories": categories,
            "published": published.strftime("%Y-%m-%d"),
            "source": "arxiv",
        })

        print(f"  [arXiv] 命中: {title[:60]}...")

        # arXiv API 速率限制
        time.sleep(3)

    print(f"[arXiv] 共获取 {len(results)} 篇 AI 相关论文")
    return results


if __name__ == "__main__":
    papers = fetch_arxiv_papers()
    import json
    print(json.dumps(papers, ensure_ascii=False, indent=2))
