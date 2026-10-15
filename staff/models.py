from django.db import models
from accounts.models import User
from core.models import TimestampedModel
from staff.enums.employment_type import EmploymentType
from staff.enums.staff_status import StaffStatus
from staff.permission_registry import (
    PERMISSION_CHOICES,
    PERMISSION_KEYS,
)


class PermissionKey(TimestampedModel):
    """
    A single fine-grained permission key (e.g. "students.create").
    The registry table is seeded from staff/permission_registry.py.
    """
    key = models.CharField(max_length=100, unique=True)
    label = models.CharField(max_length=150)
    module = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    is_system = models.BooleanField(
        default=True,
        help_text="System registry keys cannot be deleted.",
    )

    class Meta:
        ordering = ["module", "key"]
        verbose_name = "Permission Key"

    def __str__(self):
        return f"{self.label} ({self.key})"


# ── Built-in position types — cannot be deleted ───────────────────
SYSTEM_POSITIONS = ["administrator", "teacher", "accountant"]


class StaffPosition(TimestampedModel):
    """
    Defines a named bundle of fine-grained permissions.
    Schools can create custom positions on top of the three
    built-in system positions. A staff member's effective access
    is the union of their positions (plus individual grants,
    minus individual revokes).
    """
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="staff_positions",
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    permissions = models.ManyToManyField(
        PermissionKey,
        blank=True,
        related_name="positions",
        help_text="Permission keys granted by this position.",
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
        return self.permissions.filter(key=key).exists()

    def permission_keys(self):
        return set(self.permissions.values_list("key", flat=True))


class StaffProfile(TimestampedModel):
    """
    Extended profile for a staff member.

    Access is fine-grained: effective permissions = (union of the
    staff member's positions, plus individual permission_grants)
    minus individual permission_revokes.
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
        null=True,
        blank=True,
    )
    role = models.CharField(max_length=20, choices=User.Role.choices, default=User.Role.TEACHER)
    positions = models.ManyToManyField(
        StaffPosition,
        blank=True,
        related_name="staff_members",
        help_text="Position bundles assigned to this staff member.",
    )
    permission_grants = models.ManyToManyField(
        PermissionKey,
        blank=True,
        related_name="granted_to_staff",
        help_text="Individual permission keys granted beyond positions.",
    )
    permission_revokes = models.ManyToManyField(
        PermissionKey,
        blank=True,
        related_name="revoked_from_staff",
        help_text="Individual permission keys revoked from this staff member.",
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
    profile_photo = models.ImageField(
        upload_to="staff/photos/",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return f"{self.first_name} {self.last_name} — {self.school.name}"

    def save(self, *args, **kwargs):
        if not self.employee_id:
            self.employee_id = self._generate_employee_id()
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
        employee_id = f"{school_code}-EMP-{year}-{count:04d}"
        while StaffProfile.objects.filter(employee_id=employee_id).exists():
            count += 1
            employee_id = f"{school_code}-EMP-{year}-{count:04d}"
        return f"{school_code}-EMP-{year}-{count:04d}"

    @property
    def full_name(self):
        names = [self.first_name, self.last_name]
        return " ".join(n for n in names if n).strip()

    def effective_permissions(self):
        # Resolve live grants so revocation applies on the next request.
        keys = set()
        for position in self.positions.filter(school_id=self.school_id).prefetch_related("permissions"):
            keys.update(position.permission_keys())
        keys.update(
            self.permission_grants.values_list("key", flat=True)
        )
        keys.difference_update(
            self.permission_revokes.values_list("key", flat=True)
        )

        return keys

    def has_permission(self, key: str) -> bool:
        return key in self.effective_permissions()

    def has_any_permission(self, *keys: str) -> bool:
        return bool(self.effective_permissions() & set(keys))
