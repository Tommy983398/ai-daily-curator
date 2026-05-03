"""
fetch_github_releases.py - 抓取 GitHub 热门 AI 项目 Release 动态

监控预设的 AI 项目的最新 Release，
返回最近 24 小时内的 Release 信息。
"""

import requests
import os
import time
from datetime import datetime, timezone, timedelta

GITHUB_API = "https://api.github.com"

# 监控的 AI 项目列表
WATCHED_REPOS = [
    "openai/openai-python",
    "openai/whisper",
    "anthropics/anthropic-sdk-python",
    "microsoft/autogen",
    "langchain-ai/langchain",
    "langchain-ai/langgraph",
    "huggingface/transformers",
    "huggingface/diffusers",
    "mem0ai/mem0",
    "ollama/ollama",
    "meta-llama/llama-models",
    "vllm-project/vllm",
    "mistralai/mistral-common",
    "pytorch/pytorch",
    "tensorflow/tensorflow",
]

ONE_DAY_AGO = datetime.now(timezone.utc) - timedelta(hours=24)


def get_github_token() -> str | None:
    """获取 GitHub Token"""
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        token = os.environ.get("GH_TOKEN", "")
    return token if token else None


def fetch_releases() -> list[dict]:
    """获取最近 24 小时内的 Release"""
    print("[GitHub Releases] 正在检查监控项目...")

    token = get_github_token()
    headers = {
        "Accept": "application/vnd.github.v3+json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    results = []

    for repo in WATCHED_REPOS:
        try:
            url = f"{GITHUB_API}/repos/{repo}/releases?per_page=3"
            resp = requests.get(url, headers=headers, timeout=15)

            # 速率限制检查
            if resp.status_code == 403:
                print(f"  [GitHub] 速率限制，停止请求")
                break

            if resp.status_code == 404:
                print(f"  [GitHub] 仓库不存在或无权限: {repo}")
                continue

            resp.raise_for_status()
            releases = resp.json()

            for release in releases:
                published = release.get("published_at", "")
                if not published:
                    continue

                pub_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
                if pub_dt < ONE_DAY_AGO:
                    continue

                body = release.get("body", "") or ""
                results.append({
                    "repo": repo,
                    "tag_name": release.get("tag_name", ""),
                    "name": release.get("name", ""),
                    "published_at": published,
                    "body": body[:500],  # 截断
                    "html_url": release.get("html_url", ""),
                    "source": "github_release",
                })

                print(f"  [GitHub Release] 命中: {repo} - {release.get('tag_name', '')}")

        except requests.RequestException as e:
            print(f"  [GitHub Release] 请求失败 {repo}: {e}")

        # 速率控制
        time.sleep(1)

    results.sort(key=lambda x: x["published_at"], reverse=True)
    print(f"[GitHub Releases] 共获取 {len(results)} 个新 Release")
    return results


if __name__ == "__main__":
    releases = fetch_releases()
    import json
    print(json.dumps(releases, ensure_ascii=False, indent=2))
