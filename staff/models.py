from django.db import models
from core.models import TimestampedModel
from staff.enums.employment_type import EmploymentType
from staff.enums.staff_status import StaffStatus


# ── Permission Registry ───────────────────────────────────────────
# The single source of truth for all permission keys in the system.
# When adding new modules, add keys here first.

PERMISSION_CHOICES = [
    # ── Students ──────────────────────────────────────────────────
    ("students.view",           "View Students"),
    ("students.create",         "Create Students"),
    ("students.edit",           "Edit Students"),
    ("students.delete",         "Delete/Withdraw Students"),
    ("students.export",         "Export Students"),

    # ── Attendance ────────────────────────────────────────────────
    ("attendance.view",         "View Attendance"),
    ("attendance.mark",         "Mark Attendance"),
    ("attendance.edit",         "Edit Attendance Records"),
    ("attendance.export",       "Export Attendance"),

    # ── Exams & Results ───────────────────────────────────────────
    ("exams.view",              "View Exams & Results"),
    ("exams.manage",            "Manage Exams"),
    ("exams.enter_scores",      "Enter Scores"),
    ("exams.export",            "Export Results"),

    # ── Finance ───────────────────────────────────────────────────
    ("finance.view",            "View Finance"),
    ("finance.manage_fees",     "Manage Fee Structures"),
    ("finance.record_payments", "Record Payments"),
    ("finance.export",          "Export Finance Reports"),

    # ── Staff ─────────────────────────────────────────────────────
    ("staff.view",              "View Staff"),
    ("staff.manage",            "Manage Staff"),

    # ── Academics ─────────────────────────────────────────────────
    ("academics.view",          "View Academic Structure"),
    ("academics.manage",        "Manage Academic Structure"),

    # ── Reports ───────────────────────────────────────────────────
    ("reports.view",            "View Reports"),
    ("reports.export",          "Export Reports"),

    # ── Announcements ─────────────────────────────────────────────
    ("announcements.view",      "View Announcements"),
    ("announcements.manage",    "Manage Announcements"),

    # ── Settings ──────────────────────────────────────────────────
    ("settings.view",           "View School Settings"),
    ("settings.manage",         "Manage School Settings"),

    # ── Dashboard ─────────────────────────────────────────────────
    ("dashboard.admin",         "Access Admin Dashboard"),
    ("dashboard.teacher",       "Access Teacher Dashboard"),
    ("dashboard.finance",       "Access Finance Dashboard"),
]

PERMISSION_KEYS = [key for key, _ in PERMISSION_CHOICES]

# ── Built-in position types — cannot be deleted ───────────────────
SYSTEM_POSITIONS = ["administrator", "teacher", "accountant"]


class StaffPosition(TimestampedModel):
    """
    Defines a staff role and its permissions.
    Schools can create custom positions on top of the
    three built-in system positions.
    """
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="staff_positions",
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    permissions = models.JSONField(
        default=list,
        help_text="List of permission keys assigned to this position.",
    )
    is_system = models.BooleanField(
        default=False,
        help_text="System positions cannot be deleted.",
    )

    class Meta:
        ordering = ["-is_system", "name"]
        unique_together = ["school", "name"]

    def __str__(self):
        return f"{self.name} — {self.school.name}"

    def has_permission(self, key: str) -> bool:
        return key in (self.permissions or [])

    def clean_permissions(self):
        """Removes any invalid permission keys."""
        self.permissions = [
            p for p in self.permissions if p in PERMISSION_KEYS
        ]


class StaffProfile(TimestampedModel):
    """
    Extended profile for a staff member.
    Links a User to one or more StaffPositions and stores
    employment details.
    """
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="staff_profiles",
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    user = models.OneToOneField(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="staff_profile",
    )
    positions = models.ManyToManyField(
        StaffPosition,
        related_name="staff_members",
        blank=True,
    )
    employee_id = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
    )
    date_joined = models.DateField()
    employment_type = models.CharField(
        max_length=20,
        choices=EmploymentType.choices,
        default=EmploymentType.FULL_TIME,
    )
    status = models.CharField(
        max_length=20,
        choices=StaffStatus.choices,
        default=StaffStatus.ACTIVE,
    )
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    emergency_contact_name = models.CharField(
        max_length=100, blank=True
    )
    emergency_contact_phone = models.CharField(
        max_length=20, blank=True
    )
    profile_photo = models.ImageField(
        upload_to="staff/photos/",
        null=True,
        blank=True,
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return f"{self.first_name} {self.last_name} — {self.school.name}"

    def save(self, *args, **kwargs):
        if not self.employee_id:
            self.employee_id = self._generate_employee_id()
        if self.first_name != self.user.first_name or self.last_name != self.user.last_name or self.email != self.user.email:
            # Keep User's name in sync with StaffProfile
            self.user.first_name = self.first_name
            self.user.last_name = self.last_name
            self.user.email = self.email    
            self.user.save()
        super().save(*args, **kwargs)

    def _generate_employee_id(self):
        import datetime
        year = datetime.date.today().year
        school_code = self.school.school_code if self.school.school_code else "SCH"
        count = StaffProfile.objects.filter(school=self.school).count() + 1
        if self.date_joined:
            year = self.date_joined.year
            count = StaffProfile.objects.filter(
                school=self.school,
                date_joined__year=year
            ).count() + 1
        return f"{school_code}-EMP-{year}-{count:04d}"

    @property
    def full_name(self):
        names = [self.first_name, self.last_name]
        return " ".join(n for n in names if n).strip()


    @property
    def all_permissions(self):
        """
        Aggregates permissions from all assigned positions.
        Returns a flat deduplicated list.
        """
        perms = set()
        for position in self.positions.all():
            perms.update(position.permissions or [])
        return list(perms)

    def has_permission(self, key: str) -> bool:
        return key in self.all_permissions