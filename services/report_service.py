# Daily Report Service
"""
生成每日阅读报告
"""
import datetime as dt
import os
from datetime import date, timedelta
from pathlib import Path

from storage import connect


def today() -> date:
    return dt.date.today()


def yesterday() -> date:
    return today() - timedelta(days=1)


def iso_date(value: date) -> str:
    return value.isoformat()


def _get_reports_dir() -> Path:
    """Get reports directory, create if not exists."""
    home = Path.home()
    reports_dir = home / ".snipnote" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    return reports_dir


class ReportService:
    """Service for generating daily reports."""

    def __init__(self, db_path: str = "data/readlite.db"):
        self.db_path = db_path

    def _collect_stats(self, target_date: date) -> dict:
        """Collect statistics for a specific date."""
        conn = connect(Path(self.db_path))
        date_str = iso_date(target_date)

        # 1. 昨日新增未读
        new_unread = conn.execute(
            "SELECT id, text, source, author, tags FROM highlights WHERE date(created_at) = date(?) AND is_read = 0",
            (date_str,)
        ).fetchall()

        # 2. 昨日完成阅读（从unread变为read）
        read_completed = conn.execute(
            "SELECT id, text, source, author, tags FROM highlights WHERE date(last_reviewed) = date(?) AND is_read = 1",
            (date_str,)
        ).fetchall()

        # 3. 昨日复习情况
        reviewed = conn.execute(
            "SELECT id, text, source, author, tags, last_reviewed FROM highlights WHERE date(last_reviewed) = date(?)",
            (date_str,),
        ).fetchall()

        # 复习正确率（quality >= 3 为正确）
        # Note: 需要在 review 记录中记录 quality，这里简化处理

        # 4. 当前阅读负债
        backlog = conn.execute(
            "SELECT COUNT(*) as c FROM highlights WHERE is_read = 0",
        ).fetchone()["c"]

        # 5. 今日到期复习
        due_review = conn.execute(
            "SELECT COUNT(*) as c FROM highlights WHERE date(next_review) <= date(?)",
            (iso_date(today()),)
        ).fetchone()["c"]

        # 6. Top tags
        all_tags = conn.execute("SELECT tags FROM highlights WHERE tags != ''").fetchall()
        tag_counts: dict[str, int] = {}
        for row in all_tags:
            tags_str = row["tags"] or ""
            for tag in tags_str.split(","):
                tag = tag.strip()
                if tag:
                    tag = tag.lower()
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1
        top_tags = sorted(tag_counts.items(), key=lambda x: -x[1])[:5]
        top_tags_dict = {t[0]: t[1] for t in top_tags}

        conn.close()

        return {
            "new_unread": [dict(r) for r in new_unread],
            "read_completed": [dict(r) for r in read_completed],
            "reviewed": [dict(r) for r in reviewed],
            "backlog": backlog,
            "due_review": due_review,
            "top_tags": top_tags_dict,
        }

    def _calculate_debt_score(self, backlog: int, due_review: int) -> tuple[str, str]:
        """Calculate reading debt score."""
        score = backlog * 0.5 + due_review * 1.2
        if score < 10:
            return "🟢 健康", score
        elif score < 30:
            return "🟡 略高", score
        else:
            return "🔴 危险", score

    def _generate_ai_insights(self, stats: dict) -> dict:
        """Generate structured AI insights for the daily report."""
        from ai import summarize as ai_summarize

        # Prepare detailed context for AI
        context_parts = []

        # Reading activity
        if stats["new_unread"]:
            context_parts.append(f"昨日新增{len(stats['new_unread'])}条未读内容")
        if stats["read_completed"]:
            context_parts.append(f"完成{len(stats['read_completed'])}条阅读")
        if stats["reviewed"]:
            context_parts.append(f"复习{len(stats['reviewed'])}次")
        context_parts.append(f"当前阅读负债{stats['backlog']}条")

        # Top tags and sources
        if stats["top_tags"]:
            context_parts.append(f"主要阅读主题：{', '.join(list(stats['top_tags'].keys())[:3])}")

        # Sources
        all_sources = set()
        for item in stats.get("new_unread", []) + stats.get("read_completed", []):
            if item.get("source"):
                all_sources.add(item["source"])
        if all_sources:
            context_parts.append(f"内容来源：{', '.join(list(all_sources)[:5])}")

        context = "，".join(context_parts) + "。"

        # Detailed content for AI to analyze
        content_details = []
        for item in (stats.get("new_unread", []) + stats.get("read_completed", []))[:10]:
            text = item.get("text", "")[:200]
            source = item.get("source", "")
            tags = item.get("tags", "")
            if text:
                content_details.append(f"来源：{source}，标签：{tags}，内容：{text}")

        detailed_content = "\n".join(content_details) if content_details else "无详细内容"

        # Build the prompt for structured insights
        prompt = f"""请分析以下昨日阅读数据，生成结构化的阅读日报分析。

昨日阅读概况：{context}

详细内容：
{detailed_content}

请按以下格式输出分析结果（每项单独一行，不要使用编号或列表符号）：

昨日阅读主题概述：[不超过120字的主题概述]

核心洞察：[第1条核心洞察]
核心洞察：[第2条核心洞察]
核心洞察：[第3条核心洞察]

学习趋势分析：[一行学习趋势分析]

改进建议：[第1条改进建议]
改进建议：[第2条改进建议]

一句总结金句：[一句简短的总结金句]"""

        # Call AI
        result = ai_summarize(prompt)

        # Parse the structured response
        lines = result.split("\n") if result else []
        insights = {
            "overview": "",
            "insights": [],
            "trend": "",
            "suggestions": [],
            "quote": ""
        }

        current_section = None
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if "昨日阅读主题概述" in line:
                current_section = "overview"
                insights["overview"] = line.split("：", 1)[-1] if "：" in line else ""
            elif "核心洞察" in line:
                current_section = "insights"
                insight = line.split("：", 1)[-1] if "：" in line else line
                if insight and len(insights["insights"]) < 3:
                    insights["insights"].append(insight)
            elif "学习趋势分析" in line:
                current_section = "trend"
                insights["trend"] = line.split("：", 1)[-1] if "：" in line else ""
            elif "改进建议" in line:
                current_section = "suggestions"
                suggestion = line.split("：", 1)[-1] if "：" in line else line
                if suggestion and len(insights["suggestions"]) < 2:
                    insights["suggestions"].append(suggestion)
            elif "一句总结金句" in line:
                current_section = "quote"
                insights["quote"] = line.split("：", 1)[-1] if "：" in line else ""
            elif current_section == "overview" and insights["overview"]:
                insights["overview"] += " " + line
            elif current_section == "trend" and insights["trend"]:
                insights["trend"] += " " + line
            elif current_section == "quote" and insights["quote"]:
                insights["quote"] += " " + line

        # Truncate overview to 120 chars
        if len(insights["overview"]) > 120:
            insights["overview"] = insights["overview"][:117] + "..."

        return insights

    def _generate_report_content(self, stats: dict, target_date: date) -> str:
        """Generate markdown report content."""
        date_str = iso_date(target_date)
        debt_status, debt_score = self._calculate_debt_score(stats["backlog"], stats["due_review"])

        lines = []
        lines.append(f"# 昨日阅读日报 ({date_str})")
        lines.append("")
        lines.append("## 📊 概览")
        lines.append(f"- 新增未读：{len(stats['new_unread'])} 条")
        lines.append(f"- 完成阅读：{len(stats['read_completed'])} 条")
        lines.append(f"- 复习次数：{len(stats['reviewed'])} 次")
        lines.append(f"- 阅读负债：{stats['backlog']} 条")
        lines.append(f"- 今日到期复习：{stats['due_review']} 条")
        lines.append(f"- 负债指数：{debt_status} ({debt_score:.1f})")
        lines.append("")

        # Top tags
        if stats["top_tags"]:
            lines.append("## 🏷️ 阅读分布")
            for tag, count in stats["top_tags"].items():
                lines.append(f"- {tag}: {count}")
            lines.append("")

        # 新增未读
        if stats["new_unread"]:
            lines.append("## 📥 昨日新增未读")
            for item in stats["new_unread"][:5]:
                source = item.get("source", "")
                text = item.get("text", "")[:100]
                lines.append(f"- {source}: {text}...")
            if len(stats["new_unread"]) > 5:
                lines.append(f"- ...还有 {len(stats['new_unread']) - 5} 条")
            lines.append("")

        # 完成阅读
        if stats["read_completed"]:
            lines.append("## ✅ 昨日完成阅读")
            for item in stats["read_completed"][:5]:
                source = item.get("source", "")
                text = item.get("text", "")[:100]
                lines.append(f"- {source}: {text}...")
            lines.append("")

        # 复习
        if stats["reviewed"]:
            lines.append("## 🔄 昨日复习")
            for item in stats["reviewed"][:5]:
                source = item.get("source", "")
                lines.append(f"- {source}")
            lines.append("")

        # AI 分析 - 使用结构化输出
        lines.append("## 🤖 AI 分析")

        # 调用 AI 生成结构化分析
        try:
            insights = self._generate_ai_insights(stats)

            # 昨日阅读主题概述
            if insights["overview"]:
                lines.append(f"**昨日阅读主题概述**：{insights['overview']}")
                lines.append("")

            # 核心洞察
            if insights["insights"]:
                lines.append("**核心洞察**：")
                for i, insight in enumerate(insights["insights"], 1):
                    lines.append(f"{i}. {insight}")
                lines.append("")

            # 学习趋势分析
            if insights["trend"]:
                lines.append(f"**学习趋势分析**：{insights['trend']}")
                lines.append("")

            # 改进建议
            if insights["suggestions"]:
                lines.append("**改进建议**：")
                for i, suggestion in enumerate(insights["suggestions"], 1):
                    lines.append(f"{i}. {suggestion}")
                lines.append("")

            # 一句总结金句
            if insights["quote"]:
                lines.append(f"**一句总结金句**：{insights['quote']}")

        except Exception as e:
            lines.append(f"（AI 分析生成失败：{e}）")

        lines.append("")
        lines.append(f"---\n*由 SnipNote 自动生成*")

        return "\n".join(lines)

    def _save_to_db(self, target_date: date, content: str, force: bool = False) -> None:
        """Save report to database."""
        conn = connect(Path(self.db_path))
        date_str = iso_date(target_date)
        now = dt.datetime.now().isoformat(timespec="seconds")

        # 如果已存在且不强制覆盖，则跳过
        exists = conn.execute(
            "SELECT id FROM daily_reports WHERE report_date = ?",
            (date_str,)
        ).fetchone()

        if exists:
            if force:
                # 强制覆盖：先删除旧记录
                conn.execute("DELETE FROM daily_reports WHERE report_date = ?", (date_str,))
            else:
                conn.close()
                return False

        conn.execute(
            "INSERT INTO daily_reports (report_date, content, created_at) VALUES (?, ?, ?)",
            (date_str, content, now),
        )
        conn.commit()
        conn.close()
        return True

    def _save_to_file(self, target_date: date, content: str) -> None:
        """Save report to markdown file."""
        date_str = iso_date(target_date)
        filepath = _get_reports_dir() / f"{date_str}.md"
        filepath.write_text(content, encoding="utf-8")

    def generate(self, target_date: date = None, force: bool = False) -> str:
        """Generate daily report for a specific date.

        Args:
            target_date: Date to generate report for, defaults to yesterday
            force: Force regenerate if exists

        Returns:
            Path to the generated report file
        """
        if target_date is None:
            target_date = yesterday()

        date_str = iso_date(target_date)

        # 幂等检查
        if not force:
            conn = connect(Path(self.db_path))
            exists = conn.execute(
                "SELECT id FROM daily_reports WHERE report_date = ?",
                (date_str,)
            ).fetchone()
            conn.close()
            if exists:
                filepath = _get_reports_dir() / f"{date_str}.md"
                return str(filepath)

        # 收集统计
        stats = self._collect_stats(target_date)

        # 生成报告
        content = self._generate_report_content(stats, target_date)

        # 保存到数据库
        self._save_to_db(target_date, content, force=force)

        # 保存到文件
        self._save_to_file(target_date, content)

        filepath = _get_reports_dir() / f"{date_str}.md"
        return str(filepath)


def generate_daily_report(db_path: str = "data/readlite.db") -> str:
    """Convenience function to generate yesterday's report."""
    service = ReportService(db_path)
    return service.generate()
