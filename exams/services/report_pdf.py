"""Server-side PDF rendering of a published student report card.

The guardian email attaches this PDF, so it has to be produced without a
browser or system binaries. ReportLab (pure Python) is used because shared
hosting cannot be relied on to provide WeasyPrint's native libraries,
wkhtmltopdf, or headless Chrome.
"""
import io
import logging
import os
from xml.sax.saxutils import escape

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

logger = logging.getLogger(__name__)

BRAND = colors.HexColor("#1e40af")
BRAND_SOFT = colors.HexColor("#dbeafe")
TEXT = colors.HexColor("#111827")
MUTED = colors.HexColor("#6b7280")
LINE = colors.HexColor("#d1d5db")
SURFACE = colors.HexColor("#f3f4f6")


def _text(value, fallback="-"):
    if value is None or value == "":
        return fallback
    return str(value)


def _score(value):
    if value is None or value == "":
        return "-"
    try:
        return f"{value:.2f}"
    except (TypeError, ValueError):
        return str(value)


def _styles():
    base = getSampleStyleSheet()
    return {
        "school": ParagraphStyle(
            "ReportSchool",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=19,
            textColor=BRAND,
        ),
        "school_meta": ParagraphStyle(
            "ReportSchoolMeta",
            parent=base["Normal"],
            fontSize=8.5,
            leading=11,
            textColor=MUTED,
        ),
        "title": ParagraphStyle(
            "ReportTitle",
            parent=base["Title"],
            fontSize=17,
            leading=21,
            textColor=TEXT,
            spaceBefore=6,
            spaceAfter=2,
        ),
        "subtitle": ParagraphStyle(
            "ReportSubtitle",
            parent=base["Normal"],
            alignment=TA_CENTER,
            fontSize=10,
            leading=13,
            textColor=MUTED,
        ),
        "section": ParagraphStyle(
            "ReportSection",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=BRAND,
            spaceBefore=10,
            spaceAfter=4,
        ),
        "label": ParagraphStyle(
            "ReportLabel",
            parent=base["Normal"],
            fontSize=8,
            leading=10,
            textColor=MUTED,
        ),
        "value": ParagraphStyle(
            "ReportValue",
            parent=base["Normal"],
            fontSize=9.5,
            leading=12,
            textColor=TEXT,
        ),
        "cell": ParagraphStyle(
            "ReportCell",
            parent=base["Normal"],
            fontSize=8.5,
            leading=11,
            textColor=TEXT,
        ),
        "cell_right": ParagraphStyle(
            "ReportCellRight",
            parent=base["Normal"],
            alignment=TA_RIGHT,
            fontSize=8.5,
            leading=11,
            textColor=TEXT,
        ),
        "body": ParagraphStyle(
            "ReportBody",
            parent=base["Normal"],
            fontSize=9,
            leading=13,
            textColor=TEXT,
        ),
        "note": ParagraphStyle(
            "ReportNote",
            parent=base["Normal"],
            fontSize=7.5,
            leading=10,
            textColor=MUTED,
        ),
    }


def _p(value, style, fallback="-"):
    """Paragraph with XML-escaped text so names containing ``&`` cannot break it."""
    return Paragraph(escape(_text(value, fallback)), style)


def _logo_flowable(school, max_width=26 * mm):
    """Return the school logo as a flowable, or ``None`` when unavailable."""
    logo = getattr(school, "logo", None)
    if not logo or not getattr(logo, "name", ""):
        return None
    try:
        path = logo.path
    except (ValueError, NotImplementedError):
        return None
    if not path or not os.path.exists(path):
        return None

    try:
        with PILImage.open(path) as image:
            image.load()
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            width, height = image.size
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
        buffer.seek(0)
        ratio = (height / width) if width else 1
        flowable = Image(buffer, width=max_width, height=max_width * ratio)
        flowable.hAlign = "LEFT"
        return flowable
    except Exception:
        # A broken/unreadable logo must never stop a report going out.
        logger.warning("Could not load school logo for report PDF", exc_info=True)
        return None


def _header(report, styles):
    school = report.school
    logo = _logo_flowable(school)

    meta_lines = [
        line
        for line in (
            school.address,
            " · ".join(part for part in (school.city, school.country) if part),
            " · ".join(part for part in (school.phone, school.email) if part),
        )
        if line
    ]

    details = [_p(school.name, styles["school"])]
    for line in meta_lines:
        details.append(_p(line, styles["school_meta"]))
    details_cell = details

    if logo is None:
        table = Table([[details_cell]], colWidths=[170 * mm])
    else:
        table = Table([[logo, details_cell]], colWidths=[32 * mm, 138 * mm])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return table


