# SkuuMate Features - Comparison: Requirements vs Implementation

This document lists all features from the SkuuMate requirements (PDF) and compares them against what is actually implemented in the backend application.

## 1. Core Student & Academic Features

| Feature | Required (PDF) | Status in Codebase | Evidence | Notes |
|---|---|---|---|---|
| Student enrollment & digital records | All tiers (Lite+) | **Built** | `students/models.py` (Student, Enrollment), `students/views.py` (StudentListCreateView/Detail), `students/urls.py` | Full CRUD, bulk import, class enrollments |
| Student ID management | All tiers | **Partial** | `students/models.py:60-98` - auto-generated `student_id` format `{school_prefix}-{year}-{count:04d}`. Search supports `student_id` in `students/views.py:876-883` | No ID card generation, QR codes, or barcode functionality implemented |
| Classes, subjects & timetable setup | All tiers (Lite+) | **Built** | `academics/models.py` (Class, Subject, ClassSubject, TimeTableSlot), `academics/views/views.py`, `academics/serializers.py:1101-1185` | TimeTableSlot exists with overlap validation, CRUD per class |
| Academic year & term management | All tiers | **Built** | `academics/models.py:4-90` (AcademicYear, Term) - single current year/term per school, date ranges | Fully implemented |
| Score entry | All tiers (Lite+) | **Built** | `exams/models.py` (StudentMark), `exams/views.py` (bulk marks, list by class/subject), `exams/urls.py` | Bulk and individual score entry supported |
| Automated report cards | All tiers (Lite+) | **Built** | `exams/models.py` (StudentReport, StudentReportSubjectScore), `exams/services/report_generation_service.py`, rank/score engines | Generate, view, publish, add teacher/headteacher remarks |
| Basic broadsheet generation | Lite | **Not built** | No "broadsheet" references in codebase | No dedicated broadsheet view/API/service |
| Full broadsheet & performance trends | Advantage+ | **Not built** | No broadsheet/trends implementation | Data exists (marks/reports) but no broadsheet output |
| Term-to-term academic comparison | Advantage+ | **Not built** | No comparison logic/API found | Not implemented |
| Academic performance analytics | All tiers (analytics) | **Partial** | `exams/rank_engine.py`, `score_engine.py`, `report_generation_service.py` compute ranks/scores; dashboard has various views | No time-series performance trends API exposed |

---

## 2. Attendance

| Feature | Required (PDF) | Status in Codebase | Evidence | Notes |
|---|---|---|---|---|
| Student attendance | All tiers (Lite - listed as separate item) | **Built** | `attendance/models.py` (Attendance, AttendanceSummary), `attendance/views.py`, `attendance/urls.py` | Bulk mark, class sheets, reports, summaries. Unique per student/date |
| Staff attendance | Not explicitly listed in PDF feature list | **Not built** | No `StaffAttendance`/TeacherAttendance models anywhere; only student attendance in attendance app | Staff attendance not implemented as separate feature |

---

## 3. Finance & Billing

| Feature | Required (PDF) | Status in Codebase | Evidence | Notes |
|---|---|---|---|---|
| Fee billing, payment tracking | All tiers (Lite+) | **Built** | `finance/models.py` (SchoolFeeInvoice, InvoiceLineItem, FeePayment, PaymentAllocation), `finance/views.py`, `finance/urls.py` | Auto invoice numbering, status tracking (draft/issued/partially_paid/paid/overdue), payment allocations, auto status sync |
| Fee receipts | Lite+ | **Not built** | Expense has `receipt_number` only (`finance/models.py:202`); no FeeReceipt model, no receipt generation/printing endpoints/templates | Receipt generation/printing for fees not implemented |
| Debtors list & basic finance summary | Lite+ | **Not built** | Data supports (invoices with overdue/partially_paid/issued and `is_fully_paid`); no dedicated "debtors" view/URL found | Can be derived by filtering, but no explicit API/view implemented |
| Basic finance summary | Lite | **Built** | `dashboard/views.py:87-285` (FinanceManagerDashboardView) provides outstanding receivables, collected this term, invoice status breakdown; `finance/views.py` FinancialOverviewView | Basic summaries available |
| Income, expense & revenue tracking | Advantage+ | **Built** | `finance/models.py` (IncomeType, OtherIncome, ExpenseType, Expense), CRUD views and URLs | Full tracking implemented |
| Advanced finance dashboard & analytics | Advantage+ | **Built** | `dashboard/views.py` FinanceManagerDashboardView with revenue/expenses (this/last month), net income, charts-style breakdowns, recent payments/expenses | Implemented |
| Finance analytics | Advantage+ | **Built** | `dashboard/views.py` + `finance/views.py` report views (FinancialOverviewView, IncomeStatementView, IncomeByTypeReportView, ExpenseByTypeReportView) | Analytics available |
| Financial reports | Advantage+ | **Built** | `finance/urls.py:72-79` has report endpoints; views implement income statement, income-by-type, expense-by-type | Implemented |

