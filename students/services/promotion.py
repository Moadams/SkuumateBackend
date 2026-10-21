"""Student promotion between classes / academic years.

``PromotionService`` owns the business rules for moving students from one class
to another in a (typically different) academic year. Enrollments are stored per
academic year, so a promotion creates a new ``Enrollment`` in the target year
and records the per-student outcome on a ``Promotion`` row for history/undo.

The term is accepted for reporting only — it does not participate in the
duplicate check (which is per academic year, matching the ``Enrollment`` model).
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from students.models import Enrollment, Promotion, PromotionBatch


class PromotionService:
    """Create and reverse promotion batches. Views stay transport-only."""

    @classmethod
    @transaction.atomic
    def promote(
        cls,
        *,
        school,
        students,
        to_class,
        to_academic_year,
        to_term=None,
        from_class=None,
        from_academic_year=None,
        promoted_by=None,
        notes="",
    ) -> PromotionBatch:
        """Promote ``students`` into ``to_class`` for ``to_academic_year``.

        Students who already have an active enrollment for the target academic
        year are skipped and reported (they cannot be double-enrolled in the
        same year). ``from_class`` / ``from_academic_year`` only refine the
        recorded source; they never block the promotion.
        """
        students = list(students)
        student_ids = [student.pk for student in students]

        # Source enrollments (for history) — the student's active enrollment in
        # the source year, or the current year when none was supplied.
        source_qs = Enrollment.objects.filter(
            school=school,
            student_id__in=student_ids,
            is_active=True,
        ).select_related("klass", "academic_year")
        if from_academic_year is not None:
            source_qs = source_qs.filter(academic_year=from_academic_year)
        else:
            source_qs = source_qs.filter(academic_year__is_current=True)
        if from_class is not None:
            source_qs = source_qs.filter(klass=from_class)
        source_map = {enrollment.student_id: enrollment for enrollment in source_qs}

        # Any active enrollment already in the target year — the duplicate check.
        target_map = {
            enrollment.student_id: enrollment
            for enrollment in Enrollment.objects.filter(
                school=school,
                student_id__in=student_ids,
                academic_year=to_academic_year,
                is_active=True,
            ).select_related("klass")
        }

        batch = PromotionBatch.objects.create(
            school=school,
            from_academic_year=from_academic_year,
            from_class=from_class,
            to_academic_year=to_academic_year,
            to_class=to_class,
            to_term=to_term,
            promoted_by=promoted_by,
            notes=notes or "",
        )

        items = []
        for student in students:
            existing = target_map.get(student.pk)

            if existing is not None and existing.klass_id == to_class.pk:
                items.append(
                    Promotion(
                        school=school,
                        batch=batch,
                        student=student,
                        from_enrollment=source_map.get(student.pk),
                        outcome=Promotion.Outcome.SKIPPED,
                        message=(
                            f"Already enrolled in {to_class.name} for "
                            f"{to_academic_year.name}."
                        ),
                    )
                )
                continue

            if existing is not None:
                items.append(
                    Promotion(
                        school=school,
                        batch=batch,
                        student=student,
                        from_enrollment=source_map.get(student.pk),
                        outcome=Promotion.Outcome.SKIPPED,
                        message=(
                            f"Already enrolled in {existing.klass.name} for "
                            f"{to_academic_year.name}; withdraw before promoting."
                        ),
                    )
                )
                continue

            enrollment = Enrollment.objects.create(
                school=school,
                student=student,
                klass=to_class,
                academic_year=to_academic_year,
            )
            items.append(
                Promotion(
                    school=school,
                    batch=batch,
                    student=student,
                    from_enrollment=source_map.get(student.pk),
                    resulting_enrollment=enrollment,
                    outcome=Promotion.Outcome.PROMOTED,
                    message=(
                        f"Promoted to {to_class.name} ({to_academic_year.name})."
                    ),
                )
            )

        Promotion.objects.bulk_create(items)
        return batch

    @classmethod
    @transaction.atomic
    def reverse(cls, batch: PromotionBatch) -> PromotionBatch:
        """Undo a batch: delete the enrollments it created and mark it reversed."""
        for item in batch.items.filter(
            outcome=Promotion.Outcome.PROMOTED
        ).select_related("resulting_enrollment"):
            if item.resulting_enrollment is not None:
                item.resulting_enrollment.delete()

        batch.status = PromotionBatch.Status.REVERSED
        batch.reversed_at = timezone.now()
        batch.save(update_fields=["status", "reversed_at", "updated_at"])
        return batch
