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

    def _generate_report_content(self, stats: dict, target_date: date) -> str:
        """Generate markdown report content."""
        from ai import summarize as ai_summarize

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

        # AI 分析
        lines.append("## 🤖 AI 分析")

        # 准备摘要给 AI
        summary_parts = []
        if stats["new_unread"]:
            summary_parts.append(f"昨日新增{len(stats['new_unread'])}条未读")
        if stats["read_completed"]:
            summary_parts.append(f"完成{len(stats['read_completed'])}条阅读")
        if stats["reviewed"]:
            summary_parts.append(f"复习{len(stats['reviewed'])}次")
        summary_parts.append(f"当前负债{stats['backlog']}条")

        ai_input = "，".join(summary_parts)
        if stats["top_tags"]:
            ai_input += f"。主要阅读主题包括：{', '.join(stats['top_tags'].keys())}"

        # 调用 AI 生成分析
        ai_report = ai_summarize(ai_input)
        lines.append(ai_report if ai_report else "（AI 分析生成中...）")
        lines.append("")

        # 次日建议
        lines.append("## 💡 次日建议")
        suggestions = []
        if stats["due_review"] > 10:
            suggestions.append("今日有较多复习任务，建议优先处理")
        if stats["backlog"] > 50:
            suggestions.append("阅读负债较高，建议减少新内容摄入")
        if stats["new_unread"]:
            suggestions.append(f"新摄入{len(stats['new_unread'])}条内容，注意消化")
        if not suggestions:
            suggestions.append("继续保持阅读节奏")
        for s in suggestions:
            lines.append(f"- {s}")

        lines.append("")
        lines.append(f"---\n*由 SnipNote 自动生成*")

        return "\n".join(lines)

    def _save_to_db(self, target_date: date, content: str) -> None:
        """Save report to database."""
        conn = connect(Path(self.db_path))
        date_str = iso_date(target_date)
        now = dt.datetime.now().isoformat(timespec="seconds")

        # 幂等：如果已存在则跳过
        exists = conn.execute(
            "SELECT id FROM daily_reports WHERE report_date = ?",
            (date_str,)
        ).fetchone()

        if exists:
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
        self._save_to_db(target_date, content)

        # 保存到文件
        self._save_to_file(target_date, content)

        filepath = _get_reports_dir() / f"{date_str}.md"
        return str(filepath)


def generate_daily_report(db_path: str = "data/readlite.db") -> str:
    """Convenience function to generate yesterday's report."""
    service = ReportService(db_path)
    return service.generate()