---

## 4. Communications & Notifications

| Feature | Required (PDF) | Status in Codebase | Evidence | Notes |
|---|---|---|---|---|
| Parent communication tools | All tiers | **Built** | `communications/models.py` (Notification with recipient types including `GUARDIANS_OF`, `ALL_STUDENTS`, `SPECIFIC_STUDENTS`), views/serializers/urls | Can target parents/guardians; full notification system |
| SMS alerts (attendance & fee reminders) | Lite+ | **Partial** | `communications/services/sms_service.py` (SMSService), providers in communications models, test send endpoints | Service exists; **no automatic triggers** (no signals for attendance/fees). Manual sending only |
| Announcement broadcast | Advantage+ | **Built** | `communications/models.py` (Notification) - can broadcast to classes/all; views for creating/sending notifications | Broadcast capability via Notification system |
| Extended SMS alerts | Advantage+ | **Partial** | SMS infrastructure exists; no separate "extended" quota/tiering logic or channel expansion beyond providers | Infrastructure there, quota logic not obvious as separate feature |

---

## 5. Portals & Access Control

| Feature | Required (PDF) | Status in Codebase | Evidence | Notes |
|---|---|---|---|---|
| Admin & teacher portal access | Lite+ | **Built** | Role-based access via `accounts.User.Role` (ADMIN, TEACHER, etc.) and staff permissions; enforced by roles/permissions, not just package-gated | Role-based enforcement implemented |
| Student portal access (results & timetable view) | Advantage+ | **Not built** | No student portal routes/views; no student-scoped portal endpoints. `accounts.User.Role.STUDENT` exists but no portal module | Not implemented |
| Parent portal access | Future/Enterprise mentions? Not listed as implemented | **Not built** | No guardian/parent portal endpoints; `Guardian` model exists in students, communications can target guardians | Only targeting/messaging exists, no portal |
| User access control / Role-based access | All tiers | **Built** | `staff/permission_registry.py` (comprehensive PERMISSION_DEFS), `staff/models.py` (PermissionKey, StaffPosition, StaffProfile with grants/revokes), `platform_rbac` app for platform-level roles | Robust RBAC at school and platform levels |
| Activity logs & role-based access (as listed) | Advantage+ | **Built** | `core/models.py` (AuditLog), `core/mixins.py` (AuditLogMixin auto-logs CRUD), `core/views.py` (AuditLogListView) | Activity logging fully implemented |

---

## 6. Reporting, Branding & Exports

| Feature | Required (PDF) | Status in Codebase | Evidence | Notes |
|---|---|---|---|---|
| Branded report exports | Advantage+ | **Not built** | `core/mixins.py:139-180` (ExportMixin.export) returns JSON only (`ApiResponse.success` with serialized data). No PDF/CSV generation (no reportlab/weasyprint/xlsxwriter) | Exports are JSON only, not branded files |
| Financial reports | Advantage+ | **Built** | As above - income statement, by type reports in finance views/urls | Implemented |
| Custom financial report formats | Enterprise+ | **Partial** | Fixed report types only; no flexible custom report builder/designer | Basic reports exist, no custom format builder |
| Custom academic report formats | Enterprise+ | **Partial** | Report card generation via ReportScheme/ReportGenerationService; no user-configurable template designer | Template customization not present |
| Customized report card design (logo, grading style, layout) | Enterprise+ | **Partial** | `exams/models.py` (ReportScheme with SBA/exam scaling, components) configures grading weights; no visual/template layout design beyond scheme | Limited to scheme config, no full design templates |
| School branding across the system (colors, logo, export headers) | Enterprise+ | **Partial** | `schools/models.py` has `logo` (ImageField) only; no color/theme/branding fields (primary/secondary colors, theme, export headers) | Only logo is stored; no theming/colors |

---

## 7. Advanced Features (Enterprise)

