from decimal import Decimal
from collections import defaultdict

class ScoreEngine:

    @staticmethod
    def compute(*, students, marks, report_scheme, grade_scales):
        qs, sba_ids, exam_id = marks
        
        mark_map = defaultdict(lambda: defaultdict(lambda: {"sba": [], "exam": None}))

        for m in qs:
            bucket = mark_map[m.student_id][m.subject_id]
            
            if m.assessment_id == exam_id:
                bucket["exam"] = m.score
            elif m.assessment_id in sba_ids:
                if m.score is not None:
                    bucket["sba"].append({
                        "score":m.score,
                        "out_of":m.assessment.max_score
                        })

        sba_weight = Decimal(report_scheme.sba_scaling) / 100
        exam_weight = Decimal(report_scheme.exam_scaling) / 100
        TWO = Decimal("0.01")

        result = {}

        for student in students:
            subj_map = mark_map.get(student.id, {})

            rows = []
            total = Decimal("0")

            for subject_id, scores in subj_map.items():
                sba_obtained = sum(
                    item['score'] for item in scores["sba"]
                )
                sba_total = sum(
                    item["out_of"] for item in scores["sba"]
                )
                if sba_total:
                    sba_percentage = (
                        Decimal(sba_obtained) / Decimal(sba_total)
                    ) * Decimal("100")
                else:
                    sba_percentage = Decimal("0")

                sba_scaled = (
                    sba_percentage * sba_weight
                ).quantize(TWO)
                
                exam = scores["exam"] if scores["exam"] is not None else Decimal("0")

                exam_scaled = (exam * exam_weight).quantize(TWO)

                final = (sba_scaled + exam_scaled).quantize(TWO)

                rows.append({
                    "subject_id": subject_id,
                    "sba_score": sba_scaled,
                    "exam_score": exam_scaled,
                    "total_score": final,
                    "grade": ScoreEngine._grade(final, grade_scales),
                })

                total += final

            result[student.id] = {
                "rows": rows,
                "overall": (total / len(rows)).quantize(TWO) if rows else Decimal("0"),
            }

        return result

    @staticmethod
    def _grade(score, scales):
        for s in scales:
            if s.min_score <= score <= s.max_score:
                return s.grade
        return ""