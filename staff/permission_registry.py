"""Bootstrap definition of every permission key in the system.

This is the seed source for the `staff.PermissionKey` registry table.
Once seeded, the database table is the runtime source of truth for labels,
module grouping, and validation. New permissions are added here first,
then refreshed with `python manage.py seed_permissions`.
"""

PERMISSION_DEFS = [
    # ── Students ──────────────────────────────────────────────────
    {
        "key": "students.view",
        "module": "Students",
        "label": "View Students",
        "description": "View student records.",
    },
    {
        "key": "students.create",
        "module": "Students",
        "label": "Create Students",
        "description": "Register new students.",
    },
    {
        "key": "students.edit",
        "module": "Students",
        "label": "Edit Students",
        "description": "Update student details.",
    },
    {
        "key": "students.delete",
        "module": "Students",
        "label": "Delete/Withdraw Students",
        "description": "Delete or withdraw students.",
    },
    {
        "key": "students.export",
        "module": "Students",
        "label": "Export Students",
        "description": "Export student records.",
    },

    # ── Attendance ────────────────────────────────────────────────
    {
        "key": "attendance.view",
        "module": "Attendance",
        "label": "View Attendance",
        "description": "View attendance records.",
    },
    {
        "key": "attendance.mark",
        "module": "Attendance",
        "label": "Mark Attendance",
        "description": "Mark attendance for assigned classes.",
    },
    {
        "key": "attendance.edit",
        "module": "Attendance",
        "label": "Edit Attendance Records",
        "description": "Edit existing attendance records.",
    },
    {
        "key": "attendance.export",
        "module": "Attendance",
        "label": "Export Attendance",
        "description": "Export attendance records.",
    },

    # ── Exams & Results ───────────────────────────────────────────
    {
        "key": "exams.view",
        "module": "Exams",
        "label": "View Exams & Results",
        "description": "View exams and student results.",
    },
    {
        "key": "exams.manage",
        "module": "Exams",
        "label": "Manage Exams",
        "description": "Create and manage exams and assessments.",
    },
    {
        "key": "exams.enter_scores",
        "module": "Exams",
        "label": "Enter Scores",
        "description": "Enter scores for assigned subjects.",
    },
    {
        "key": "exams.approve_scores",
        "module": "Exams",
        "label": "Approve Scores",
        "description": "Approve submitted scores for reporting.",
    },
    {
        "key": "exams.export",
        "module": "Exams",
        "label": "Export Results",
        "description": "Export exam results.",
    },

    # ── Finance ───────────────────────────────────────────────────
    {
        "key": "finance.view",
        "module": "Finance",
        "label": "View Finance",
        "description": "View financial data.",
    },
    {
        "key": "finance.manage_fees",
        "module": "Finance",
        "label": "Manage Fee Structures",
        "description": "Create and manage fee structures.",
    },
    {
        "key": "finance.record_payments",
        "module": "Finance",
        "label": "Record Payments",
        "description": "Record and manage payments.",
    },
    {
        "key": "finance.export",
        "module": "Finance",
        "label": "Export Finance Reports",
        "description": "Export financial reports.",
    },

    # ── Staff ─────────────────────────────────────────────────────
    {
        "key": "staff.view",
        "module": "Staff",
        "label": "View Staff",
        "description": "View staff records.",
    },
    {
        "key": "staff.manage",
        "module": "Staff",
        "label": "Manage Staff",
        "description": "Create, update and deactivate staff.",
    },
    {
        "key": "staff.assign_positions",
        "module": "Staff",
        "label": "Assign Positions & Permissions",
        "description": "Assign staff positions and individual permissions.",
    },

    # ── Academics ─────────────────────────────────────────────────
    {
        "key": "academics.view",
        "module": "Academics",
        "label": "View Academic Structure",
        "description": "View subjects, classes and years.",
    },
    {
        "key": "academics.manage",
        "module": "Academics",
        "label": "Manage Academic Structure",
        "description": "Create and manage academic structure.",
    },
    {
        "key": "class.teach",
        "module": "Academics",
        "label": "Teach Assigned Classes",
        "description": "Access and manage own assigned classes/subjects.",
    },

    # ── Reports ───────────────────────────────────────────────────
    {
        "key": "reports.view",
        "module": "Reports",
        "label": "View Reports",
        "description": "View student report cards.",
    },
    {
        "key": "reports.approve",
        "module": "Reports",
        "label": "Approve Reports",
        "description": "Approve finalised report cards.",
    },
    {
        "key": "reports.export",
        "module": "Reports",
        "label": "Export Reports",
        "description": "Export report cards.",
    },

    # ── Announcements ─────────────────────────────────────────────
    {
        "key": "announcements.view",
        "module": "Announcements",
        "label": "View Announcements",
        "description": "View announcements.",
    },
    {
        "key": "announcements.manage",
        "module": "Announcements",
        "label": "Manage Announcements",
        "description": "Create and manage announcements.",
    },

    # ── Admissions ────────────────────────────────────────────────
    {
        "key": "admissions.view",
        "module": "Admissions",
        "label": "View Admissions",
        "description": "View admission applications.",
    },
    {
        "key": "admissions.manage",
        "module": "Admissions",
        "label": "Manage Admissions",
        "description": "Process and manage admissions.",
    },

    # ── Settings ──────────────────────────────────────────────────
    {
        "key": "settings.view",
        "module": "Settings",
        "label": "View School Settings",
        "description": "View school settings.",
    },
    {
        "key": "settings.manage",
        "module": "Settings",
        "label": "Manage School Settings",
        "description": "Update school settings.",
    },

    # ── Dashboard ─────────────────────────────────────────────────
    {
        "key": "dashboard.admin",
        "module": "Dashboard",
        "label": "Access Admin Dashboard",
        "description": "Access the admin dashboard.",
    },
    {
        "key": "dashboard.teacher",
        "module": "Dashboard",
        "label": "Access Teacher Dashboard",
        "description": "Access the teacher dashboard.",
    },
    {
        "key": "dashboard.finance",
        "module": "Dashboard",
        "label": "Access Finance Dashboard",
        "description": "Access the finance dashboard.",
    },

    # ── School ────────────────────────────────────────────────────
    {
        "key": "school.manage",
        "module": "School",
        "label": "Manage School Operations",
        "description": "Full management of school operations. Replaces administrator role.",
    },
    {
        "key": "school.subscriptions",
        "module": "School",
        "label": "View Subscription & Billing",
        "description": "View the school's subscription and billing details.",
    },
]

PERMISSION_KEYS = [d["key"] for d in PERMISSION_DEFS]

PERMISSION_CHOICES = [
    (d["key"], d["label"]) for d in PERMISSION_DEFS
]