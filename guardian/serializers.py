from decimal import Decimal

from django.db.models import Sum
from rest_framework import serializers

from academics.models import AcademicYear, Term
from exams.models import StudentReport
from finance.models import FeePayment, InvoiceLineItem, SchoolFeeInvoice
from schools.models import School
from students.models import Student

from .enums import GuardianStudentRelationship
from .models import Guardian, GuardianStudent


def reject_duplicate_students(value):
    student_ids = [item['student'].pk for item in value]
    if len(student_ids) != len(set(student_ids)):
        raise serializers.ValidationError("Each student can only be listed once.")
    return value


class GuardianStudentInputSerializer(serializers.Serializer):
    """A student to link to a guardian, with how they are related."""
    student = serializers.PrimaryKeyRelatedField(queryset=Student.objects.all())
    relationship = serializers.ChoiceField(choices=GuardianStudentRelationship.choices)


class GuardianSerializer(serializers.ModelSerializer):
    students = GuardianStudentInputSerializer(many=True, required=False, write_only=True)
    assigned_students = serializers.SerializerMethodField()

    class Meta:
        model = Guardian
        fields = (
            'id',
            'first_name',
            'last_name',
            'email',
            'phone',
            'address',
            'gender',
            'students',
            'assigned_students',
        )
        read_only_fields = ('id',)

    def get_assigned_students(self, obj):
        return [
            {
                'student': link.student_id,
                'relationship': link.relationship,
            }
            for link in obj.guardian_students.all()
        ]

    def validate_students(self, value):
        return reject_duplicate_students(value)


class GuardianUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Guardian
        fields = (
            'first_name',
            'last_name',
            'email',
            'phone',
            'address',
            'gender',
        )


class GuardianLinkedStudentSerializer(serializers.ModelSerializer):
    """A student linked to a guardian, as shown on the guardian detail."""
    student_code = serializers.CharField(source='student.student_id', read_only=True)
    full_name = serializers.CharField(source='student.full_name', read_only=True)

    class Meta:
        model = GuardianStudent
        fields = ('id', 'student', 'student_code', 'full_name', 'relationship')
        read_only_fields = fields


class GuardianDetailSerializer(serializers.ModelSerializer):
    students = GuardianLinkedStudentSerializer(
        source='guardian_students', many=True, read_only=True
    )

    class Meta:
        model = Guardian
        fields = (
            'id',
            'first_name',
            'last_name',
            'email',
            'phone',
            'address',
            'gender',
            'user_account',
            'students',
            'created_at',
            'updated_at',
        )
        read_only_fields = fields


class GuardianLinkStudentsSerializer(serializers.Serializer):
    students = GuardianStudentInputSerializer(many=True, allow_empty=False)

    def validate_students(self, value):
        return reject_duplicate_students(value)


class GuardianUnlinkStudentsSerializer(serializers.Serializer):
    students = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)

    def validate_students(self, value):
        return list(dict.fromkeys(value))


class GuardianChildSchoolSerializer(serializers.ModelSerializer):
    class Meta:
        model = School
        fields = ('id', 'name')
        read_only_fields = fields


class GuardianChildSerializer(serializers.ModelSerializer):
    """What a guardian sees for each of their linked students."""
    school = GuardianChildSchoolSerializer(read_only=True)
    class_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Student
        fields = ('id', 'student_id', 'full_name', 'profile_photo', 'school', "class_name")
        read_only_fields = fields

    def get_class_name(self, obj):
        enrollment = (
            obj.enrollments.filter(academic_year__is_current=True, is_active=True)
            .select_related('klass', 'academic_year')
            .first()
        )
        if enrollment is None:
            return None
        return enrollment.klass.name

class GuardianChildDetailSerializer(GuardianChildSerializer):
    """One linked student, with the guardian's relationship and class.

    Expects ``context['relationship']`` (from the ``GuardianStudent`` link).
    """
    relationship = serializers.SerializerMethodField()
    current_enrollment = serializers.SerializerMethodField()

    class Meta(GuardianChildSerializer.Meta):
        fields = GuardianChildSerializer.Meta.fields + (
            'gender',
            'status',
            'relationship',
            'current_enrollment',
        )
        read_only_fields = fields

    def get_relationship(self, obj):
        return self.context.get('relationship')

    def get_current_enrollment(self, obj):
        enrollment = (
            obj.enrollments.filter(academic_year__is_current=True, is_active=True)
            .select_related('klass', 'academic_year')
            .first()
        )
        if enrollment is None:
            return None
        return {
            'id': enrollment.id,
            'class_id': enrollment.klass_id,
            'class_name': enrollment.klass.name,
            'academic_year_id': enrollment.academic_year_id,
            'academic_year_name': enrollment.academic_year.name,
        }


