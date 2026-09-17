from rest_framework import serializers


class SchoolRelatedFieldsMixin:
    """Scope explicitly listed writable relations before DRF resolves their IDs.

    Nested serializers inherit their root context. Missing school context never
    permits a lookup against all schools.
    """
    school_related_fields = ()
    school_relation_paths = {}

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")
        school = getattr(getattr(request, "user", None), "school", None) if request else self.context.get("school")
        for name in self.school_related_fields:
            field = fields[name]
            if field.read_only:
                continue
            relation = field.child_relation if isinstance(field, serializers.ManyRelatedField) else field
            queryset = relation.queryset
            lookup = self.school_relation_paths.get(name, "school")
            relation.queryset = queryset.filter(**{lookup: school}) if school else queryset.none()
        return fields
