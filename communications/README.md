# Communications Module

Send email and SMS notifications to students, staff, and guardians. Supports multiple providers with per-channel default configuration.

---

## 1. Providers

Providers store credentials for email and SMS gateways. Managed by superadmins.

### List Providers
```
GET /api/v1/communications/providers/
```

### Create a Provider
```
POST /api/v1/communications/providers/
Content-Type: application/json

{
  "name": "Primary SMTP",
  "channel": "email",
  "provider_type": "smtp",
  "config": {
    "host": "smtp.gmail.com",
    "port": 587,
    "username": "user@gmail.com",
    "password": "app-password",
    "use_tls": true,
    "from_email": "School <noreply@school.com>"
  },
  "is_default": true
}
```

**Provider Types & Config Fields**

| `provider_type` | Channel | Config Fields |
|---|---|---|
| `smtp` | email | `host`, `port`, `username`, `password`, `use_tls`, `use_ssl`, `from_email` |
| `sendgrid` | email | `api_key`, `from_email` |
| `mailgun` | email | `api_key`, `domain`, `from_email` |
| `twilio` | sms | `account_sid`, `auth_token`, `from_number` |
| `africas_talking` | sms | `api_key`, `username`, `from_number` |

### Update / Delete
```
GET/PUT/DELETE /api/v1/communications/providers/<uuid>/
```

### Test a Provider
```
POST /api/v1/communications/providers/<uuid>/test/
Content-Type: application/json

{
  "recipient": "admin@school.com",
  "subject": "Test",
  "message": "This is a test message."
}
```
The `recipient` should be an email for email providers or a phone number for SMS providers.

---

## 2. Templates

Reusable notification templates with `{{variable}}` placeholders. Managed by school admins.

### List / Create
```
GET /api/v1/communications/templates/
POST /api/v1/communications/templates/
Content-Type: application/json

{
  "name": "Fee Reminder",
  "subject": "Fee Reminder for {{student_name}}",
  "body": "Dear {{guardian_name}},\n\nThis is a reminder that {{student_name}} has an outstanding fee of {{amount}} due on {{due_date}}.",
  "channel": "both",
  "variables": ["student_name", "guardian_name", "amount", "due_date"]
}
```

### Update / Delete
```
GET/PUT/DELETE /api/v1/communications/templates/<uuid>/
```

---

## 3. Notifications

Send and track notifications.

### Send a Notification
```
POST /api/v1/communications/notifications/
Content-Type: application/json
```

**Using a template** — body auto-rendered from template + variables:
```json
{
  "template": "<template-uuid>",
  "title": "Fee Reminder",
  "channel": "email",
  "recipient_type": "all_students",
  "template_variables": {
    "amount": "500.00",
    "due_date": "2026-07-15"
  }
}
```

**Custom message** — no template:
```json
{
  "title": "School Closed Tomorrow",
  "message_body": "Dear parent, school will be closed tomorrow due to a staff training day.",
  "channel": "both",
  "recipient_type": "guardians_of",
  "recipient_ids": ["<student-uuid-1>", "<student-uuid-2>"]
}
```

**Send to a whole class:**
```json
{
  "title": "Sports Day Reminder",
  "message_body": "Sports day is this Friday. Bring your PE kits.",
  "channel": "sms",
  "recipient_type": "class",
  "class_id": "<class-uuid>"
}
```

**Send to specific staff:**
```json
{
  "title": "Staff Meeting",
  "message_body": "Staff meeting at 3pm in the conference room.",
  "channel": "email",
  "recipient_type": "specific_staff",
  "recipient_ids": ["<staff-uuid-1>", "<staff-uuid-2>"]
}
```

### `recipient_type` Options

| Value | Resolves To | Requires |
|---|---|---|
| `all_students` | All active students in the school | — |
| `all_staff` | All active staff in the school | — |
| `specific_students` | Students by UUID | `recipient_ids: [uuids]` |
| `specific_staff` | Staff by UUID | `recipient_ids: [uuids]` |
| `class` | Students enrolled in a class | `class_id: <uuid>` |
| `guardians_of` | Guardians of given students | `recipient_ids: [student-uuids]` |

### List Notifications
```
GET /api/v1/communications/notifications/
```

Filters: `channel`, `recipient_type`, `status`, `sent_from`, `sent_to`, `search` (title/body), `ordering`

### Notification Detail with Delivery Status
```
GET /api/v1/communications/notifications/<uuid>/
```
Returns full notification data plus `recipients` array with per-recipient status (`pending` / `sent` / `failed`) and error messages.

### View Recipients Only
```
GET /api/v1/communications/notifications/<uuid>/recipients/
```

---

## Flow Summary

1. **Configure providers** — Add SMTP/SendGrid/Mailgun for email, Twilio/Africa's Talking for SMS. Mark one per channel as `is_default`.
2. **Create templates** (optional) — Build reusable messages with `{{variable}}` placeholders.
3. **Send notifications** — POST to `notifications/` choosing a recipient type. The system resolves all recipients, picks the default provider for the channel, and attempts delivery to each.
4. **Track delivery** — Check `status` on the notification (sent/partial/failed) and individual recipient records for details.


prompt
Create screens for sending notifications and viewing delivery history.

## Notification List Page (`/communications/notifications`)
- Fetch GET /api/v1/communications/notifications/
- Table columns: Title, Channel (badge), Recipient Type, Status (Sent/Partial/Failed badge), Sent At, Recipient Count
- "Send Notification" button
- Filters: channel, recipient_type, status, date range, search

## Send Notification Form (modal or separate page)
- POST /api/v1/communications/notifications/

### Step 1: Choose Template or Custom
- Toggle: "Use Template" / "Custom Message"
- If template:
  - Select dropdown of templates fetched from GET /api/v1/communications/templates/
  - After selecting, auto-fill title and message_body from template
  - Show variable input fields: for each variable in template.variables, show a text input. As admin fills them, render a live preview of the body.

### Step 2: Compose
- title (text, required)
- message_body (rich textarea, required if no template)
- channel (select: Email, SMS, Both)

### Step 3: Choose Recipients
- recipient_type (select):
  - "All Students" — no extra fields
  - "All Staff" — no extra fields
  - "Specific Students" — shows a multi-select searchable student picker (fetch from GET /api/v1/students/?search=)
  - "Specific Staff" — shows a multi-select searchable staff picker
  - "Whole Class" — shows a class dropdown (fetch from GET /api/v1/academics/classes/)
  - "Guardians of Students" — shows student multi-select (sends to guardians)

### Submit
- On submit, show a loading state since sending may take time
- On success, navigate to the detail page showing delivery results

## Notification Detail Page (`/communications/notifications/<uuid>/`)
- Fetch GET /api/v1/communications/notifications/<uuid>/
- Display:
  - Title, channel badge, status badge, sent timestamp
  - Message body (rendered)
  - Summary cards: Sent count (green), Failed count (red), Pending count (yellow)
- Recipients table below (fetched from GET /api/v1/communications/notifications/<uuid>/recipients/):
  - Columns: Recipient Name, Contact, Status (Sent/Failed badge), Error Message (if failed), Sent At
  - Filterable by status
  - Paginated