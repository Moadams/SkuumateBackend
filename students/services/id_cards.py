"""Student ID card rendering.

Cards are drawn with Pillow (no external layout engine) and assembled into a
print-ready PDF. Each student produces two pages — a front and a back — sized to
the ISO/IEC 7810 ID-1 (CR80) format so the PDF can be sent straight to a card
printer. The QR code on the back encodes the student's raw ``student_id``; a
public ``student-verify`` endpoint turns that string back into the displayed
record.

The renderer only needs Pillow and ``qrcode`` (Pillow draws text with a bundled
scalable font, so no font files ship with the project).
"""
from __future__ import annotations

import io
import os

import qrcode
from PIL import Image, ImageDraw, ImageFont

# ── Geometry ──────────────────────────────────────────────────────────
# ISO/IEC 7810 ID-1 (CR80) card, rendered at 300 DPI for crisp printing.
DPI = 300
CARD_WIDTH_MM = 85.6
CARD_HEIGHT_MM = 53.98
CARD_SIZE = (
    round(CARD_WIDTH_MM / 25.4 * DPI),   # 1011 px
    round(CARD_HEIGHT_MM / 25.4 * DPI),  # 638 px
)

# ── Palette ───────────────────────────────────────────────────────────
BRAND = (37, 99, 235)        # #2563EB — matches the Excel template header
BRAND_DARK = (30, 64, 175)   # #1E40AF
INK = (17, 24, 39)           # #111827
MUTED = (107, 114, 128)      # #6B7280
LINE = (226, 232, 240)       # #E2E8F0
SURFACE = (248, 250, 252)    # #F8FAFC
WHITE = (255, 255, 255)


# ── Font resolution ───────────────────────────────────────────────────
_FONT_CACHE: dict[tuple[int, bool], ImageFont.FreeTypeFont] = {}

_REGULAR_FONTS = (
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\calibri.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
    "/Library/Fonts/Arial.ttf",
)
_BOLD_FONTS = (
    r"C:\Windows\Fonts\segoeuib.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\calibrib.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    "/Library/Fonts/Arial Bold.ttf",
)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    key = (size, bold)
    cached = _FONT_CACHE.get(key)
    if cached is not None:
        return cached

    font = None
    for path in (_BOLD_FONTS if bold else _REGULAR_FONTS):
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, size)
                break
            except OSError:
                font = None
    if font is None:
        try:
            font = ImageFont.load_default(size=size)
        except TypeError:  # very old Pillow has no sized default font
            font = ImageFont.load_default()

    _FONT_CACHE[key] = font
    return font


# ── Small drawing helpers ─────────────────────────────────────────────
def _text_height(draw: ImageDraw.ImageDraw, font) -> int:
    return font.getbbox("Ag")[3]


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    words = str(text or "").split()
    if not words:
        return []
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if not current or draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _ellipsize(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> str:
    text = str(text or "")
    if draw.textlength(text, font=font) <= max_width:
        return text
    ellipsis = "…"
    while text and draw.textlength(text + ellipsis, font=font) > max_width:
        text = text[:-1]
    return text + ellipsis


def _cover(image: Image.Image, width: int, height: int) -> Image.Image:
    """Center-crop ``image`` to ``width`` x ``height`` filling the whole box."""
    image = image.convert("RGB")
    iw, ih = image.size
    if iw == 0 or ih == 0:
        return Image.new("RGB", (width, height), SURFACE)
    scale = max(width / iw, height / ih)
    resized = image.resize(
        (max(1, round(iw * scale)), max(1, round(ih * scale))), Image.LANCZOS
    )
    nw, nh = resized.size
    left = (nw - width) // 2
    top = (nh - height) // 2
    return resized.crop((left, top, left + width, top + height))


def _rounded(image: Image.Image, radius: int) -> Image.Image:
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, image.size[0] - 1, image.size[1] - 1), radius=radius, fill=255
    )
    rounded = Image.new("RGBA", image.size, (0, 0, 0, 0))
    rounded.paste(image.convert("RGBA"), (0, 0))
    rounded.putalpha(mask)
    return rounded


