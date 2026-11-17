import os

import requests


class ChatClient:
    def __init__(self, api_key=None, base_url=None, model=None, timeout=90):
        self.api_key = api_key or os.environ.get("LLM_API_KEY", "")
        self.base_url = (
            base_url or os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/v1")
        ).rstrip("/")
        self.model = model or os.environ.get("LLM_MODEL", "deepseek-chat")
        self.timeout = timeout

    def complete(self, messages, tools=None, temperature=0):
        if not self.api_key:
            raise RuntimeError("缺少 LLM_API_KEY，请先设置环境变量")

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools

        resp = requests.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]
