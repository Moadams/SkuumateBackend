"""
Attendance statistics business rules — daily rollups, term averages,
and recent daily history for a school.
"""
from datetime import date
from typing import List, Optional

from django.db.models import Avg

from .dto import AttendanceDTO, AttendanceDayDTO, AttendanceTodayDTO


class AttendanceStatsService:
    """Read-only attendance aggregations. No DB writes."""

    @staticmethod
    def today(school, day: Optional[date] = None) -> AttendanceTodayDTO:
        from attendance.models import Attendance

        day = day or date.today()
        records = Attendance.objects.filter(school=school, date=day)
        total = records.count()
        present = records.filter(status=Attendance.Status.PRESENT).count()
        absent = records.filter(status=Attendance.Status.ABSENT).count()
        late = records.filter(status=Attendance.Status.LATE).count()
        percentage = round((present / total) * 100, 2) if total else 0

        return AttendanceTodayDTO(
            date=day,
            total=total,
            present=present,
            absent=absent,
            late=late,
            percentage=percentage,
        )

    @staticmethod
    def term_average(school, term) -> float:
        from attendance.models import AttendanceSummary

        if term is None:
            return 0
        result = (
            AttendanceSummary.objects
            .filter(school=school, term=term)
            .aggregate(avg=Avg("attendance_percentage"))
        )
        return float(result["avg"] or 0)

    @staticmethod
    def last_days(school, days: int = 7) -> List[AttendanceDayDTO]:
        from attendance.models import AttendanceSummary

        summaries = (
            AttendanceSummary.objects
            .filter(school=school)
            .order_by("-date")[:days]
        )
        return [
            AttendanceDayDTO(
                date=summary.date,
                percentage=float(summary.attendance_percentage),
                present=summary.present_count,
                total=summary.total_students,
            )
            for summary in summaries
        ]

    @staticmethod
    def build(school, term) -> AttendanceDTO:
        return AttendanceDTO(
            today=AttendanceStatsService.today(school),
            term_average_percentage=round(
                AttendanceStatsService.term_average(school, term), 2
            ),
            last_7_days=AttendanceStatsService.last_days(school, 7),
        )