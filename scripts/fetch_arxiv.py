"""
fetch_arxiv.py - 抓取 arXiv 热门 AI/LLM 论文

策略：
1. 搜索最近 7 天的 cs.AI / cs.LG / cs.CL 论文
2. 多维度关键词匹配，覆盖前沿 AI 研究
3. 取最相关、最有价值的 5-8 篇
"""

import requests
import re
import time
from datetime import datetime, timezone, timedelta
import xml.etree.ElementTree as ET

ARXIV_API = "http://export.arxiv.org/api/query"

# 搜索分类：AI / 机器学习 / 自然语言处理 / 计算机视觉
SEARCH_QUERIES = [
    "cat:cs.AI AND (abs:agent OR abs:reasoning OR abs:alignment)",
    "cat:cs.CL AND (abs:language model OR abs:LLM OR abs:instruction)",
    "cat:cs.LG AND (abs:scaling OR abs:efficient OR abs:foundation model)",
    "cat:cs.CV AND (abs:diffusion OR abs:generation OR abs:multimodal)",
]

MAX_RESULTS_PER_QUERY = 15  # 每个查询最多取 15 条

# 优先级关键词（命中越多越相关）
HIGH_PRIORITY_KW = [
    "agent", "multi-agent", "autonomous agent", "ai agent",
    "reasoning", "chain-of-thought", "deepseek", "gpt", "claude", "gemini",
    "scaling law", "mixture of experts", "moe",
    "reinforcement learning", "rlhf", "dpo", "grpo",
    "world model", "planning", "tool use", "function calling",
    "code generation", "code model",
    "diffusion", "text-to-image", "video generation",
    "multimodal", "vision-language", "vlm",
    "retrieval augmented", "rag", "long context",
    "alignment", "safety", "jailbreak",
    "efficient", "quantization", "distillation", "pruning",
    "open-source", "open weights",
]

MEDIUM_PRIORITY_KW = [
    "transformer", "attention", "bert", "encoder", "decoder",
    "prompt", "fine-tun", "in-context learning",
    "embedding", "vector", "knowledge graph",
    "neural network", "deep learning", "representation",
    "self-supervised", "pre-train", "transfer learning",
    "nlp", "sentiment", "named entity", "parsing",
    "computer vision", "object detection", "segmentation",
    "generative", "adversarial", "gan", "vae",
    "speech", "tts", "asr", "audio",
    "robotics", "control", "sim-to-real",
    "federated learning", "privacy", "robustness",
    "benchmark", "evaluation", "human evaluation",
    "medical", "clinical", "drug", "protein",
]


def score_paper(title: str, abstract: str) -> int:
    """根据标题和摘要对论文打分，分越高越相关"""
    text = (title + " " + abstract).lower()
    score = 0
    for kw in HIGH_PRIORITY_KW:
        if kw in text:
            score += 3
    for kw in MEDIUM_PRIORITY_KW:
        if kw in text:
            score += 1
    return score


def clean_html(text: str) -> str:
    """移除 HTML 标签"""
    return re.sub(r"<[^>]+>", "", text)


def parse_arxiv_date(date_str: str) -> datetime:
    """解析 arXiv 日期格式"""
    date_str = date_str.strip().rstrip("Z")
    try:
        return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.strptime(date_str.split("T")[0], "%Y-%m-%d").replace(tzinfo=timezone.utc)


def fetch_arxiv_papers(max_papers: int = 8) -> list[dict]:
    """获取 arXiv 高质量 AI 论文"""
    print("[arXiv] 正在搜索最近 7 天的热门 AI 论文...")

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    all_papers = []
    seen_ids = set()

    for query in SEARCH_QUERIES:
        try:
            params = {
                "search_query": query,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
                "max_results": MAX_RESULTS_PER_QUERY,
            }
            resp = requests.get(ARXIV_API, params=params, timeout=30)
            resp.raise_for_status()

            root = ET.fromstring(resp.text)
            ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

            for entry in root.findall("atom:entry", ns):
                title = clean_html(entry.find("atom:title", ns).text.strip())
                published = parse_arxiv_date(entry.find("atom:published", ns).text)

                if published < cutoff:
                    continue

                # 提取 arXiv ID 去重
                id_text = entry.find("atom:id", ns).text
                arxiv_id = id_text.split("/abs/")[-1] if "/abs/" in id_text else id_text
                if arxiv_id in seen_ids:
                    continue
                seen_ids.add(arxiv_id)

                authors = []
                for author in entry.findall("atom:author", ns):
                    name = author.find("atom:name", ns)
                    if name is not None:
                        authors.append(name.text.strip())

                abstract = clean_html(entry.find("atom:summary", ns).text.strip())

                categories = []
                for cat in entry.findall("atom:category", ns):
                    term = cat.get("term")
                    if term:
                        categories.append(term)

                score = score_paper(title, abstract)

                all_papers.append({
                    "title": title,
                    "authors": authors[:5],
                    "abstract": abstract[:800],
                    "arxiv_id": arxiv_id,
                    "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
                    "abs_url": f"https://arxiv.org/abs/{arxiv_id}",
                    "categories": categories,
                    "published": published.strftime("%Y-%m-%d"),
                    "source": "arxiv",
                    "_score": score,
                })

            time.sleep(3)  # arXiv API 速率限制

        except requests.RequestException as e:
            print(f"  [arXiv] 查询失败: {e}")
            continue

    # 按相关度排序，取 TOP N
    all_papers.sort(key=lambda x: x["_score"], reverse=True)
    selected = all_papers[:max_papers]

    # 清理内部字段
    for p in selected:
        del p["_score"]

    print(f"[arXiv] 共检索 {len(all_papers)} 篇，精选 {len(selected)} 篇")
    for p in selected:
        print(f"  [arXiv] {p['title'][:60]}... ({p['published']})")

    return selected


if __name__ == "__main__":
    papers = fetch_arxiv_papers()
    import json
    print(json.dumps(papers, ensure_ascii=False, indent=2))
