# Finance Module

School fee management, payments, income, and expense tracking for the school management system.

## Models

### FeeComponent
Pre-defined fee items that appear on invoices (e.g., Tuition, Transport, Feeding). Each component belongs to a school and can be deactivated.

### SchoolFeeInvoice
An invoice issued to a student for a specific academic term. Contains line items linking to `FeeComponent` records. Invoice numbers auto-generate as `{SCHOOL_CODE}-INV-{YEAR}-{SEQUENCE}`.

### InvoiceLineItem
Links a `FeeComponent` and amount to an invoice. An invoice cannot have duplicate components.

### FeePayment
A payment recorded against an invoice. Supports multiple payment methods: cash, bank transfer, mobile money, cheque. Automatically updates the invoice status (partially_paid / paid) on save.

### PaymentAllocation
Allocates a payment amount to specific line items. The sum of allocations must equal the payment amount. This enables granular reporting of how much was collected per fee component.

### IncomeType
Categories for non-fee income (e.g., Donations, Grants, Event Fees).

### ExpenseType
Categories for expenses (e.g., Salaries, Utilities, Maintenance).

### OtherIncome
Non-fee income entries linked to an `IncomeType`.

### Expense
Expense entries linked to an `ExpenseType`.

## Key Workflows

### Creating an Invoice
```
POST /api/v1/finance/invoices/
{
  "student": "<uuid>",
  "academic_year": "<uuid>",
  "term": "<uuid>",
  "line_items": [
    { "fee_component": "<uuid>", "amount": "500.00" },
    { "fee_component": "<uuid>", "amount": "300.00" }
  ]
}
```
The `total_amount` is computed from the sum of line items.

### Bulk Invoice Creation
```
POST /api/v1/finance/invoices/bulk/
{
  "students": ["<uuid>", "<uuid>", ...],
  "academic_year": "<uuid>",
  "term": "<uuid>",
  "line_items": [
    { "fee_component": "<uuid>", "amount": "500.00" },
    { "fee_component": "<uuid>", "amount": "300.00" }
  ]
}
```
Skips students who already have an invoice for the same term.

### Recording a Payment with Allocations
```
POST /api/v1/finance/payments/
{
  "invoice": "<uuid>",
  "amount_paid": "500.00",
  "payment_date": "2026-01-15",
  "payment_method": "mobile_money",
  "allocations": [
    { "line_item": "<uuid>", "amount": "300.00" },
    { "line_item": "<uuid>", "amount": "200.00" }
  ]
}
```
The sum of allocations must equal `amount_paid`. Invoice status updates automatically.

## Reports

### Income Statement
```
GET /api/v1/finance/reports/income-statement/
?start_date=2026-01-01&end_date=2026-12-31
&academic_year_id=<uuid>&term_id=<uuid>
```
Returns total fee income, other income, total expenses, and net income.

### Income by Type
```
GET /api/v1/finance/reports/income-by-type/
```
Returns fee income grouped by component and other income grouped by income type.

### Expense by Type
```
GET /api/v1/finance/reports/expense-by-type/
```
Returns expenses grouped by expense type.

## Filters

All list endpoints support `DjangoFilterBackend`, `SearchFilter`, and `OrderingFilter`. Key filterable fields:

| Endpoint | Filters |
|---|---|
| `invoices/` | `student`, `academic_year`, `term`, `klass`, `status`, `is_fully_paid`, `due_date_from`, `due_date_to` |
| `payments/` | `invoice`, `student`, `payment_method`, `payment_date_from`, `payment_date_to` |
| `other-incomes/` | `income_type`, `date_from`, `date_to` |
| `expenses/` | `expense_type`, `date_from`, `date_to` |

## Permissions

All endpoints require `admin` or `finance_manager` role. The `IsAdminOrFinanceManager` permission class combines both roles.
