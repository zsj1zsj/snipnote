# AI/LLM Plugin Layer
"""
This module provides interfaces for LLM-powered features.

Features:
- Summarize highlight content
- Suggest tags based on content
"""
import json
import os
import urllib.request
from pathlib import Path
from typing import Protocol


def _load_config() -> dict:
    """Load configuration from config.json."""
    config_path = Path(__file__).parent.parent / "config.json"
    if not config_path.exists():
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


class LLMProvider(Protocol):
    """Protocol for LLM providers."""

    def summarize(self, text: str) -> str:
        """Summarize the given text."""
        ...

    def suggest_tags(self, text: str) -> list[str]:
        """Suggest tags based on the text content."""
        ...


class DummyProvider:
    """Dummy provider for testing without actual LLM API."""

    def summarize(self, text: str) -> str:
        """Return a placeholder summary."""
        return f"[AI总结] 这是一段关于 {text[:20]}... 的内容摘要"

    def suggest_tags(self, text: str) -> list[str]:
        """Return placeholder tags based on content analysis."""
        # Simple keyword-based suggestion for testing
        text_lower = text.lower()
        suggestions = []
        keywords = {
            "python": "Python",
            "javascript": "JavaScript",
            "java": "Java",
            "算法": "算法",
            "机器学习": "机器学习",
            "深度学习": "深度学习",
            "web": "Web",
            "数据库": "数据库",
            "api": "API",
            "git": "Git",
            "docker": "Docker",
            "linux": "Linux",
        }
        for keyword, tag in keywords.items():
            if keyword in text_lower:
                suggestions.append(tag)
        return suggestions[:5] or ["待分类"]


class MiniMaxProvider:
    """MiniMax LLM provider."""

    def __init__(self):
        config = _load_config()
        llm_config = config.get("llm", {})
        self.api_base_url = llm_config.get("api_base_url", "https://api.minimaxi.com/v1/chat/completions")
        self.api_key = llm_config.get("api_key", "")
        self.model = llm_config.get("model", "MiniMax-M2.5")

    def _call_api(self, messages: list[dict]) -> str:
        """Call MiniMax API and return the response."""
        if not self.api_key:
            return "[错误] 请在 config.json 中配置 API Key"

        data = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
        }

        req = urllib.request.Request(
            self.api_base_url,
            data=json.dumps(data).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result["choices"][0]["message"]["content"]
        except Exception as e:
            return f"[API错误] {str(e)}"

    def summarize(self, text: str) -> str:
        """Summarize the given text using MiniMax."""
        # Truncate text if too long
        truncated = text[:8000] if len(text) > 8000 else text

        messages = [
            {
                "role": "system",
                "content": "你是一个专业的文章总结助手。请用简洁的语言总结用户提供的文章内容，不超过100字。"
            },
            {
                "role": "user",
                "content": f"请总结以下内容：\n\n{truncated}"
            }
        ]

        return self._call_api(messages)

    def suggest_tags(self, text: str) -> list[str]:
        """Suggest tags based on the text content using MiniMax."""
        # Truncate text if too long
        truncated = text[:4000] if len(text) > 4000 else text

        messages = [
            {
                "role": "system",
                "content": "你是一个专业的标签建议助手。请根据文章内容给出3-5个合适的标签，每个标签应该是简短的关键词（如：Python、机器学习、Web开发等）。只返回标签，用逗号分隔，不要有其他内容。"
            },
            {
                "role": "user",
                "content": f"请为以下内容建议标签：\n\n{truncated}"
            }
        ]

        result = self._call_api(messages)
        # Parse the response to get tags
        tags = [t.strip() for t in result.split(",")]
        tags = [t for t in tags if t][:5]  # Limit to 5 tags
        return tags if tags else ["待分类"]


# Default provider - change this to use a different provider
# Options: DummyProvider(), MiniMaxProvider()
default_provider = MiniMaxProvider()


def summarize(text: str) -> str:
    """Summarize the given text using the default LLM provider.

    Args:
        text: The text to summarize

    Returns:
        A summarized version of the text
    """
    return default_provider.summarize(text)


def suggest_tags(text: str) -> list[str]:
    """Suggest tags based on the text content.

    Args:
        text: The text to analyze

    Returns:
        A list of suggested tags
    """
    return default_provider.suggest_tags(text)