class GuardianReportSerializer(serializers.ModelSerializer):
    """A published report card, as listed for a guardian."""
    academic_year_name = serializers.CharField(source='academic_year.name', read_only=True)
    term_name = serializers.CharField(source='term.get_name_display', read_only=True)
    class_name = serializers.CharField(source='student_class.name', read_only=True)

    class Meta:
        model = StudentReport
        fields = (
            'id',
            'academic_year',
            'academic_year_name',
            'term',
            'term_name',
            'class_name',
            'overall_score',
            'overall_position',
            'overall_attendance',
            'total_school_days',
            'teacher_remarks',
            'headteacher_remarks',
            'promoted_to',
            'status',
        )
        read_only_fields = fields


class GuardianInvoiceLineItemSerializer(serializers.ModelSerializer):
    """One fee component on an invoice, with what has been paid against it."""
    fee_component_name = serializers.CharField(source='fee_component.name', read_only=True)
    paid_amount = serializers.SerializerMethodField()
    balance = serializers.SerializerMethodField()

    class Meta:
        model = InvoiceLineItem
        fields = (
            'id',
            'fee_component',
            'fee_component_name',
            'amount',
            'paid_amount',
            'balance',
        )
        read_only_fields = fields

    def _paid_amount(self, obj):
        # ``payment_allocations`` is prefetched by the view; summing in Python
        # avoids one aggregate query per component.
        return sum(
            (allocation.amount for allocation in obj.payment_allocations.all()),
            Decimal('0.00'),
        )

    def get_paid_amount(self, obj):
        return str(self._paid_amount(obj))

    def get_balance(self, obj):
        return str(obj.amount - self._paid_amount(obj))


class GuardianInvoiceListSerializer(serializers.ModelSerializer):
    """An invoice for a linked student, as listed for a guardian."""
    academic_year_name = serializers.CharField(source='academic_year.name', read_only=True)
    term_name = serializers.CharField(source='term.get_name_display', read_only=True)
    klass_name = serializers.CharField(source='klass.name', read_only=True, allow_null=True)
    total_paid = serializers.SerializerMethodField()
    balance_due = serializers.SerializerMethodField()

    class Meta:
        model = SchoolFeeInvoice
        fields = (
            'id',
            'invoice_number',
            'academic_year',
            'academic_year_name',
            'term',
            'term_name',
            'klass',
            'klass_name',
            'total_amount',
            'total_paid',
            'balance_due',
            'status',
            'due_date',
            'is_fully_paid',
            'created_at',
        )
        read_only_fields = fields

    def _paid_total(self, obj):
        # ``paid_total`` is annotated by the service; fall back for callers
        # that serialize an invoice fetched another way.
        annotated = getattr(obj, 'paid_total', None)
        if annotated is not None:
            return annotated
        return obj.payments.aggregate(total=Sum('amount_paid'))['total'] or Decimal('0.00')

    def get_total_paid(self, obj):
        return str(self._paid_total(obj))

    def get_balance_due(self, obj):
        return str(obj.total_amount - self._paid_total(obj))


class GuardianInvoiceDetailSerializer(GuardianInvoiceListSerializer):
    """An invoice with its fee-component breakdown."""
    line_items = GuardianInvoiceLineItemSerializer(many=True, read_only=True)

    class Meta(GuardianInvoiceListSerializer.Meta):
        fields = GuardianInvoiceListSerializer.Meta.fields + ('line_items',)
        read_only_fields = fields


class GuardianInvoicePaymentSerializer(serializers.ModelSerializer):
    """A payment recorded against one of a linked student's invoices."""
    invoice_number = serializers.CharField(source='invoice.invoice_number', read_only=True)
    academic_year_name = serializers.CharField(
        source='invoice.academic_year.name', read_only=True
    )
    term_name = serializers.CharField(
        source='invoice.term.get_name_display', read_only=True
    )
    payment_method_display = serializers.CharField(
        source='get_payment_method_display', read_only=True
    )

    class Meta:
        model = FeePayment
        fields = (
            'id',
            'invoice',
            'invoice_number',
            'academic_year_name',
            'term_name',
            'amount_paid',
            'payment_date',
            'payment_method',
            'payment_method_display',
            'reference_number',
            'created_at',
        )
        read_only_fields = fields


class GuardianTermSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source='get_name_display', read_only=True)

    class Meta:
        model = Term
        fields = ('id', 'name', 'start_date', 'end_date', 'is_current')
        read_only_fields = fields


class GuardianAcademicYearSerializer(serializers.ModelSerializer):
    terms = GuardianTermSerializer(many=True, read_only=True)

    class Meta:
        model = AcademicYear
        fields = ('id', 'name', 'start_date', 'end_date', 'is_current', 'terms')
        read_only_fields = fields


class GuardianStudentSerializer(serializers.ModelSerializer):
    model = GuardianStudent
    fields = (
        'id',
        'school',
        'guardian',
        'student',
        'relationship',
        'created_at',
        'updated_at'
    )

    read_only_fields = (
        "id",
        "school",
        'created_at',
        'updated_at'
    )
