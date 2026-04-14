from django.db import models
from core.models import TimestampedModel


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
    class EmploymentType(models.TextChoices):
        FULL_TIME = "full_time", "Full Time"
        PART_TIME = "part_time", "Part Time"
        CONTRACT = "contract", "Contract"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ON_LEAVE = "on_leave", "On Leave"
        SUSPENDED = "suspended", "Suspended"
        TERMINATED = "terminated", "Terminated"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="staff_profiles",
    )
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
        choices=Status.choices,
        default=Status.ACTIVE,
    )
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
        ordering = ["user__last_name", "user__first_name"]

    def __str__(self):
        return f"{self.user.full_name} — {self.school.name}"

    def save(self, *args, **kwargs):
        if not self.employee_id:
            self.employee_id = self._generate_employee_id()
        super().save(*args, **kwargs)

    def _generate_employee_id(self):
        import datetime
        year = datetime.date.today().year
        prefix = self.school.name[:3].upper()
        count = StaffProfile.objects.filter(
            school=self.school
        ).count() + 1
        return f"{prefix}-EMP-{year}-{count:03d}"

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