def _load_field_image(field) -> Image.Image | None:
    """Return a PIL image for an ImageFieldFile, or None when absent/unreadable."""
    if not field:
        return None
    try:
        handle = field.open("rb")
    except (FileNotFoundError, OSError, ValueError):
        return None
    try:
        image = Image.open(handle)
        image.load()
        return image.convert("RGBA")
    except (OSError, ValueError):
        return None
    finally:
        try:
            handle.close()
        except Exception:  # noqa: BLE001 — closing must never break rendering
            pass


def _initials(name: str) -> str:
    parts = [p for p in str(name or "").split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _age(date_of_birth) -> int | None:
    if not date_of_birth:
        return None
    from datetime import date

    today = date.today()
    years = today.year - date_of_birth.year
    if (today.month, today.day) < (date_of_birth.month, date_of_birth.day):
        years -= 1
    return years if years >= 0 else None


def _qr_image(data: str, size: int) -> Image.Image:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    return image.resize((size, size), Image.NEAREST)


# ── Card context ──────────────────────────────────────────────────────
def resolve_card_context(student, term=None) -> dict:
    """Resolve the class / academic year / term shown on the card.

    Iterates the (possibly prefetched) enrollment set rather than filtering so a
    bulk run stays free of per-student queries.
    """
    from django.utils import timezone

    enrollments = [e for e in student.enrollments.all() if e.is_active]
    enrollment = None
    if term is not None:
        enrollment = next(
            (e for e in enrollments if e.academic_year_id == term.academic_year_id),
            None,
        )
    if enrollment is None:
        enrollment = next(
            (e for e in enrollments if getattr(e.academic_year, "is_current", False)),
            None,
        )
    if enrollment is None and enrollments:
        enrollment = enrollments[0]

    academic_year = getattr(enrollment, "academic_year", None)
    klass = getattr(enrollment, "klass", None)

    context_term = term
    if context_term is None and academic_year is not None:
        context_term = (
            student.school.terms.filter(academic_year=academic_year, is_current=True)
            .order_by("name")
            .first()
        )

    return {
        "class_name": getattr(klass, "name", None) or "—",
        "academic_year": getattr(academic_year, "name", None) or "—",
        "term_name": context_term.get_name_display()
        if context_term is not None
        else "—",
        "issued_on": timezone.localdate(),
    }


# ── Front ─────────────────────────────────────────────────────────────
HEADER_H = 108
FOOTER_H = 46
PHOTO_W = 208
PHOTO_H = 250
PAD = 28


def render_card_front(student, school, term=None, context=None) -> Image.Image:
    context = context or resolve_card_context(student, term)
    width, height = CARD_SIZE
    card = Image.new("RGB", CARD_SIZE, WHITE)
    draw = ImageDraw.Draw(card)

    # Header band with the school identity.
    draw.rectangle((0, 0, width, HEADER_H), fill=BRAND)

    logo_box = HEADER_H - 32
    logo_x = PAD
    logo_y = (HEADER_H - logo_box) // 2
    _draw_logo(card, school, logo_x, logo_y, logo_box)

    text_x = logo_x + logo_box + 18
    name_font = _font(30, bold=True)
    school_name = _ellipsize(
        draw, school.name, name_font, width - text_x - PAD
    )
    draw.text((text_x, logo_y - 2), school_name, font=name_font, fill=WHITE)
    draw.text(
        (text_x, logo_y + 40),
        "STUDENT IDENTIFICATION CARD",
        font=_font(16, bold=True),
        fill=(219, 234, 254),
    )

    # Photo box (right).
    photo_x = width - PHOTO_W - PAD
    photo_y = HEADER_H + 22
    _draw_photo(card, draw, student, photo_x, photo_y, PHOTO_W, PHOTO_H)

    # Identity block (left).
    left_x = PAD
    left_w = photo_x - PAD - 24

    name_font = _font(38, bold=True)
    current_y = HEADER_H + 20
    for line in _wrap(draw, student.full_name, name_font, left_w)[:2]:
        draw.text((left_x, current_y), line, font=name_font, fill=INK)
        current_y += _text_height(draw, name_font) + 6

    current_y += 6
    fields = [
        ("STUDENT ID", student.student_id),
        ("CLASS", context["class_name"]),
        ("GENDER", student.get_gender_display()),
    ]
    age = _age(student.date_of_birth)
    if age is not None:
        fields.append(("AGE", str(age)))

    row_height = 62
    for label, value in fields:
        if current_y + row_height > height - FOOTER_H - 6:
            break
        draw.text((left_x, current_y), label, font=_font(15, bold=True), fill=MUTED)
        value_font = _font(24, bold=True)
        draw.text(
            (left_x, current_y + 20),
            _ellipsize(draw, value, value_font, left_w),
            font=value_font,
            fill=INK,
        )
        current_y += row_height

    # Footer: validity + school contact.
    draw.rectangle((0, height - FOOTER_H, width, height), fill=SURFACE)
    draw.line((0, height - FOOTER_H, width, height - FOOTER_H), fill=LINE, width=2)
    footer_font = _font(16, bold=True)
    valid = f"Valid: {context['academic_year']}  ·  {context['term_name']}"
    draw.text((PAD, height - FOOTER_H + 14), valid, font=footer_font, fill=BRAND_DARK)
    contact = "  ·  ".join(
        part for part in (school.phone, school.email) if part
    )
    if contact:
        contact_font = _font(14)
        draw.text(
            (width - PAD - draw.textlength(contact, font=contact_font),
             height - FOOTER_H + 15),
            contact,
            font=contact_font,
            fill=MUTED,
        )

    return card


# ── Back ──────────────────────────────────────────────────────────────
def render_card_back(student, school, term=None, context=None) -> Image.Image:
    context = context or resolve_card_context(student, term)
    width, height = CARD_SIZE
    card = Image.new("RGB", CARD_SIZE, WHITE)
    draw = ImageDraw.Draw(card)

    draw.rectangle((0, 0, width, 62), fill=BRAND)
    title_font = _font(22, bold=True)
    draw.text((PAD, 18), "STUDENT IDENTIFICATION CARD", font=title_font, fill=WHITE)
    id_font = _font(18, bold=True)
    id_text = student.student_id
    draw.text(
        (width - PAD - draw.textlength(id_text, font=id_font), 20),
        id_text,
        font=id_font,
        fill=(219, 234, 254),
    )

    # QR block (left) — encodes the raw student_id.
    qr_size = 236
    qr_x = PAD + 8
    qr_y = 96
    qr = _qr_image(student.student_id, qr_size)
    card.paste(qr, (qr_x, qr_y))
    draw.rectangle(
        (qr_x - 2, qr_y - 2, qr_x + qr_size + 2, qr_y + qr_size + 2),
        outline=LINE,
        width=2,
    )
    caption_font = _font(15, bold=True)
    caption = "SCAN TO VERIFY"
    draw.text(
        (qr_x + (qr_size - draw.textlength(caption, font=caption_font)) / 2,
         qr_y + qr_size + 10),
        caption,
        font=caption_font,
        fill=MUTED,
    )

    # Details (right).
    col_x = qr_x + qr_size + 34
    col_w = width - col_x - PAD
    cursor = 96

    guardian = _primary_guardian(student)
    if guardian is not None:
        cursor = _section(draw, col_x, cursor, col_w, "EMERGENCY CONTACT")
        name_font = _font(24, bold=True)
        draw.text(
            (col_x, cursor),
            _ellipsize(draw, f"{guardian.first_name} {guardian.last_name}".strip(),
                       name_font, col_w),
            font=name_font,
            fill=INK,
        )
        cursor += _text_height(draw, name_font) + 4
        meta_font = _font(17)
        if guardian.relationship:
            draw.text(
                (col_x, cursor), guardian.get_relationship_display(),
                font=meta_font, fill=MUTED,
            )
            cursor += _text_height(draw, meta_font) + 2
        if guardian.phone:
            phone_font = _font(22, bold=True)
            draw.text((col_x, cursor), guardian.phone, font=phone_font, fill=BRAND_DARK)
            cursor += _text_height(draw, phone_font) + 12
        else:
            cursor += 10

    cursor = _section(draw, col_x, cursor, col_w, "SCHOOL")
    body_font = _font(16)
    address = ", ".join(
        part for part in (school.address, school.city, school.country) if part
    )
    for line in _wrap(draw, address, body_font, col_w)[:2]:
        draw.text((col_x, cursor), line, font=body_font, fill=INK)
        cursor += _text_height(draw, body_font) + 4
    contact = "  ·  ".join(part for part in (school.phone, school.email) if part)
    for line in _wrap(draw, contact, body_font, col_w)[:2]:
        draw.text((col_x, cursor), line, font=body_font, fill=MUTED)
        cursor += _text_height(draw, body_font) + 4

    # Footer note.
    note_font = _font(13)
    draw.line((PAD, height - 52, width - PAD, height - 52), fill=LINE, width=2)
    note = (
        f"This card is the property of {school.name}. "
        "If found, please return it to the school office."
    )
    draw.text(
        (PAD, height - 44),
        _ellipsize(draw, note, note_font, width - 2 * PAD),
        font=note_font,
        fill=MUTED,
    )

    return card


def _section(draw: ImageDraw.ImageDraw, x: int, y: int, width: int, title: str) -> int:
    font = _font(15, bold=True)
    draw.text((x, y), title, font=font, fill=BRAND)
    line_y = y + _text_height(draw, font) + 4
    draw.line((x, line_y, x + width, line_y), fill=LINE, width=2)
    return line_y + 10


def _primary_guardian(student):
    guardians = list(student.guardians.all())
    if not guardians:
        return None
    for guardian in guardians:
        if guardian.is_primary:
            return guardian
    return guardians[0]


def _draw_logo(card: Image.Image, school, x: int, y: int, box: int) -> None:
    logo = _load_field_image(school.logo)
    if logo is None:
        draw = ImageDraw.Draw(card)
        draw.rounded_rectangle((x, y, x + box, y + box), radius=14, fill=WHITE)
        initial_font = _font(int(box * 0.5), bold=True)
        initials = _initials(school.name)
        draw.text(
            (x + box / 2 - draw.textlength(initials, font=initial_font) / 2,
             y + box / 2 - _text_height(draw, initial_font) / 2 - 4),
            initials,
            font=initial_font,
            fill=BRAND,
        )
        return
    fitted = _cover(logo, box, box)
    card.paste(_rounded(fitted, 14), (x, y), _rounded(fitted, 14))


def _draw_photo(card, draw, student, x: int, y: int, width: int, height: int) -> None:
    draw.rounded_rectangle(
        (x - 3, y - 3, x + width + 3, y + height + 3),
        radius=16,
        outline=LINE,
        width=2,
    )
    photo = _load_field_image(student.profile_photo)
    if photo is None:
        draw.rounded_rectangle((x, y, x + width, y + height), radius=14, fill=SURFACE)
        initial_font = _font(int(width * 0.42), bold=True)
        initials = _initials(student.full_name)
        draw.text(
            (x + width / 2 - draw.textlength(initials, font=initial_font) / 2,
             y + height / 2 - _text_height(draw, initial_font) / 2 - 10),
            initials,
            font=initial_font,
            fill=BRAND,
        )
        return
    fitted = _rounded(_cover(photo, width, height), 14)
    card.paste(fitted, (x, y), fitted)


# ── PDF assembly ──────────────────────────────────────────────────────
def _to_pdf(pages: list[Image.Image]) -> io.BytesIO:
    if not pages:
        raise ValueError("No card pages to render.")
    rgb_pages = [page.convert("RGB") for page in pages]
    buffer = io.BytesIO()
    rgb_pages[0].save(
        buffer,
        format="PDF",
        resolution=DPI,
        save_all=True,
        append_images=rgb_pages[1:],
    )
    buffer.seek(0)
    return buffer


def build_student_card_pdf(student, school, term=None) -> io.BytesIO:
    """Front + back pages for a single student."""
    if term is None:
        term = _current_term(school)
    context = resolve_card_context(student, term)
    pages = [
        render_card_front(student, school, term, context),
        render_card_back(student, school, term, context),
    ]
    return _to_pdf(pages)


def build_students_cards_pdf(students, school, term=None) -> io.BytesIO:
    """Front + back pages for many students, in the given order."""
    if term is None:
        term = _current_term(school)
    pages: list[Image.Image] = []
    for student in students:
        context = resolve_card_context(student, term)
        pages.append(render_card_front(student, school, term, context))
        pages.append(render_card_back(student, school, term, context))
    return _to_pdf(pages)


def _current_term(school):
    from academics.services import AcademicsService

    return AcademicsService._current_term(school)