| Feature | Required (PDF) | Status in Codebase | Evidence | Notes |
|---|---|---|---|---|
| Advanced institutional analytics dashboard | Enterprise+ | **Partial** | `dashboard/views.py` has multiple dashboards (superadmin, admin, finance, teacher); no dedicated cross-school institutional analytics beyond what exists | Some analytics exist, not explicitly "advanced institutional analytics" as described |
| Multi-year academic & financial tracking | Enterprise+ | **Built** | AcademicYear/Term + enrollments/marks/reports link to years; finance records have dates/timestamps; queries can span periods | Data model supports multi-year tracking |
| Hierarchical admin & department-level access control | Enterprise+ | **Not built** | No `Department` model anywhere in codebase; RBAC is role/permission based, not departmental hierarchy | Not implemented |
| Data migration & dedicated onboarding sessions | Enterprise+ (service deliverable) | **Partial** | `schools/services/onboarding.py` (OnboardingService), bulk import (StudentBulkCreateView/ClassBulkStudentsView) | Some onboarding/data import tools exist; "dedicated sessions" is service deliverable (human) |
| Priority SLA support & operational review sessions | Enterprise+ (service deliverable) | **Not built** | No SLA/ticketing/priority support models/views; only mentioned as feature codes conceptually | Not implemented in code |

---

## 8. Technical/Infrastructure

| Feature | Required (PDF) | Status in Codebase | Evidence | Notes |
|---|---|---|---|---|
| Web-based platform / API | All tiers | **Built** | Django REST Framework, settings with DRF, comprehensive API endpoints across all apps; URLs mounted at `/api/v1/` | Fully web-based REST API |
| Secure cloud storage | All tiers | **Not built** | No S3/AWS/storage backend config in settings; uses default filesystem (MEDIA_ROOT/STATIC_ROOT). No backup code | Default local storage only |
| Announcements & events | All tiers | **Built** | `communications/models.py` (Notification) serves as announcements/notices to targeted audiences | Implemented via notification system |
| GES-style reports/results | All tiers | **Built** | Report generation with schemes, grades, ranks via exams app (report cards); terminology matches GES-style structure | Implemented |

---

## 9. Subscription/Feature Entitlement System

| Feature | Required (PDF) | Status in Codebase | Evidence | Notes |
|---|---|---|---|---|
| Feature catalog & entitlements | All tiers | **Built** | `subscriptions/feature_catalog.py` (all feature codes declared), `subscriptions/models.py`, `subscriptions/sync.py`, `subscriptions/permissions.py` (feature gates), `subscriptions/utils.py` | Feature codes match PDF spec structure; feature gating system implemented |

---

## Summary

### Implemented (Built)
- Student enrollment/records, classes/subjects/timetable, academic year/term management
- Score entry, automated report cards  
- Attendance (student only)
- Fee billing, payment tracking, income/expense tracking, finance reports, finance dashboards/analytics
- Parent communications (notifications), announcement broadcast, SMS service infrastructure
- RBAC (school + platform), activity/audit logs
- Multi-year data model support
- Web-based REST API, subscriptions/feature entitlements

### Partially Implemented
- Student ID generation (auto) but no card/QR/barcode generation
- SMS alerts exist but no automatic triggers (attendance/fee reminders need automation)
- Finance reports exist but custom formats limited
- Report card customization limited to ReportScheme (no templates)
- School branding only has logo (no colors/themes)
- Onboarding has bulk import tools
- Export returns JSON only

### Not Implemented (Missing)
- **Broadsheets** (basic and full) - no implementation
- **Term-to-term academic comparison** - no implementation  
- **Debtors list** (dedicated view) - data model supports but no explicit endpoint
- **Fee receipts** (generation/printing) - not implemented
- **Student portal** (results/timetable for students) - not implemented
- **Branded PDF/CSV exports** - ExportMixin returns JSON only
- **School branding colors/themes** - only logo exists
- **Department-level/hierarchical access control** - no Department model
- **Staff attendance** - not implemented
- **Cloud storage/backups** - filesystem only
- **Priority SLA support** - no implementation (service deliverable only conceptually)
- **Custom report template designers** for financial/academic reports
- **Advanced institutional analytics** (as described) - partial only
- **Performance trends API** (time-series) - partial data model only

### Priority Gaps vs PDF Requirements
According to the PDF's phased plan in the docs, the key sold-but-not-built items include: debtors list, fee receipts, broadsheets (basic/full), term comparison, branded exports, school branding beyond logo, report card templates, student portal, department access control, advanced analytics, multi-year tracking views, custom report builders, automatic SMS triggers. These align with what's missing above.

The backend has a solid foundation (models, RBAC, feature gating, core domain logic). The main gaps are in: export generation (PDF/CSV), reporting UI outputs (broadsheets/comparisons/trends), student portal endpoints, staff attendance, and some branding/dept features.