def _student_block(report, styles):
    rows = [
        (
            "Student",
            report.student.full_name,
            "Student ID",
            report.student.student_id,
        ),
        (
            "Class",
            report.student_class.name,
            "Academic Year",
            report.academic_year.name,
        ),
        (
            "Term",
            report.term.get_name_display(),
            "Position in Class",
            _text(report.overall_position, "-"),
        ),
        (
            "Attendance",
            f"{report.overall_attendance}/{report.total_school_days} days",
            "Promoted To",
            _text(report.promoted_to, "-"),
        ),
    ]

    data = []
    for left_label, left_value, right_label, right_value in rows:
        data.append(
            [
                _p(left_label, styles["label"]),
                _p(left_value, styles["value"]),
                _p(right_label, styles["label"]),
                _p(right_value, styles["value"]),
            ]
        )

    table = Table(data, colWidths=[24 * mm, 61 * mm, 27 * mm, 58 * mm])
    table.setStyle(
        TableStyle(
            [
                ("SPAN", (0, 0), (0, 0)),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (-1, -1), SURFACE),
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _subject_block(report, styles):
    scores = list(report.subject_scores.all())
    if not scores:
        return _p("No subject scores recorded for this report.", styles["body"])

    header = [
        Paragraph("<b>Subject</b>", styles["cell"]),
        Paragraph("<b>SBA</b>", styles["cell_right"]),
        Paragraph("<b>Exam</b>", styles["cell_right"]),
        Paragraph("<b>Total</b>", styles["cell_right"]),
        Paragraph("<b>Grade</b>", styles["cell_right"]),
        Paragraph("<b>Rank</b>", styles["cell_right"]),
    ]
    data = [header]
    for score in scores:
        data.append(
            [
                _p(score.subject.name, styles["cell"]),
                _p(_score(score.sba_score), styles["cell_right"]),
                _p(_score(score.exam_score), styles["cell_right"]),
                _p(_score(score.total_score), styles["cell_right"]),
                _p(score.grade, styles["cell_right"]),
                _p(score.rank, styles["cell_right"]),
            ]
        )

    table = Table(data, colWidths=[72 * mm, 18 * mm, 18 * mm, 18 * mm, 18 * mm, 16 * mm])
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
    ]
    for row_index in range(1, len(data)):
        if row_index % 2 == 0:
            style.append(("BACKGROUND", (0, row_index), (-1, row_index), SURFACE))
    table.setStyle(TableStyle(style))
    return table


def _summary_block(report, styles):
    overall = _score(report.overall_score)
    position = _text(report.overall_position, "-")
    attendance = f"{report.overall_attendance}/{report.total_school_days}"
    data = [
        [
            _p("OVERALL SCORE", styles["label"]),
            _p("POSITION", styles["label"]),
            _p("ATTENDANCE", styles["label"]),
        ],
        [
            _p(f"{overall}%", styles["value"]),
            _p(position, styles["value"]),
            _p(f"{attendance} days", styles["value"]),
        ],
    ]
    table = Table(data, colWidths=[56 * mm, 56 * mm, 58 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), BRAND_SOFT),
                ("BOX", (0, 0), (-1, -1), 0.5, BRAND),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, BRAND),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _remarks_block(report, styles):
    blocks = []
    remarks = [
        ("Class Teacher's Remarks", report.teacher_remarks, report.teacher),
        ("Headteacher's Remarks", report.headteacher_remarks, report.headteacher),
    ]
    for title, remark, author in remarks:
        content = [
            _p(title, styles["section"]),
            _p(remark or "No remarks recorded.", styles["body"]),
        ]
        if author:
            content.append(_p(f"— {author}", styles["note"]))
        blocks.append(KeepTogether(content))
    return blocks


def _signature_block(styles):
    data = [
        [
            _p("Class Teacher's Signature", styles["note"]),
            _p("Headteacher's Signature / Stamp", styles["note"]),
        ],
        [Paragraph("<br/><br/>__________________________", styles["body"]),
         Paragraph("<br/><br/>__________________________", styles["body"])],
    ]
    table = Table(data, colWidths=[85 * mm, 85 * mm])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return table


def _page_footer(school_name):
    def draw(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.5)
        canvas.line(15 * mm, 13 * mm, A4[0] - 15 * mm, 13 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(15 * mm, 9 * mm, f"{school_name} · Report Card")
        canvas.drawRightString(A4[0] - 15 * mm, 9 * mm, f"Page {doc.page}")
        canvas.restoreState()

    return draw


def build_report_pdf(report) -> io.BytesIO:
    """Render one ``StudentReport`` to an in-memory PDF."""
    styles = _styles()
    story = [
        _header(report, styles),
        Spacer(1, 4 * mm),
        Paragraph("TERMINAL REPORT CARD", styles["title"]),
        Paragraph(
            escape(
                f"{report.term.get_name_display()} · {report.academic_year.name}"
            ),
            styles["subtitle"],
        ),
        Spacer(1, 4 * mm),
        _student_block(report, styles),
        Paragraph("SUBJECT PERFORMANCE", styles["section"]),
        _subject_block(report, styles),
        Paragraph("SUMMARY", styles["section"]),
        _summary_block(report, styles),
    ]
    story.extend(_remarks_block(report, styles))
    story.extend(
        [
            Spacer(1, 6 * mm),
            _signature_block(styles),
            Spacer(1, 4 * mm),
            _p(
                "This report card was generated by SkuuMate.",
                styles["note"],
            ),
        ]
    )

    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=14 * mm,
        bottomMargin=17 * mm,
        title=f"{report.student.full_name} - {report.term.get_name_display()} Report",
        author=report.school.name,
        subject="Student report card",
    )
    footer = _page_footer(report.school.name)
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    buffer.seek(0)
    return buffer
