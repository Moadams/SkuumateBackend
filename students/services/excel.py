"""Excel handling for class-scoped bulk student import.

``parse_class_excel`` implements the parser behind the class-bulk upload, and
``build_class_bulk_template_workbook`` materialises the matching downloadable
template so the two can never drift apart.
"""
from datetime import datetime

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill


REQUIRED_COLUMNS = ["first_name", "last_name", "date_of_birth", "gender"]
VALID_GENDERS = ["male", "female", "other"]
VALID_RELATIONSHIPS = ["father", "mother", "guardian", "sibling", "other"]
DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"]

TEMPLATE_HEADERS = [
    "first_name",
    "last_name",
    "other_names",
    "date_of_birth",
    "gender",
    "admission_date",
    "address",
    "previous_school",
    "email",
    "phone_number",
    "photo_filename",
    "guardian_first_name",
    "guardian_last_name",
    "guardian_relationship",
    "guardian_phone",
    "guardian_email",
    "guardian_address",
    "guardian_is_primary",
]


def _parse_date(raw):
    """Parse a raw cell into a date, trying the supported formats."""
    if not raw:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(str(raw).strip(), fmt).date()
        except ValueError:
            continue
    return None


def parse_class_excel(file):
    """
    Parses the simplified class-bulk Excel file.
    Returns ``(students_data, row_errors)``.
    """
    try:
        workbook = openpyxl.load_workbook(file, read_only=True, data_only=True)
    except Exception:
        raise ValueError(
            "Could not read the file. Please upload a valid .xlsx Excel file."
        )

    sheet = workbook.active

    headers = []
    for cell in next(sheet.iter_rows(min_row=1, max_row=1)):
        value = str(cell.value).strip().lower() if cell.value else ""
        headers.append(value)

    if not headers:
        raise ValueError("The Excel file appears to be empty.")

    missing = [col for col in REQUIRED_COLUMNS if col not in headers]
    if missing:
        raise ValueError(
            f"Missing required column(s): {', '.join(missing)}. "
            f"Please use the provided template."
        )

    students = []
    row_errors = []

    for row_index, row in enumerate(
        sheet.iter_rows(min_row=2, values_only=True), start=2
    ):
        if all(cell is None or str(cell).strip() == "" for cell in row):
            continue

        row_dict = {
            headers[i]: (
                str(row[i]).strip() if row[i] is not None else ""
            )
            for i in range(min(len(headers), len(row)))
        }

        errors = []
        student = dict(row_dict)

        # Validate required fields
        for col in REQUIRED_COLUMNS:
            if not student.get(col):
                errors.append(f"'{col}' is required.")

        # Validate gender
        gender = student.get("gender", "").lower()
        if gender and gender not in VALID_GENDERS:
            errors.append(
                f"Invalid gender '{gender}'. "
                f"Must be one of: {', '.join(VALID_GENDERS)}."
            )
        else:
            student["gender"] = gender

        # Parse dates
        for date_field in ["date_of_birth", "admission_date"]:
            raw = student.get(date_field, "")
            parsed = _parse_date(raw)
            if raw and parsed is None:
                errors.append(
                    f"Invalid date format for '{date_field}': '{raw}'. "
                    f"Use YYYY-MM-DD."
                )
            else:
                student[date_field] = parsed

        # Clean optional fields
        student.setdefault("other_names", "")
        student.setdefault("address", "")
        student.setdefault("previous_school", "")
        student.setdefault("email", "")
        student.setdefault("phone_number", "")

        # Guardian (single)
        guardian = {}
        g_first_name = student.pop("guardian_first_name", "").strip()
        g_last_name = student.pop("guardian_last_name", "").strip()
        g_relationship = student.pop("guardian_relationship", "").strip().lower()
        g_phone = student.pop("guardian_phone", "").strip()
        g_email = student.pop("guardian_email", "").strip()
        g_address = student.pop("guardian_address", "").strip()
        g_is_primary = student.pop("guardian_is_primary", "").strip().lower() in (
            "true", "1", "yes"
        )

        has_guardian = any([g_first_name, g_last_name, g_relationship, g_phone])
        if has_guardian:
            if not g_first_name:
                errors.append("Guardian 'first_name' is required.")
            if not g_last_name:
                errors.append("Guardian 'last_name' is required.")
            if not g_relationship:
                errors.append("Guardian 'relationship' is required.")
            elif g_relationship not in VALID_RELATIONSHIPS:
                errors.append(
                    f"Invalid guardian relationship '{g_relationship}'. "
                    f"Must be one of: {', '.join(VALID_RELATIONSHIPS)}."
                )
            if not g_phone:
                errors.append("Guardian 'phone' is required.")

            if not errors:
                guardian = {
                    "first_name": g_first_name,
                    "last_name": g_last_name,
                    "relationship": g_relationship,
                    "phone": g_phone,
                    "email": g_email,
                    "address": g_address,
                    "is_primary": g_is_primary,
                }

        student["guardian"] = guardian if guardian else None

        # Photo filename
        photo_filename = student.pop("photo_filename", "").strip()
        student["photo_filename"] = photo_filename if photo_filename else None

        if errors:
            row_errors.append({
                "row": row_index,
                "name": (
                    f"{student.get('first_name', '')} "
                    f"{student.get('last_name', '')}"
                ).strip() or f"Row {row_index}",
                "errors": errors,
            })
        else:
            student["_row"] = row_index
            students.append(student)

    workbook.close()
    return students, row_errors


