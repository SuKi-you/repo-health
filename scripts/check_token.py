"""检查 GITHUB_TOKEN 是否生效，并打印当前额度。

/rate_limit 这个端点本身不计入配额，所以随便跑。
用法：python scripts/check_token.py
"""

from __future__ import annotations

import os
import sys

import requests


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    headers = {
        "User-Agent": "oss-health",
        "Accept": "application/vnd.github+json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    resp = requests.get(
        "https://api.github.com/rate_limit", headers=headers, timeout=10
    )
    resp.raise_for_status()
    core = resp.json()["resources"]["core"]

    if token:
        print("token: 已配置")
    else:
        print("token: 未配置 —— 现在只有 60 次/小时，开发时半小时就会撞墙")
    print(f"额度: {core['remaining']} / {core['limit']}")
    return 0 if token else 1


if __name__ == "__main__":
    sys.exit(main())
