"""
Term progress business rule — computes weeks elapsed, weeks remaining,
and overall progress for the current academic term.

Shared by the school details projection and any dashboard that needs
term-level timing data.
"""
from datetime import date
from typing import Optional

from .dto import TermProgressDTO


class TermProgressService:
    """Pure computation of term timing/progress. No DB writes."""

    @staticmethod
    def build(term, today: Optional[date] = None) -> Optional[TermProgressDTO]:
        if term is None:
            return None

        today = today or date.today()
        total_days = (term.end_date - term.start_date).days or 1
        elapsed_days = max(0, (today - term.start_date).days)

        progress_percent = min(100, round((elapsed_days / total_days) * 100))
        total_weeks = total_days // 7
        current_week = min((elapsed_days // 7) + 1, total_weeks)
        days_remaining = max(0, (term.end_date - today).days)

        return TermProgressDTO(
            id=str(term.id),
            name=term.get_name_display(),
            start_date=term.start_date,
            end_date=term.end_date,
            next_reopening_date=term.next_reopening_date,
            current_week=current_week,
            total_weeks=total_weeks,
            days_remaining=days_remaining,
            progress_percent=progress_percent,
        )