def build_class_bulk_template_workbook():
    """Builds the class-bulk Excel template workbook."""
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Students"

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(
        start_color="2563EB", end_color="2563EB", fill_type="solid"
    )

    for col_num, header in enumerate(TEMPLATE_HEADERS, start=1):
        cell = sheet.cell(row=1, column=col_num, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
        sheet.column_dimensions[cell.column_letter].width = max(len(header) + 4, 18)

    sample = [
        "Ekow", "Mensah", "Kofi",
        "2010-05-14", "male", "2025-09-01",
        "123 Adum Street, Kumasi", "Good Shepherd Academy",
        "ekow.mensah@school.com", "0244000001",
        "ekow_photo.jpg",
        "Kwame", "Mensah", "father",
        "0244000002", "kwame@email.com", "", "true",
    ]
    for col_num, value in enumerate(sample, start=1):
        cell = sheet.cell(row=2, column=col_num, value=value)
        cell.alignment = Alignment(horizontal="left")

    # Notes sheet
    notes_sheet = workbook.create_sheet(title="Notes")
    notes = [
        ["Field", "Required", "Format / Allowed Values"],
        ["first_name", "Yes", "Text"],
        ["last_name", "Yes", "Text"],
        ["other_names", "No", "Text"],
        ["date_of_birth", "Yes", "YYYY-MM-DD or DD/MM/YYYY"],
        ["gender", "Yes", "male / female / other"],
        ["admission_date", "No", "YYYY-MM-DD or DD/MM/YYYY"],
        ["address", "No", "Text"],
        ["previous_school", "No", "Text"],
        ["email", "No", "Email address"],
        ["phone_number", "No", "Phone number"],
        ["photo_filename", "No", "Filename in the uploaded photos ZIP (e.g., student1.jpg)"],
        ["guardian_first_name", "No", "Text"],
        ["guardian_last_name", "No", "Text"],
        ["guardian_relationship", "No", "father / mother / guardian / sibling / other"],
        ["guardian_phone", "No", "Phone number"],
        ["guardian_email", "No", "Email address"],
        ["guardian_address", "No", "Text"],
        ["guardian_is_primary", "No", "true / false"],
    ]
    notes_header_font = Font(bold=True)
    for row_index, row_data in enumerate(notes, start=1):
        for col_index, value in enumerate(row_data, start=1):
            cell = notes_sheet.cell(row=row_index, column=col_index, value=value)
            if row_index == 1:
                cell.font = notes_header_font
            notes_sheet.column_dimensions[cell.column_letter].width = 40

    return workbook
