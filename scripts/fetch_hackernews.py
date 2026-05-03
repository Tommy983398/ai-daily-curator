"""
fetch_hackernews.py - 抓取 Hacker News AI 相关高分帖子

使用 Hacker News Firebase API 获取 Top Stories，
过滤 AI 相关帖子（score > 50）。
"""

import requests
import json
import re
import time
from datetime import datetime, timezone, timedelta

HN_API = "https://hacker-news.firebaseio.com/v0"

AI_KEYWORDS = [
    "ai", "artificial intelligence", "machine learning", "deep learning",
    "llm", "gpt", "chatgpt", "claude", "gemini", "openai", "anthropic",
    "neural network", "transformer", "diffusion", "stable diffusion",
    "midjourney", "dall-e", "dalle", "generative", "language model",
    "reinforcement learning", "computer vision", "nlp", "natural language",
    "bert", "fine-tuning", "finetuning", "prompt engineering",
    "rag", "embedding", "vector database", "huggingface", "hugging face",
    "autonomous agent", "multi-agent", "agent", "robotics",
    "speech recognition", "text-to-speech", "tts", "stt",
    "vision model", "image generation", "code generation", "copilot",
    "large model", "foundation model", "multimodal", "vision-language",
    "mistral", "llama", "falcon", "phi", "qwen", "yi ",
]

ONE_DAY_AGO = int((datetime.now(timezone.utc) - timedelta(hours=36)).timestamp())


def is_ai_related(title: str) -> bool:
    """检查标题是否包含 AI 相关关键词（不区分大小写）"""
    title_lower = title.lower()
    return any(kw in title_lower for kw in AI_KEYWORDS)


def fetch_top_stories(limit: int = 200) -> list[dict]:
    """获取 Top Stories 并过滤 AI 相关帖子"""
    print("[HN] 正在获取 Top Stories...")
    resp = requests.get(f"{HN_API}/topstories.json", timeout=30)
    resp.raise_for_status()
    story_ids = resp.json()[:limit]

    results = []
    checked = 0

    for sid in story_ids:
        try:
            item_resp = requests.get(f"{HN_API}/item/{sid}.json", timeout=15)
            item_resp.raise_for_status()
            item = item_resp.json()

            if not item:
                continue

            checked += 1

            # 过滤条件：分数 > 50、AI相关、36小时内
            score = item.get("score", 0)
            title = item.get("title", "")
            timestamp = item.get("time", 0)

            if score < 50:
                continue
            if not is_ai_related(title):
                continue
            if timestamp < ONE_DAY_AGO:
                continue

            results.append({
                "title": title,
                "url": item.get("url", f"https://news.ycombinator.com/item?id={sid}"),
                "score": score,
                "hn_id": sid,
                "time": timestamp,
                "time_str": datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                "source": "hackernews",
            })

            print(f"  [HN] 命中: {title[:60]}... (score={score})")

        except requests.RequestException as e:
            print(f"  [HN] 请求失败 sid={sid}: {e}")
            continue

        # 简单的速率控制
        if checked % 20 == 0:
            time.sleep(1)

    results.sort(key=lambda x: x["score"], reverse=True)
    print(f"[HN] 共检查 {checked} 条，命中 {len(results)} 条 AI 帖子")
    return results


if __name__ == "__main__":
    stories = fetch_top_stories()
    print(json.dumps(stories, ensure_ascii=False, indent=2))
