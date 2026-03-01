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


    @property
    def name(self) -> str:
        """Provider name."""
        ...


class DummyProvider:
    """Dummy provider for testing without actual LLM API."""

    @property
    def name(self) -> str:
        return "dummy"

    def summarize(self, text: str) -> str:
        """Return a placeholder summary."""
        return f"[AI总结] 这是一段关于 {text[:20]}... 的内容摘要"

    def suggest_tags(self, text: str, existing_tags: str = "") -> list[str]:
        """Return placeholder tags based on content analysis."""
        # Filter out existing tags from suggestions
        existing_set = set()
        if existing_tags:
            for t in existing_tags.split(","):
                existing_set.add(t.strip().lower())

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
            if keyword in text_lower and tag.lower() not in existing_set:
                suggestions.append(tag)
        # Filter out existing tags
        suggestions = [t for t in suggestions if t.lower() not in existing_set]
        return suggestions[:5] or ["待分类"]


class LLMProviderImpl:
    """LLM provider implementation (supports multiple backends)."""

    def __init__(self):
        config = _load_config()
        llm_config = config.get("llm", {})
        providers_config = config.get("providers", {})

        # Get selected provider
        provider_name = llm_config.get("provider", "minimax")

        # Get provider settings
        if provider_name in providers_config:
            provider_settings = providers_config[provider_name]
        else:
            # Fallback to legacy config
            provider_settings = {
                "api_base_url": llm_config.get("api_base_url", "https://api.minimaxi.com/v1/chat/completions"),
                "model": llm_config.get("model", "MiniMax-M2.5")
            }

        self.api_base_url = provider_settings.get("api_base_url", "https://api.minimaxi.com/v1/chat/completions")
        self.api_key = llm_config.get("api_key", "")
        self.model = provider_settings.get("model", "MiniMax-M2.5")
        self.provider_name = provider_name

        # Load tags prompt from config
        tags_config = config.get("tags", {})
        default_prompt = "你是一个专业的标签建议助手。请根据内容建议3-5个标签，采用三维标签模型：\n1. 内容类型（What）：新闻、评论、教程、视频、访谈、研究报告、技术、科普等\n2. 领域分类（Domain）：财经、体育、科技、游戏、历史、AI、编程、读书、心理学等\n3. 地域/对象（Context）：中国、日本、美国、全球、企业名、人物名等\n\n要求：1. 每个标签必须是独立的词或短语 2. 用逗号分隔每个标签，不要用+号连接 3. 只返回标签内容，不要有其他说明 4. 不要输出思考过程"
        self.tags_prompt = tags_config.get("prompt", default_prompt)

    @property
    def name(self) -> str:
        return self.provider_name

    def _call_api(self, messages: list[dict]) -> str:
        """Call LLM API and return the response."""
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
                content = result["choices"][0]["message"]["content"]
                # Filter out thinking tags if present
                return self._filter_thinking(content)
        except Exception as e:
            return f"[API错误] {str(e)}"

    def _filter_thinking(self, text: str) -> str:
        """Filter out thinking tags from the response."""
        import re
        # Remove <thinking>...</thinking> tags
        text = re.sub(r'<thinking>.*?</thinking>', '', text, flags=re.DOTALL)
        # Remove <thinking>...</thinking> variations
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        return text.strip()

    def summarize(self, text: str) -> str:
        """Summarize the given text using LLM."""
        # Truncate text if too long
        truncated = text[:8000] if len(text) > 8000 else text

        messages = [
            {
                "role": "system",
                "content": "你是一个专业的文章总结助手。请直接输出总结内容，不超过100字，不要输出思考过程。"
            },
            {
                "role": "user",
                "content": truncated
            }
        ]

        return self._call_api(messages)

    def suggest_tags(self, text: str, existing_tags: str = "") -> list[str]:
        """Suggest tags based on the text content using LLM.

        Args:
            text: The text content to analyze
            existing_tags: Comma-separated existing tags to consider
        """
        # Truncate text if too long
        truncated = text[:4000] if len(text) > 4000 else text

        # Build system prompt
        system_prompt = self.tags_prompt

        # Build user prompt with existing tags
        user_content = truncated
        if existing_tags:
            user_content = f"已有标签：{existing_tags}\n\n请根据以上内容推荐新标签（已有标签之外的）：\n\n{truncated}"

        messages = [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": user_content
            }
        ]

        result = self._call_api(messages)
        # Parse the response to get tags
        tags = [t.strip() for t in result.split(",")]
        tags = [t for t in tags if t][:5]  # Limit to 5 tags
        return tags if tags else ["待分类"]


# Default provider
default_provider = LLMProviderImpl()


def summarize(text: str) -> str:
    """Summarize the given text using the default LLM provider.

    Args:
        text: The text to summarize

    Returns:
        A summarized version of the text
    """
    return default_provider.summarize(text)


def suggest_tags(text: str, existing_tags: str = "") -> list[str]:
    """Suggest tags based on the text content.

    Args:
        text: The text to analyze
        existing_tags: Comma-separated existing tags to consider

    Returns:
        A list of suggested tags
    """
    return default_provider.suggest_tags(text, existing_tags)
