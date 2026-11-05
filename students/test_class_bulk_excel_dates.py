from datetime import date, datetime
from io import BytesIO

from django.test import SimpleTestCase
from openpyxl import Workbook

from students.services.excel import parse_class_excel


class ClassBulkExcelDateTests(SimpleTestCase):
    def _parse_row(self, date_of_birth, admission_date):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(
            ["first_name", "last_name", "date_of_birth", "gender", "admission_date"]
        )
        sheet.append(["Richard", "Agyei", date_of_birth, "male", admission_date])

        file = BytesIO()
        workbook.save(file)
        file.seek(0)
        students, errors = parse_class_excel(file)
        return students, errors

    def test_parses_excel_native_datetime_cells(self):
        students, errors = self._parse_row(
            datetime(1999, 12, 12),
            datetime(2025, 9, 12),
        )

        self.assertEqual(errors, [])
        self.assertEqual(students[0]["date_of_birth"], date(1999, 12, 12))
        self.assertEqual(students[0]["admission_date"], date(2025, 9, 12))

    def test_parses_excel_datetime_strings(self):
        students, errors = self._parse_row(
            "1999-12-12 00:00:00",
            "2025-09-12 00:00:00",
        )

        self.assertEqual(errors, [])
        self.assertEqual(students[0]["date_of_birth"], date(1999, 12, 12))
        self.assertEqual(students[0]["admission_date"], date(2025, 9, 12))
