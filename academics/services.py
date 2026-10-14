class AcademicsService:

    @staticmethod
    def _current_term(school):
        from academics.models import Term
        return Term.objects.filter(school=school, is_current=True).first()