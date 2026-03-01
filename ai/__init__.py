# AI/LLM Plugin Layer
"""
This module provides interfaces for LLM-powered features.

Features:
- Summarize highlight content
- Suggest tags based on content
"""
from typing import Protocol


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


# Default provider - change this to use a real LLM
default_provider = DummyProvider()


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
